"""Development-only USSD menu simulator. No carrier gateway is connected."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.ussd_service import MockUssdProvider, UssdRequest
from app.utils.phones import normalize_kenyan_mobile

router = APIRouter(prefix="/ussd", tags=["USSD"])


class UssdSimulationRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=10, max_length=20)
    text: str = Field(default="", max_length=300)
    language: str = Field(default="en", pattern=r"^(en|sw)$")

    model_config = ConfigDict(extra="forbid")


@router.post("/mock/session", summary="Simulate a USSD menu response in development")
def mock_ussd_session(payload: UssdSimulationRequest):
    if settings.app_env.lower() not in {"development", "dev", "test", "testing", "local"}:
        raise HTTPException(status_code=404, detail="USSD simulator is only available in development")
    try:
        phone = normalize_kenyan_mobile(payload.phone_number)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid Kenyan mobile number") from None
    provider = MockUssdProvider()
    menu = provider.respond(UssdRequest(payload.session_id, phone, payload.text, payload.language))
    return {"provider": provider.name, "live_gateway_connected": False, "response": menu}
