from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from meeting_agent.classification import Level, Topic  # noqa: F401  (re-export)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Platform(str, Enum):
    ZOOM = "zoom"
    TEAMS = "teams"
    IN_PERSON = "in_person"
    OTHER = "other"


class Stakeholder(str, Enum):
    INVESTOR = "investor"
    MICROSOFT = "microsoft"
    STRATEGIC_ENTERPRISE = "strategic_enterprise"  # interested in the controlled pilot
    CREDIT_UNION_OR_BANK = "credit_union_or_bank"
    TECHNICAL_ALLY = "technical_ally"
    OTHER = "other"


class NdaStatus(str, Enum):
    SIGNED = "signed"
    NOT_SIGNED = "not_signed"
    PENDING = "pending"


class NdaScope(str, Enum):
    ALL = "all"
    TECHNICAL = "technical"
    COMMERCIAL = "commercial"


class ParticipantIn(BaseModel):
    """nda_status has no default on purpose: the dashboard forces an explicit answer."""

    name: str = Field(min_length=1)
    organisation: str = Field(min_length=1)
    role: str = Field(min_length=1)
    nda_status: NdaStatus
    nda_scope: NdaScope = NdaScope.ALL
    nda_date: date | None = None
    nda_reference: str | None = None
    nda_expires: date | None = None

    @field_validator("name", "organisation", "role")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def _signed_needs_evidence(self) -> ParticipantIn:
        if self.nda_status is NdaStatus.SIGNED and not (self.nda_date and self.nda_reference):
            raise ValueError("a signed NDA needs nda_date and nda_reference")
        return self


class Participant(ParticipantIn):
    id: str = Field(default_factory=new_id)
    joined_late: bool = False


class MeetingIn(BaseModel):
    title: str = Field(min_length=1)
    meeting_date: date
    platform: Platform
    stakeholder: Stakeholder
    goal: str = Field(min_length=1)
    avoid_topics: list[str] = []
    participants: list[ParticipantIn] = Field(min_length=1)


class MeetingStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ENDED = "ended"


class Release(BaseModel):
    chunk_id: str
    reason: str = Field(min_length=3)
    used: bool = False


class Meeting(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str
    meeting_date: date
    platform: Platform
    stakeholder: Stakeholder
    goal: str
    avoid_topics: list[str] = []
    participants: list[Participant]
    status: MeetingStatus = MeetingStatus.DRAFT
    releases: list[Release] = []

    @classmethod
    def from_in(cls, m: MeetingIn) -> Meeting:
        return cls(
            title=m.title.strip(),
            meeting_date=m.meeting_date,
            platform=m.platform,
            stakeholder=m.stakeholder,
            goal=m.goal.strip(),
            avoid_topics=[t.strip() for t in m.avoid_topics if t.strip()],
            participants=[Participant(**p.model_dump()) for p in m.participants],
        )


class Source(BaseModel):
    chunk_id: str
    title: str
    level: Level
    confidence: str


class Warning_(BaseModel):
    rule_id: str
    message: str


class PrivateNote(BaseModel):
    chunk_id: str
    title: str
    excerpt: str


class Outcome(str, Enum):
    ANSWERED = "answered"
    WITHHELD_NDA = "withheld_nda"
    NO_ANSWER = "no_answer"
    AVOID_TOPIC = "avoid_topic"


class AskResult(BaseModel):
    outcome: Outcome
    say: str
    sources: list[Source] = []
    withheld: list[Source] = []       # presenter-only: lets you tap "release once"
    private_notes: list[PrivateNote] = []  # presenter-only: internal material, never spoken
    warnings: list[Warning_] = []
    followup_id: str | None = None
    uncleared: list[str] = []         # names of participants blocking NDA-level content
    degraded: bool = False            # model was unavailable; answer is a plain quote
