from datetime import date

import pytest

from conftest import TODAY, participant
from meeting_agent.classification import Level, Topic
from meeting_agent.gate import Verdict, covers, decide
from meeting_agent.models import Participant, ParticipantIn, Release


def P(**kw) -> Participant:
    return Participant(**ParticipantIn(**participant(**kw)).model_dump())


@pytest.mark.parametrize("status", ["not_signed", "pending"])
def test_unsigned_never_covers(status):
    p = P(status=status)
    assert not covers(p, Topic.GENERAL, TODAY)
    assert not covers(p, Topic.TECHNICAL, TODAY)


def test_signed_all_covers_everything():
    p = P()
    assert all(covers(p, t, TODAY) for t in Topic)


def test_scope_limits_topics():
    p = P(scope="technical")
    assert covers(p, Topic.TECHNICAL, TODAY)
    assert covers(p, Topic.GENERAL, TODAY)
    assert not covers(p, Topic.COMMERCIAL, TODAY)


def test_expired_nda_does_not_cover():
    p = P(nda_expires=date(2026, 11, 1))
    assert not covers(p, Topic.TECHNICAL, TODAY)
    assert covers(p, Topic.TECHNICAL, date(2026, 10, 1))


def chunk(chunks, doc):
    return next(c for c in chunks if c.doc == doc)


def test_public_always_allowed_even_with_unsigned(chunks, make_meeting):
    m = make_meeting([participant(status="not_signed")])
    assert decide(chunk(chunks, "docs/overview.md"), m, TODAY) is Verdict.ALLOW


def test_nda_chunk_needs_everyone_covered(chunks, make_meeting):
    c = chunk(chunks, "docs/architecture.md")
    assert decide(c, make_meeting([participant("A"), participant("B")]), TODAY) is Verdict.ALLOW
    mixed = make_meeting([participant("A"), participant("B", status="pending")])
    assert decide(c, mixed, TODAY) is Verdict.WITHHOLD_NDA


def test_scope_mismatch_withholds(chunks, make_meeting):
    m = make_meeting([participant(scope="technical")])
    assert decide(chunk(chunks, "docs/architecture.md"), m, TODAY) is Verdict.ALLOW
    assert decide(chunk(chunks, "docs/pricing-plan.md"), m, TODAY) is Verdict.WITHHOLD_NDA


def test_internal_never_allowed_and_release_cannot_lift_it(chunks, make_meeting):
    c = chunk(chunks, "docs/testlog.md")
    m = make_meeting()
    m.releases.append(Release(chunk_id=c.chunk_id, reason="please"))
    assert decide(c, m, TODAY) is Verdict.INTERNAL


def test_release_lifts_nda_once(chunks, make_meeting):
    c = chunk(chunks, "docs/architecture.md")
    m = make_meeting([participant(status="not_signed")])
    assert decide(c, m, TODAY) is Verdict.WITHHOLD_NDA
    m.releases.append(Release(chunk_id=c.chunk_id, reason="sanctioned by me"))
    assert decide(c, m, TODAY) is Verdict.ALLOW
    m.releases[0].used = True
    assert decide(c, m, TODAY) is Verdict.WITHHOLD_NDA


def test_no_participants_fails_closed(chunks, make_meeting):
    m = make_meeting()
    m.participants = []
    assert decide(chunk(chunks, "docs/architecture.md"), m, TODAY) is Verdict.WITHHOLD_NDA


def test_levels_are_exhaustive(chunks):
    assert {c.level for c in chunks} == set(Level)
