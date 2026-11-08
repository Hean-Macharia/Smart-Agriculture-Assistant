from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from app.core.config import settings
from app.core.dependencies import get_current_user, get_notification_repository, get_user_repository, require_roles, sms_provider
from app.models.user import UserRole
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.notification import NotificationListResponse, NotificationPublic, NotificationSend, NotificationSendResponse
from app.schemas.user import UserPublic
from app.services.notification_service import NotificationAccessError, NotificationStateError, send_notification
from app.services.sms_providers import SmsProvider

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/mine", response_model=NotificationListResponse, summary="List my in-app notification and SMS attempt history")
def my_notifications(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: UserPublic = Depends(get_current_user), repo: NotificationRepository = Depends(get_notification_repository)):
    items, total = repo.list_for_user(user.id, skip=offset, limit=limit)
    return NotificationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/send", response_model=NotificationSendResponse, summary="Send an event SMS to a registered user (admin/officer operation)")
def send_event_sms(payload: NotificationSend, response: Response, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)], user: UserPublic = Depends(require_roles(UserRole.ADMIN, UserRole.AGRICULTURAL_OFFICER)), users: UserRepository = Depends(get_user_repository), notifications: NotificationRepository = Depends(get_notification_repository), provider: SmsProvider = Depends(sms_provider)):
    if settings.sms_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        raise HTTPException(status_code=503, detail="Mock SMS is disabled outside development/test")
    try:
        outcome = send_notification(recipient_user_id=payload.recipient_user_id, event=payload.event.value, message=payload.message, idempotency_key=idempotency_key, users=users, notifications=notifications, provider=provider)
        if outcome.notification["status"] == "FAILED":
            response.status_code = 502
        return NotificationSendResponse(notification=NotificationPublic.model_validate(outcome.notification), detail=outcome.detail)
    except NotificationAccessError:
        raise HTTPException(status_code=404, detail="Recipient account not found") from None
    except NotificationStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
