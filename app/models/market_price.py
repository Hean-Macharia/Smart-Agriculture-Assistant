from enum import Enum


class MarketPriceSource(str, Enum):
    MANUAL = "MANUAL"
    EXTERNAL = "EXTERNAL"
