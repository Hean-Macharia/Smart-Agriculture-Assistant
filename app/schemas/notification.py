from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationEvent, NotificationStatus


class NotificationSend(BaseModel):
    recipient_user_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    event: NotificationEvent
    message: str = Field(min_length=5, max_length=500)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NotificationPublic(BaseModel):
    id: str
    recipient_user_id: str
    event: NotificationEvent
    message: str
    provider: str
    status: NotificationStatus
    provider_reference: str | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationPublic]
    total: int
    limit: int
    offset: int


class NotificationSendResponse(BaseModel):
    notification: NotificationPublic
    detail: str
