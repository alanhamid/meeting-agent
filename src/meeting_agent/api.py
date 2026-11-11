from __future__ import annotations

import hmac
import json
import os
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from meeting_agent.ask import ask as run_ask
from meeting_agent.classification import Level
from meeting_agent.gate import clearance_summary
from meeting_agent.gateway import Gateway, gateway_from_env
from meeting_agent.kb.loader import load_kb
from meeting_agent.kb.search import Index
from meeting_agent.models import (
    AskResult,
    Meeting,
    MeetingIn,
    MeetingStatus,
    NdaScope,
    NdaStatus,
    Participant,
    ParticipantIn,
    Release,
)
from meeting_agent.notes import make_notes
from meeting_agent.policy import load_policy
from meeting_agent.store import Store
from meeting_agent.transcripts import MAX_CHARS, Utterance, parse_transcript

ROOT = Path(__file__).resolve().parents[2]


class AskIn(BaseModel):
    question: str


class LateJoin(BaseModel):
    name: str
    organisation: str = "unknown"
    role: str = "unknown"


class NdaUpdate(BaseModel):
    nda_status: NdaStatus
    nda_scope: NdaScope = NdaScope.ALL
    nda_date: date | None = None
    nda_reference: str | None = None
    nda_expires: date | None = None


class TranscriptIn(BaseModel):
    text: str


class ReleaseIn(BaseModel):
    chunk_id: str
    reason: str


def create_app(
    kb_root: Path | None = None,
    db_path: str | None = None,
    policy_path: Path | None = None,
    gateway: Gateway | None = None,
    token: str | None = None,
    env: str | None = None,
    notes_model: bool | None = None,
) -> FastAPI:
    env = env or os.getenv("MEETING_AGENT_ENV", "dev")
    token = token if token is not None else os.getenv("MEETING_AGENT_TOKEN")
    if env == "production" and not token:
        raise RuntimeError("MEETING_AGENT_TOKEN is required when MEETING_AGENT_ENV=production")

    kb_root = kb_root or Path(os.getenv("MEETING_AGENT_KB", ROOT / "kb"))
    chunks = load_kb(kb_root) if kb_root.exists() else []
    index = Index(chunks)
    chunk_by_id = {c.chunk_id: c for c in chunks}
    policy = load_policy(policy_path or ROOT / "config" / "policy.yaml")
    store = Store(db_path or os.getenv("MEETING_AGENT_DB", ":memory:"))
    gw = gateway or gateway_from_env(dict(os.environ))
    # Transcripts hold other people's words. They go to a model only when explicitly enabled.
    if notes_model is None:
        notes_model = os.getenv("MEETING_AGENT_NOTES_MODEL", "off") == "on"
    notes_gw = gw if notes_model else None

    def auth(authorization: str | None = Header(default=None)) -> None:
        if not token:
            return
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(401, "unauthorised")

    app = FastAPI(title="meeting-agent", dependencies=[Depends(auth)])

    def get(meeting_id: str) -> Meeting:
        m = store.get_meeting(meeting_id)
        if m is None:
            raise HTTPException(404, "unknown meeting")
        return m

    def view(m: Meeting) -> dict:
        return {**m.model_dump(mode="json"), "clearance": clearance_summary(m, date.today())}

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "chunks": len(chunks),
            "env": env,
            "answer_model": type(gw).__name__,
            "notes_model": "on" if notes_model else "off (local keyword notes)",
        }

    @app.post("/api/meetings")
    def create_meeting(body: MeetingIn) -> dict:
        m = Meeting.from_in(body)
        store.save_meeting(m)
        store.add_event(m.id, "created", {"participants": [p.name for p in m.participants]})
        return view(m)

    @app.get("/api/meetings")
    def list_meetings() -> list[dict]:
        return [view(m) for m in store.list_meetings()]

    @app.get("/api/meetings/{mid}")
    def get_meeting(mid: str) -> dict:
        return view(get(mid))

    @app.post("/api/meetings/{mid}/start")
    def start(mid: str) -> dict:
        m = get(mid)
        if m.status is not MeetingStatus.DRAFT:
            raise HTTPException(409, f"meeting is {m.status.value}")
        m.status = MeetingStatus.ACTIVE
        store.save_meeting(m)
        store.add_event(m.id, "started", {})
        return view(m)

    @app.post("/api/meetings/{mid}/end")
    def end(mid: str) -> dict:
        m = get(mid)
        if m.status is not MeetingStatus.ACTIVE:
            raise HTTPException(409, f"meeting is {m.status.value}")
        m.status = MeetingStatus.ENDED
        store.save_meeting(m)
        store.add_event(m.id, "ended", {})
        return view(m)

    @app.post("/api/meetings/{mid}/participants")
    def late_join(mid: str, body: LateJoin) -> dict:
        m = get(mid)
        if m.status is MeetingStatus.ENDED:
            raise HTTPException(409, "meeting has ended")
        try:  # a late joiner is NEVER cleared until you say so
            p = Participant(
                **ParticipantIn(
                    name=body.name,
                    organisation=body.organisation,
                    role=body.role,
                    nda_status=NdaStatus.NOT_SIGNED,
                ).model_dump(),
                joined_late=True,
            )
        except ValidationError as e:
            raise HTTPException(422, str(e)) from e
        m.participants.append(p)
        store.save_meeting(m)
        store.add_event(m.id, "participant_joined", {"name": p.name, "id": p.id})
        return view(m)

    @app.put("/api/meetings/{mid}/participants/{pid}/nda")
    def set_nda(mid: str, pid: str, body: NdaUpdate) -> dict:
        m = get(mid)
        p = next((x for x in m.participants if x.id == pid), None)
        if p is None:
            raise HTTPException(404, "unknown participant")
        try:
            checked = ParticipantIn(
                name=p.name, organisation=p.organisation, role=p.role, **body.model_dump()
            )
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e
        before = p.nda_status.value
        for k in ("nda_status", "nda_scope", "nda_date", "nda_reference", "nda_expires"):
            setattr(p, k, getattr(checked, k))
        store.save_meeting(m)
        store.add_event(
            m.id,
            "nda_changed",
            {
                "participant": p.name,
                "from": before,
                "to": p.nda_status.value,
                "reference": p.nda_reference,
            },
        )
        return view(m)

    @app.post("/api/meetings/{mid}/ask", response_model=AskResult)
    def ask_endpoint(mid: str, body: AskIn) -> AskResult:
        m = get(mid)
        try:
            return run_ask(body.question, m, index, gw, policy, store)
        except PermissionError as e:
            raise HTTPException(409, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/meetings/{mid}/release")
    def release(mid: str, body: ReleaseIn) -> dict:
        m = get(mid)
        if m.status is not MeetingStatus.ACTIVE:
            raise HTTPException(409, "meeting is not active")
        c = chunk_by_id.get(body.chunk_id)
        if c is None:
            raise HTTPException(404, "unknown passage")
        if c.level is not Level.NDA:
            raise HTTPException(403, "only NDA-level passages can be released; internal never")
        try:
            r = Release(chunk_id=body.chunk_id, reason=body.reason.strip())
        except ValidationError as e:
            raise HTTPException(422, "a reason is required") from e
        m.releases.append(r)
        store.save_meeting(m)
        store.add_event(m.id, "release", {"chunk_id": r.chunk_id, "reason": r.reason})
        return view(m)

    @app.get("/api/meetings/{mid}/followups")
    def followups(mid: str) -> list[dict]:
        get(mid)
        return store.followups(mid)

    @app.post("/api/meetings/{mid}/followups/{fid}/done")
    def followup_done(mid: str, fid: str) -> dict:
        get(mid)
        if not store.close_followup(mid, fid):
            raise HTTPException(404, "unknown follow-up")
        return {"ok": True}

    @app.get("/api/meetings/{mid}/events")
    def events(mid: str) -> list[dict]:
        get(mid)
        return store.events(mid)

    @app.post("/api/meetings/{mid}/transcript")
    def add_transcript(mid: str, body: TranscriptIn) -> dict:
        m = get(mid)
        if m.status is MeetingStatus.DRAFT:
            raise HTTPException(409, "start the meeting first")
        if len(body.text) > MAX_CHARS:
            raise HTTPException(413, f"transcript too large (max {MAX_CHARS} characters)")
        utts = parse_transcript(body.text)
        if not utts:
            raise HTTPException(422, "no speech found in transcript")
        tid = store.add_transcript(mid, [u.__dict__ for u in utts])
        store.add_event(mid, "transcript_added", {"id": tid, "turns": len(utts)})
        return {"id": tid, "turns": len(utts), "speakers": list(dict.fromkeys(u.speaker for u in utts))}

    @app.post("/api/meetings/{mid}/notes")
    def generate_notes(mid: str) -> dict:
        m = get(mid)
        t = store.latest_transcript(mid)
        if t is None:
            raise HTTPException(409, "add a transcript first")
        tid, raw = t
        notes = make_notes(m, [Utterance(**u) for u in raw], notes_gw, store.followups(mid))
        store.add_notes(mid, tid, notes.model_dump_json())
        store.add_event(mid, "notes_generated", {"transcript_id": tid, "method": notes.method})
        return notes.model_dump(mode="json")

    @app.get("/api/meetings/{mid}/notes")
    def get_notes(mid: str) -> dict:
        get(mid)
        raw = store.latest_notes(mid)
        if raw is None:
            raise HTTPException(404, "no notes yet")
        return json.loads(raw)

    static = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app


def app_factory() -> FastAPI:
    return create_app()
