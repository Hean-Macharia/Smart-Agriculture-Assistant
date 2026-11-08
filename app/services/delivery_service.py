from app.models.delivery import DeliveryStatus
from app.models.order import OrderStatus
from app.repositories.delivery_repository import DeliveryRepository
from app.repositories.order_repository import OrderRepository


class DeliveryAccessError(Exception):
    pass


class DeliveryStateError(Exception):
    pass


def create_delivery(*, order_id: str, seller_id: str, payload: dict, deliveries: DeliveryRepository, orders: OrderRepository):
    order = orders.get(order_id)
    if order is None or order["seller_id"] != seller_id:
        raise DeliveryAccessError
    if order["order_status"] not in {OrderStatus.READY_FOR_DELIVERY.value, OrderStatus.IN_TRANSIT.value}:
        raise DeliveryStateError("Order must be ready for delivery")
    values = {**payload, "order_id": order_id, "buyer_id": order["buyer_id"], "seller_id": order["seller_id"]}
    return deliveries.create(values)


def update_delivery(*, delivery_id: str, actor_id: str, is_admin: bool, target: DeliveryStatus, note: str | None, deliveries: DeliveryRepository, orders: OrderRepository):
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise DeliveryAccessError
    if not is_admin and actor_id != delivery["seller_id"]:
        raise DeliveryAccessError
    transitions = {
        DeliveryStatus.PICKED_UP: [DeliveryStatus.PENDING.value],
        DeliveryStatus.IN_TRANSIT: [DeliveryStatus.PICKED_UP.value],
        DeliveryStatus.DELIVERED: [DeliveryStatus.IN_TRANSIT.value],
    }
    if is_admin:
        transitions[DeliveryStatus.PICKED_UP] = [DeliveryStatus.PENDING.value]
        transitions[DeliveryStatus.IN_TRANSIT] = [DeliveryStatus.PENDING.value, DeliveryStatus.PICKED_UP.value]
        transitions[DeliveryStatus.DELIVERED] = [DeliveryStatus.PICKED_UP.value, DeliveryStatus.IN_TRANSIT.value]
    allowed = transitions.get(target)
    if not allowed:
        raise DeliveryStateError("Only the buyer can confirm delivery")
    updated = deliveries.transition(delivery_id, allowed, target.value, actor_id, note)
    if updated is None:
        raise DeliveryStateError("Delivery status transition is not allowed")
    if target == DeliveryStatus.IN_TRANSIT:
        orders.transition(delivery["order_id"], [OrderStatus.READY_FOR_DELIVERY.value], OrderStatus.IN_TRANSIT.value)
    elif target == DeliveryStatus.DELIVERED:
        orders.transition(delivery["order_id"], [OrderStatus.IN_TRANSIT.value, OrderStatus.READY_FOR_DELIVERY.value], OrderStatus.DELIVERED.value)
    return updated


def confirm_delivery(*, delivery_id: str, buyer_id: str, deliveries: DeliveryRepository, orders: OrderRepository):
    delivery = deliveries.get(delivery_id)
    if delivery is None or delivery["buyer_id"] != buyer_id:
        raise DeliveryAccessError
    updated = deliveries.transition(delivery_id, [DeliveryStatus.DELIVERED.value], DeliveryStatus.CONFIRMED.value, buyer_id, "Buyer confirmed receipt")
    if updated is None:
        raise DeliveryStateError("Only a delivered order can be confirmed")
    order = orders.transition(delivery["order_id"], [OrderStatus.DELIVERED.value], OrderStatus.COMPLETED.value)
    if order is None:
        raise DeliveryStateError("Order is not eligible for completion")
    return updated
