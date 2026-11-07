from bson import ObjectId

from app.models.marketplace import ProductAvailability
from app.models.order import OrderStatus, PaymentStatus
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate


class StockUnavailableError(Exception):
    """The listing is inactive or does not have enough stock."""


class OrderStateConflictError(Exception):
    """Requested order transition is not currently allowed."""


class OrderAccessError(Exception):
    """The authenticated account does not own this order or listing."""


def place_order(
    orders: OrderRepository,
    products: MarketplaceRepository,
    buyer_id: str,
    payload: OrderCreate,
) -> dict:
    order_id = str(ObjectId())
    product = products.get(payload.product_id)
    if product is None or product["availability_status"] != ProductAvailability.ACTIVE:
        raise StockUnavailableError
    if product["farmer_id"] == buyer_id:
        raise OrderAccessError

    reserved_product = products.reserve_stock(payload.product_id, payload.quantity, order_id)
    if reserved_product is None:
        raise StockUnavailableError

    values = {
        "_id": ObjectId(order_id),
        "buyer_id": buyer_id,
        "seller_id": reserved_product["farmer_id"],
        "product_id": payload.product_id,
        "product_name": reserved_product["product_name"],
        "quantity": payload.quantity,
        "unit": reserved_product["unit"],
        "unit_price_kes": reserved_product["price_per_unit_kes"],
        "total_amount_kes": payload.quantity * reserved_product["price_per_unit_kes"],
        "delivery_information": payload.delivery_information.model_dump(),
        "payment_status": PaymentStatus.UNPAID.value,
        "order_status": OrderStatus.AWAITING_PAYMENT.value,
    }
    try:
        return orders.create(values)
    except Exception:
        # A write timeout can happen after MongoDB committed the insert. Check by the
        # preassigned order ID before compensating, or a committed order could be unreserved.
        saved_order = orders.get(order_id)
        if saved_order is not None:
            return saved_order
        products.release_stock(payload.product_id, payload.quantity, order_id)
        raise


def cancel_order(
    orders: OrderRepository,
    products: MarketplaceRepository,
    order_id: str,
    buyer_id: str,
) -> dict:
    order = orders.get(order_id)
    if order is None or order["buyer_id"] != buyer_id:
        raise OrderAccessError
    if order["order_status"] == OrderStatus.CANCELLED.value:
        # Makes a retry safe if the prior request changed order state but failed while restoring stock.
        products.release_stock(order["product_id"], order["quantity"], order_id)
        return order
    if order["order_status"] != OrderStatus.AWAITING_PAYMENT.value or order["payment_status"] != PaymentStatus.UNPAID.value:
        raise OrderStateConflictError

    cancelled = orders.transition(order_id, [OrderStatus.AWAITING_PAYMENT.value], OrderStatus.CANCELLED.value)
    if cancelled is None:
        latest = orders.get(order_id)
        if latest is None or latest["buyer_id"] != buyer_id:
            raise OrderAccessError
        if latest["order_status"] == OrderStatus.CANCELLED.value:
            products.release_stock(latest["product_id"], latest["quantity"], order_id)
            return latest
        raise OrderStateConflictError

    products.release_stock(cancelled["product_id"], cancelled["quantity"], order_id)
    return cancelled


def update_seller_order_status(orders: OrderRepository, order_id: str, seller_id: str, target: OrderStatus) -> dict:
    order = orders.get(order_id)
    if order is None or order["seller_id"] != seller_id:
        raise OrderAccessError
    transitions = {
        OrderStatus.PROCESSING: [OrderStatus.PAID.value],
        OrderStatus.READY_FOR_DELIVERY: [OrderStatus.PROCESSING.value],
    }
    allowed_current = transitions.get(target)
    if allowed_current is None:
        raise OrderStateConflictError
    updated = orders.transition(order_id, allowed_current, target.value)
    if updated is None:
        raise OrderStateConflictError
    return updated
