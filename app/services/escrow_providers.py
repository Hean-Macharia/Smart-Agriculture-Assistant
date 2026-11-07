"""Escrow adapters distinguish an internal workflow from actual funds custody."""

from dataclasses import dataclass
from typing import Protocol


class EscrowProviderError(RuntimeError):
    """A safeguarded-funds provider is unavailable or rejected an action."""


@dataclass(frozen=True)
class SafeguardResult:
    provider_safeguarded: bool
    provider_reference: str | None
    description: str


@dataclass(frozen=True)
class ReleaseResult:
    simulated_settlement: bool
    provider_settled: bool
    provider_reference: str | None


class EscrowProvider(Protocol):
    name: str

    def confirm_safeguarding(self, *, payment_reference: str, amount_kes: int) -> SafeguardResult: ...

    def release(self, *, idempotency_key: str, seller_amount_kes: int) -> ReleaseResult: ...

    def request_refund(self, *, idempotency_key: str, amount_kes: int) -> ReleaseResult: ...


class MockEscrowProvider:
    """Development simulation. It never receives, holds, or transfers money."""

    name = "mock"

    def confirm_safeguarding(self, *, payment_reference: str, amount_kes: int) -> SafeguardResult:
        del payment_reference, amount_kes
        return SafeguardResult(False, None, "Mock provider does not safeguard real funds")

    def release(self, *, idempotency_key: str, seller_amount_kes: int) -> ReleaseResult:
        del seller_amount_kes
        return ReleaseResult(True, False, f"MOCK-RELEASE-{idempotency_key[:16]}")

    def request_refund(self, *, idempotency_key: str, amount_kes: int) -> ReleaseResult:
        del amount_kes
        return ReleaseResult(True, False, f"MOCK-REFUND-{idempotency_key[:16]}")


class PartnerEscrowProvider:
    """Fail-closed adapter boundary for an authorised safeguarding partner."""

    name = "partner"

    def _not_configured(self):
        raise EscrowProviderError("No safeguarded-funds partner adapter is configured")

    def confirm_safeguarding(self, *, payment_reference: str, amount_kes: int) -> SafeguardResult:
        del payment_reference, amount_kes
        self._not_configured()

    def release(self, *, idempotency_key: str, seller_amount_kes: int) -> ReleaseResult:
        del idempotency_key, seller_amount_kes
        self._not_configured()

    def request_refund(self, *, idempotency_key: str, amount_kes: int) -> ReleaseResult:
        del idempotency_key, amount_kes
        self._not_configured()


def get_escrow_provider() -> EscrowProvider:
    from app.core.config import settings

    if settings.escrow_provider == "partner":
        return PartnerEscrowProvider()
    return MockEscrowProvider()
