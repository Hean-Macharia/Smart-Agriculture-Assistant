from enum import Enum


class AdvisoryKind(str, Enum):
    OFFICER = "OFFICER"
    WEATHER_RULE = "WEATHER_RULE"
