import hashlib
import hmac
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.core.config import settings
from app.core.dependencies import get_current_user, get_farm_repository, get_market_price_repository, get_notification_repository, get_sms_preferences_repository, get_user_repository, require_roles, sms_provider
from app.models.user import UserRole
from app.repositories.farm_repository import FarmRepository
from app.repositories.market_price_repository import MarketPriceRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.notification import NotificationListResponse, NotificationPublic, NotificationSend, NotificationSendResponse, SmsDeliveryReceipt, SmsPreferencesPublic, SmsPreferencesUpdate
from app.schemas.user import UserPublic
from app.services.notification_service import NotificationAccessError, NotificationConsentRequiredError, NotificationStateError, send_notification
from app.repositories.sms_repository import SmsPreferencesRepository
from app.services.sms_providers import SmsProvider, SmsProviderError
from app.services.weather_service import WeatherProviderError, fetch_weather_forecast
from app.utils.phones import normalize_kenyan_mobile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/preferences", response_model=SmsPreferencesPublic, summary="Get my SMS consent and notification preferences")
def get_my_sms_preferences(user: UserPublic = Depends(get_current_user), preferences: SmsPreferencesRepository = Depends(get_sms_preferences_repository)):
    return preferences.get_for_user(user.id, user.phone)


@router.put("/preferences", response_model=SmsPreferencesPublic, summary="Set SMS consent, language and message categories")
def update_my_sms_preferences(payload: SmsPreferencesUpdate, user: UserPublic = Depends(get_current_user), preferences: SmsPreferencesRepository = Depends(get_sms_preferences_repository)):
    try:
        phone = normalize_kenyan_mobile(user.phone)
    except ValueError:
        raise HTTPException(status_code=409, detail="Update your account with a valid Kenyan mobile number first") from None
    return preferences.save_for_user(
        user_id=user.id,
        phone_number=phone,
        consented=payload.consented,
        language=payload.language,
        categories=[event.value for event in payload.categories],
    )


@router.get("/mine", response_model=NotificationListResponse, summary="List my in-app notification and SMS attempt history")
def my_notifications(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(get_current_user), repo: NotificationRepository = Depends(get_notification_repository)):
    items, total = repo.list_for_user(user.id, skip=offset, limit=limit)
    return NotificationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/send", response_model=NotificationSendResponse, summary="Send an event SMS to a registered user (admin/officer operation)")
def send_event_sms(payload: NotificationSend, response: Response, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)], user: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)), users: UserRepository = Depends(get_user_repository), notifications: NotificationRepository = Depends(get_notification_repository), preferences: SmsPreferencesRepository = Depends(get_sms_preferences_repository), provider: SmsProvider = Depends(sms_provider)):
    if settings.sms_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Mock SMS is disabled outside development/test")
    try:
        outcome = send_notification(recipient_user_id=payload.recipient_user_id, event=payload.event.value, message=payload.message, idempotency_key=idempotency_key, users=users, notifications=notifications, preferences=preferences, provider=provider)
        if outcome.notification["status"] == "FAILED":
            response.status_code = 502
        return NotificationSendResponse(notification=NotificationPublic.model_validate(outcome.notification), detail=outcome.detail)
    except NotificationAccessError:
        raise HTTPException(status_code=404, detail="Recipient account not found") from None
    except NotificationConsentRequiredError:
        raise HTTPException(status_code=409, detail="Recipient has not consented to this SMS category") from None
    except NotificationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


def _inbound_reply(command: str, *, phone: str, preferences: SmsPreferencesRepository, users: UserRepository, prices: MarketPriceRepository, farms: FarmRepository) -> tuple[str, str]:
    tokens = command.strip().split()
    keyword = tokens[0].upper() if tokens else ""
    argument = " ".join(tokens[1:])[:80]
    current_preferences = preferences.get_for_phone(phone) or {}
    kiswahili = current_preferences.get("language", "en") == "sw"
    if keyword == "STOP":
        return "STOP", "Umeondolewa kwenye SMS za ShambaLink. Jibu START kujiunga tena." if kiswahili else "You are opted out of ShambaLink SMS. Reply START to opt in again."
    if keyword == "START":
        return "START", "Umejiunga na taarifa za ShambaLink. Jibu STOP kusitisha." if kiswahili else "You are opted in to ShambaLink SMS. Reply STOP to opt out."
    if keyword == "HELP":
        return "HELP", "Amri: WEATHER, PRICE MAIZE, ADVICE TOMATO, LANG SW, HELP, STOP, START." if kiswahili else "Commands: WEATHER, PRICE MAIZE, ADVICE TOMATO, LANG SW, HELP, STOP, START. Prices can change."
    if keyword == "LANG" and argument.upper() in {"EN", "SW"}:
        return "LANG", "Lugha imewekwa Kiswahili." if argument.upper() == "SW" else "Language set to English."
    if keyword == "PRICE" and argument:
        items, _ = prices.list_prices(crop_name=argument, county=None, market_location=None, start_date=None, end_date=None, skip=0, limit=1)
        if not items:
            return "PRICE", "Hakuna bei iliyorekodiwa. Uliza afisa wa kilimo." if kiswahili else "No recorded price is available. Ask your agricultural officer."
        item = items[0]
        if kiswahili:
            return "PRICE", f"Bei iliyorekodiwa: {item['crop_name']} KES {item['price_kes']}/{item['unit']} {item['market_location']}, {item['date_collected']}. Inaweza kubadilika."
        return "PRICE", f"Recorded price: {item['crop_name']} KES {item['price_kes']}/{item['unit']} at {item['market_location']} on {item['date_collected']}. It may change."
    if keyword == "WEATHER":
        account = users.get_by_phone(phone)
        if account:
            farms_list, _ = farms.list_for_owner(str(account["_id"]), skip=0, limit=10)
            selected = next((farm for farm in farms_list if farm.get("latitude") is not None and farm.get("longitude") is not None), None)
            if selected:
                try:
                    weather = fetch_weather_forecast(selected["latitude"], selected["longitude"])
                    observation = weather.current
                    if kiswahili:
                        return "WEATHER", f"Hali ya hewa {selected['county']}: {observation.conditions}, {observation.temperature_c:.0f}C, unyevu {observation.humidity_percent}%. Chanzo: OpenWeatherMap."
                    return "WEATHER", f"Weather {selected['county']}: {observation.conditions}, {observation.temperature_c:.0f}C, humidity {observation.humidity_percent}%. Source: OpenWeatherMap."
                except WeatherProviderError:
                    pass
        return "WEATHER", "Utabiri haupatikani. Hifadhi eneo la shamba au wasiliana na afisa." if kiswahili else "Forecast unavailable. Save farm coordinates or contact your agricultural officer."
    if keyword == "ADVICE" and argument:
        from app.services.pest_knowledge_service import list_pest_knowledge
        entries = list_pest_knowledge(argument)
        if entries:
            guidance = entries[0]["prevention_and_nonchemical_management"][0]
            return "ADVICE", guidance[:155]
        return "ADVICE", "Hakuna mwongozo uliokaguliwa wa zao hilo. Uliza afisa wa kilimo." if kiswahili else "No reviewed crop guide is available. Ask your agricultural officer."
    return keyword or "UNKNOWN", "Amri haijatambuliwa. Tuma HELP." if kiswahili else "Command not recognized. Text HELP for options."


@router.post("/inbound/africas-talking", summary="Receive authenticated inbound SMS commands")
async def receive_inbound_sms(
    request: Request,
    x_sms_webhook_token: str | None = Header(default=None, alias="X-SMS-Webhook-Token"),
    preferences: SmsPreferencesRepository = Depends(get_sms_preferences_repository),
    users: UserRepository = Depends(get_user_repository),
    prices: MarketPriceRepository = Depends(get_market_price_repository),
    farms: FarmRepository = Depends(get_farm_repository),
    provider: SmsProvider = Depends(sms_provider),
):
    secret = settings.sms_webhook_secret.strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Inbound SMS authentication is not configured")
    if x_sms_webhook_token is None or not hmac.compare_digest(x_sms_webhook_token, secret):
        raise HTTPException(status_code=401, detail="Invalid SMS callback credentials")
    form = await request.form()
    try:
        phone = normalize_kenyan_mobile(str(form.get("from", "")))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid sender phone number") from None
    provider_message_id = str(form.get("id", "")).strip()
    command = str(form.get("text", "")).strip()[:120]
    if not provider_message_id or not command:
        raise HTTPException(status_code=422, detail="Provider message id and command are required")
    command_key = command.split()[0].upper()
    try:
        accepted = preferences.accept_inbound(
            provider_message_id=provider_message_id,
            phone_number=phone,
            command=command_key,
            hourly_limit=settings.sms_inbound_hourly_limit,
        )
    except Exception as exc:
        logger.warning("Inbound SMS persistence failed: type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="SMS service temporarily unavailable") from None
    if not accepted:
        # Duplicate IDs and sender throttling are both acknowledged without a reply.
        return {"status": "duplicate_or_rate_limited"}
    if command_key == "STOP":
        preferences.set_phone_consent(phone_number=phone, consented=False, source="inbound_sms")
    elif command_key == "START":
        preferences.set_phone_consent(phone_number=phone, consented=True, source="inbound_sms")
    elif command_key == "LANG":
        parts = command.split()
        language = parts[1].lower() if len(parts) > 1 else ""
        if language in {"sw", "en"}:
            preferences.set_phone_language(phone_number=phone, language=language, source="inbound_sms")
    reply = ""
    try:
        _, reply = _inbound_reply(command, phone=phone, preferences=preferences, users=users, prices=prices, farms=farms)
        result = provider.send_sms(to=phone, message=reply, idempotency_key=f"inbound:{provider_message_id}:reply")
    except SmsProviderError as exc:
        logger.warning("Inbound SMS reply failed: type=%s", type(exc).__name__)
        return {"status": "accepted_reply_failed"}
    return {"status": "simulated" if result.simulated else "accepted", "detail": "Provider acceptance is not handset delivery confirmation"}


@router.post("/callback/delivery", summary="Accept a signed SMS delivery receipt")
async def sms_delivery_receipt(
    request: Request,
    x_sms_signature: str | None = Header(default=None, alias="X-SMS-Signature"),
    notifications: NotificationRepository = Depends(get_notification_repository),
):
    secret = settings.sms_webhook_secret.strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="SMS delivery callback is not configured")
    raw = await request.body()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    supplied = (x_sms_signature or "").removeprefix("sha256=")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid SMS delivery signature")
    try:
        payload = SmsDeliveryReceipt.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid delivery receipt") from None
    updated = notifications.update_delivery_receipt(payload.message_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="No accepted message matches this provider reference")
    return {"status": updated["status"]}
