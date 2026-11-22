from enum import Enum


class TreatmentRecordType(str, Enum):
    CULTURAL = "CULTURAL"
    BIOLOGICAL = "BIOLOGICAL"
    CHEMICAL = "CHEMICAL"
    OTHER = "OTHER"


class DiseaseCaseStatus(str, Enum):
    OPEN = "OPEN"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    RESOLVED = "RESOLVED"
