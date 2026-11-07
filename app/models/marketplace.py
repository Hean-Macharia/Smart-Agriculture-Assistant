from enum import Enum


class ProductAvailability(str, Enum):
    ACTIVE = "ACTIVE"
    SOLD_OUT = "SOLD_OUT"
    INACTIVE = "INACTIVE"
