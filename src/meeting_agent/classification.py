from __future__ import annotations

from enum import Enum


class Level(str, Enum):
    PUBLIC = "public"      # safe for anyone
    NDA = "nda"            # only when every participant is covered by a signed NDA
    INTERNAL = "internal"  # never shared with anyone, NDA or not


class Topic(str, Enum):
    GENERAL = "general"
    TECHNICAL = "technical"
    COMMERCIAL = "commercial"


class Confidence(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    UNVERIFIED = "unverified"
    UNREVIEWED = "unreviewed"  # default: nobody has rated this source yet
