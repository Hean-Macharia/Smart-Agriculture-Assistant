"""Phone-number normalization for Kenyan mobile network numbers."""

import re


def normalize_kenyan_mobile(value: str) -> str:
    """Return E.164 (+254...) for supported Kenyan mobile numbers."""
    normalized = re.sub(r"[\s()-]", "", value)
    if re.fullmatch(r"0[17]\d{8}", normalized):
        normalized = "+254" + normalized[1:]
    elif re.fullmatch(r"254[17]\d{8}", normalized):
        normalized = "+" + normalized
    if not re.fullmatch(r"\+254[17]\d{8}", normalized):
        raise ValueError("Use a valid Kenyan mobile number such as +254712345678")
    return normalized
