"""Seller payout orchestration. Uses the escrow provider and its fail-closed rules."""

from app.repositories.escrow_repository import EscrowRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.transaction_repository import TransactionLedgerRepository
from app.services.escrow_providers import EscrowProvider
from app.services.escrow_service import request_seller_release


def request_payout(*, escrow_id: str, seller_id: str, escrows: EscrowRepository, orders: OrderRepository, ledger: TransactionLedgerRepository, provider: EscrowProvider, is_admin: bool = False):
    return request_seller_release(escrow_id=escrow_id, seller_id=seller_id, escrows=escrows, orders=orders, ledger=ledger, provider=provider, is_admin=is_admin)
