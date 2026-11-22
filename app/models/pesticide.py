from enum import Enum


class PesticideReviewStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PesticideReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
