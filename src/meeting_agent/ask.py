"""The ask pipeline.

Order matters: (1) retrieve over everything, (2) gate each hit, (3) only cleared passages go
to the model, (4) policy checks run on the question and the draft.

Rules:
- If the best hit among {cleared, NDA-withheld} is NDA-withheld, we do not answer from weaker
  cleared hits; we give the fixed NDA script and log a follow-up.
- INTERNAL hits never reach the model and never block an answer; they surface as private notes
  for the presenter only.
"""
from __future__ import annotations

from datetime import date

from meeting_agent.classification import Level
from meeting_agent.gate import Verdict, decide, uncleared_for
from meeting_agent.gateway import ExtractiveGateway, Gateway, GatewayError, Passage, build_system
from meeting_agent.kb.search import Hit, Index
from meeting_agent.models import (
    AskResult,
    Meeting,
    MeetingStatus,
    Outcome,
    PrivateNote,
    Source,
)
from meeting_agent.policy import Policy
from meeting_agent.store import Store

TOP_K = 6
MAX_PASSAGES = 3
EXCERPT = 240


def _source(h: Hit) -> Source:
    c = h.chunk
    return Source(chunk_id=c.chunk_id, title=c.title, level=c.level, confidence=c.confidence.value)


def ask(
    question: str,
    meeting: Meeting,
    index: Index,
    gateway: Gateway,
    policy: Policy,
    store: Store,
    today: date | None = None,
) -> AskResult:
    today = today or date.today()
    question = question.strip()
    if meeting.status is not MeetingStatus.ACTIVE:
        raise PermissionError("meeting is not active")
    if not question:
        raise ValueError("empty question")

    warnings = policy.check(question, meeting.stakeholder)

    q_low = question.lower()
    if any(t.lower() in q_low for t in meeting.avoid_topics):
        fid = store.add_followup(meeting.id, "avoid_topic", question, [])
        store.add_event(meeting.id, "ask", {"question": question, "outcome": "avoid_topic"})
        return AskResult(
            outcome=Outcome.AVOID_TOPIC,
            say=policy.scripts["avoid_topic"],
            warnings=warnings,
            followup_id=fid,
        )

    # Internal material is searched separately so it can never crowd out answerable passages.
    hits = index.search(question, k=TOP_K, levels={Level.PUBLIC, Level.NDA})
    internal_hits = index.search(question, k=3, levels={Level.INTERNAL})
    verdicts = [(h, decide(h.chunk, meeting, today)) for h in hits + internal_hits]
    allowed = [h for h, v in verdicts if v is Verdict.ALLOW]
    withheld = [h for h, v in verdicts if v is Verdict.WITHHOLD_NDA]
    internal = [h for h, v in verdicts if v is Verdict.INTERNAL]

    notes = [
        PrivateNote(
            chunk_id=h.chunk.chunk_id,
            title=h.chunk.title,
            excerpt=h.chunk.text[:EXCERPT].replace("\n", " "),
        )
        for h in internal[:3]
    ]

    top_relevant = next((h for h, v in verdicts if v is not Verdict.INTERNAL), None)
    if top_relevant is not None and any(h is top_relevant for h in withheld):
        blockers = sorted({p.name for p in uncleared_for(meeting, top_relevant.chunk.topic, today)})
        fid = store.add_followup(meeting.id, "nda", question, blockers)
        store.add_event(
            meeting.id,
            "ask",
            {
                "question": question,
                "outcome": "withheld_nda",
                "withheld": [h.chunk.chunk_id for h in withheld],
            },
        )
        return AskResult(
            outcome=Outcome.WITHHELD_NDA,
            say=policy.scripts["nda"],
            withheld=[_source(h) for h in withheld],
            private_notes=notes,
            warnings=warnings,
            followup_id=fid,
            uncleared=blockers,
        )

    if not allowed:
        fid = store.add_followup(meeting.id, "no_answer", question, [])
        store.add_event(meeting.id, "ask", {"question": question, "outcome": "no_answer"})
        return AskResult(
            outcome=Outcome.NO_ANSWER,
            say=policy.scripts["no_answer"],
            private_notes=notes,
            warnings=warnings,
            followup_id=fid,
        )

    used = allowed[:MAX_PASSAGES]
    passages = [Passage(h.chunk.chunk_id, h.chunk.title, h.chunk.text) for h in used]
    degraded = False
    try:
        draft = gateway.answer(build_system(meeting), question, passages).strip()
    except GatewayError:
        # Model unavailable mid-meeting: fall back to quoting the cleared passage, and say so.
        degraded = True
        draft = ExtractiveGateway().answer("", question, passages).strip()
    warnings += [w for w in policy.check(draft, meeting.stakeholder) if w not in warnings]

    # A release is single use: consume it once the passage has actually been used.
    used_ids = {h.chunk.chunk_id for h in used}
    for r in meeting.releases:
        if r.chunk_id in used_ids and not r.used:
            r.used = True
    store.save_meeting(meeting)

    store.add_event(
        meeting.id,
        "ask",
        {"question": question, "outcome": "answered", "sources": sorted(used_ids), "degraded": degraded},
    )
    return AskResult(
        outcome=Outcome.ANSWERED,
        say=draft or policy.scripts["no_answer"],
        sources=[_source(h) for h in used],
        withheld=[_source(h) for h in withheld],
        private_notes=notes,
        warnings=warnings,
        degraded=degraded,
    )
