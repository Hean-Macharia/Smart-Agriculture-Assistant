import logging
from dataclasses import dataclass

from app.models.notification import NotificationStatus
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.services.sms_providers import SmsProvider, SmsProviderError

logger = logging.getLogger(__name__)


class NotificationAccessError(Exception):
    pass


class NotificationStateError(Exception):
    pass


@dataclass(frozen=True)
class NotificationOutcome:
    notification: dict
    detail: str


def send_notification(*, recipient_user_id: str, event: str, message: str, idempotency_key: str, users: UserRepository, notifications: NotificationRepository, provider: SmsProvider) -> NotificationOutcome:
    recipient = users.get_by_id(recipient_user_id)
    if recipient is None or not recipient.get("is_active"):
        raise NotificationAccessError
    phone = recipient.get("phone")
    if not phone:
        raise NotificationStateError("The recipient account has no phone number")
    values = {
        "recipient_user_id": recipient_user_id,
        "recipient_phone": phone,
        "event": event,
        "message": message,
        "provider": provider.name,
        "idempotency_key": idempotency_key,
        "status": NotificationStatus.PENDING.value,
    }
    notification, created = notifications.create_pending(values)
    if not created:
        detail = "Notification already processed" if notification["status"] != NotificationStatus.PENDING.value else "Notification is already pending"
        return NotificationOutcome(notification, detail)
    claimed = notifications.claim(notification["id"])
    if claimed is None:
        return NotificationOutcome(notifications.get(notification["id"]), "Notification is already being processed")
    try:
        result = provider.send_sms(to=phone, message=message, idempotency_key=idempotency_key)
    except SmsProviderError:
        failed = notifications.finish(notification["id"], status=NotificationStatus.FAILED.value, provider_reference=None)
        return NotificationOutcome(failed or notifications.get(notification["id"]), "SMS provider failed; no delivery was confirmed")
    status = NotificationStatus.SIMULATED.value if result.simulated else NotificationStatus.ACCEPTED.value
    final = notifications.finish(notification["id"], status=status, provider_reference=result.provider_reference)
    detail = f"{provider.name} sandbox message simulated; it was not delivered to a handset" if result.simulated else "SMS request accepted by provider; handset delivery is not confirmed"
    return NotificationOutcome(final or notifications.get(notification["id"]), detail)


def dispatch_sms_event(*, recipient_user_id: str, event: str, event_id: str, message: str) -> None:
    """Best-effort background hook for domain events; default is opt-out/off."""
    from app.core.config import settings

    if not settings.sms_auto_dispatch:
        return
    if settings.sms_provider == "mock" and settings.app_env.lower() not in {"development", "test"}:
        logger.warning("SMS event dispatch skipped: mock provider is disabled in this environment")
        return
    try:
        # Lazy imports avoid coupling the notification layer to app construction.
        from app.core.dependencies import get_notification_repository, get_user_repository, sms_provider

        send_notification(
            recipient_user_id=recipient_user_id,
            event=event,
            message=message,
            idempotency_key=f"auto:{event}:{event_id}:{recipient_user_id}"[:128],
            users=get_user_repository(),
            notifications=get_notification_repository(),
            provider=sms_provider(),
        )
    except Exception as exc:
        # Avoid logging SMS body, phone number, provider response, or credentials.
        logger.warning("Automatic SMS event dispatch failed (%s)", type(exc).__name__)
