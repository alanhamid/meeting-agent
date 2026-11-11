"""The clearance gate: deterministic, runs before any model call. Fail closed."""
from __future__ import annotations

from datetime import date
from enum import Enum

from meeting_agent.classification import Level, Topic
from meeting_agent.kb.loader import Chunk
from meeting_agent.models import Meeting, NdaScope, NdaStatus, Participant


class Verdict(str, Enum):
    ALLOW = "allow"
    WITHHOLD_NDA = "withhold_nda"  # would be allowed once the NDA situation is fixed
    INTERNAL = "internal"          # never shareable


def covers(p: Participant, topic: Topic, today: date) -> bool:
    if p.nda_status is not NdaStatus.SIGNED:
        return False
    if p.nda_expires is not None and p.nda_expires < today:
        return False
    if p.nda_scope is NdaScope.ALL or topic is Topic.GENERAL:
        return True
    return p.nda_scope.value == topic.value


def uncleared_for(meeting: Meeting, topic: Topic, today: date) -> list[Participant]:
    return [p for p in meeting.participants if not covers(p, topic, today)]


def decide(chunk: Chunk, meeting: Meeting, today: date) -> Verdict:
    if chunk.level is Level.PUBLIC:
        return Verdict.ALLOW
    if chunk.level is Level.INTERNAL:
        return Verdict.INTERNAL  # releases can never lift this
    if any(r.chunk_id == chunk.chunk_id and not r.used for r in meeting.releases):
        return Verdict.ALLOW
    if not meeting.participants or uncleared_for(meeting, chunk.topic, today):
        return Verdict.WITHHOLD_NDA
    return Verdict.ALLOW


def clearance_summary(meeting: Meeting, today: date) -> dict:
    """What the dashboard banner shows."""
    out = {}
    for topic in (Topic.TECHNICAL, Topic.COMMERCIAL):
        blockers = uncleared_for(meeting, topic, today)
        out[topic.value] = {
            "cleared": not blockers and bool(meeting.participants),
            "blocked_by": [p.name for p in blockers],
        }
    return out
