from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from meeting_agent.gateway import Passage
from meeting_agent.kb.loader import load_kb
from meeting_agent.kb.search import Index
from meeting_agent.models import Meeting, MeetingIn, MeetingStatus
from meeting_agent.policy import load_policy
from meeting_agent.store import Store

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_KB = Path(__file__).parent / "fixtures" / "kb"


class RecordingGateway:
    """Captures exactly what the model would have been given."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[Passage]]] = []

    def answer(self, system, question, passages):
        self.calls.append((system, question, passages))
        body = [ln for ln in passages[0].text.splitlines() if ln.strip() and not ln.startswith("#")] if passages else []
        return " ".join(body)

    @property
    def seen_text(self) -> str:
        return "\n".join(
            s + q + "".join(p.title + p.text for p in ps) for s, q, ps in self.calls
        )


def participant(name="Ann", status="signed", scope="all", **kw):
    p = {"name": name, "organisation": "Org", "role": "CFO", "nda_status": status, "nda_scope": scope}
    if status == "signed":
        p.update(nda_date="2026-01-05", nda_reference="DOC-1")
    p.update(kw)
    return p


def meeting_in(participants=None, stakeholder="investor", **kw) -> dict:
    d = {
        "title": "Intro",
        "meeting_date": "2026-11-09",
        "platform": "zoom",
        "stakeholder": stakeholder,
        "goal": "Explain the pilot",
        "avoid_topics": [],
        "participants": participants if participants is not None else [participant()],
    }
    d.update(kw)
    return d


@pytest.fixture
def chunks():
    return load_kb(FIXTURE_KB)


@pytest.fixture
def index(chunks):
    return Index(chunks)


@pytest.fixture
def policy():
    return load_policy(ROOT / "config" / "policy.yaml")


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def gw():
    return RecordingGateway()


@pytest.fixture
def make_meeting(store):
    def _make(participants=None, stakeholder="investor", active=True, **kw) -> Meeting:
        m = Meeting.from_in(MeetingIn(**meeting_in(participants, stakeholder, **kw)))
        if active:
            m.status = MeetingStatus.ACTIVE
        store.save_meeting(m)
        return m

    return _make


TODAY = date(2026, 11, 9)
