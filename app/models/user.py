from enum import Enum


class UserRole(str, Enum):
    FARMER = "FARMER"
    BUYER = "BUYER"
    ADMIN = "ADMIN"
    AGRICULTURAL_OFFICER = "AGRICULTURAL_OFFICER"
