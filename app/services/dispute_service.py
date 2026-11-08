from app.models.dispute import DisputeStatus
from app.models.order import OrderStatus, PaymentStatus
from app.repositories.dispute_repository import DisputeRepository
from app.repositories.order_repository import OrderRepository


class DisputeAccessError(Exception):
    pass


class DisputeStateError(Exception):
    pass


def create_dispute(*, order_id: str, user_id: str, values: dict, disputes: DisputeRepository, orders: OrderRepository):
    order = orders.get(order_id)
    if order is None or user_id not in {order["buyer_id"], order["seller_id"]}:
        raise DisputeAccessError
    if order["payment_status"] != PaymentStatus.PAID.value or order["order_status"] in {OrderStatus.CANCELLED.value, OrderStatus.COMPLETED.value}:
        raise DisputeStateError("A dispute can only be opened for a paid, unresolved order")
    doc = disputes.create({**values, "order_id": order_id, "buyer_id": order["buyer_id"], "seller_id": order["seller_id"], "raised_by": user_id, "previous_order_status": order["order_status"]})
    orders.transition(order_id, [order["order_status"]], OrderStatus.DISPUTED.value)
    return doc


def review_dispute(*, dispute_id: str, admin_id: str, status: DisputeStatus, decision, resolution: str, disputes: DisputeRepository, orders: OrderRepository):
    dispute = disputes.get(dispute_id)
    if dispute is None:
        raise DisputeAccessError
    if status == DisputeStatus.UNDER_REVIEW and decision is not None:
        raise DisputeStateError("A decision may be recorded only when resolving or rejecting")
    if status in {DisputeStatus.RESOLVED, DisputeStatus.REJECTED} and decision is None:
        raise DisputeStateError("An administrator decision is required")
    if status == DisputeStatus.CLOSED:
        if dispute["status"] not in {DisputeStatus.RESOLVED.value, DisputeStatus.REJECTED.value} or decision is not None:
            raise DisputeStateError("Only a resolved or rejected dispute can be closed")
        allowed_current = [DisputeStatus.RESOLVED.value, DisputeStatus.REJECTED.value]
    elif status in {DisputeStatus.UNDER_REVIEW, DisputeStatus.RESOLVED, DisputeStatus.REJECTED}:
        allowed_current = [DisputeStatus.OPEN.value, DisputeStatus.UNDER_REVIEW.value]
    else:
        raise DisputeStateError("Unsupported administrator transition")
    updated = disputes.review(dispute_id, status=status.value, admin_id=admin_id, resolution=resolution, decision=decision.value if decision else None, allowed_current=allowed_current)
    if updated is None:
        raise DisputeStateError("Dispute is already closed or resolved")
    if status in {DisputeStatus.RESOLVED, DisputeStatus.REJECTED}:
        orders.transition(dispute["order_id"], [OrderStatus.DISPUTED.value], dispute.get("previous_order_status", OrderStatus.PAID.value))
    return updated
