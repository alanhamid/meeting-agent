"""SQLite store. Events are append-only (enforced by triggers); follow-ups only change status."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime

from meeting_agent.models import Meeting, new_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL,
  ts TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TABLE IF NOT EXISTS followups (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, created TEXT NOT NULL,
  reason TEXT NOT NULL, question TEXT NOT NULL, who TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS transcripts (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, created TEXT NOT NULL, body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS transcripts_no_update BEFORE UPDATE ON transcripts
  BEGIN SELECT RAISE(ABORT, 'transcripts are immutable'); END;
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL, transcript_id TEXT NOT NULL,
  created TEXT NOT NULL, body TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def save_meeting(self, m: Meeting) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO meetings(id, body) VALUES(?, ?) "
                "ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                (m.id, m.model_dump_json()),
            )

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        with self._lock:
            r = self._db.execute("SELECT body FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        return Meeting.model_validate_json(r["body"]) if r else None

    def list_meetings(self) -> list[Meeting]:
        with self._lock:
            rows = self._db.execute("SELECT body FROM meetings").fetchall()
        return [Meeting.model_validate_json(r["body"]) for r in rows]

    def add_event(self, meeting_id: str, kind: str, body: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events(meeting_id, ts, kind, body) VALUES(?,?,?,?)",
                (meeting_id, _now(), kind, json.dumps(body, default=str)),
            )

    def events(self, meeting_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, kind, body FROM events WHERE meeting_id=? ORDER BY id", (meeting_id,)
            ).fetchall()
        return [{"ts": r["ts"], "kind": r["kind"], **json.loads(r["body"])} for r in rows]

    def add_followup(self, meeting_id: str, reason: str, question: str, who: list[str]) -> str:
        fid = new_id()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO followups(id, meeting_id, created, reason, question, who) "
                "VALUES(?,?,?,?,?,?)",
                (fid, meeting_id, _now(), reason, question, json.dumps(who)),
            )
        return fid

    def followups(self, meeting_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM followups WHERE meeting_id=? ORDER BY created, id", (meeting_id,)
            ).fetchall()
        return [{**dict(r), "who": json.loads(r["who"])} for r in rows]

    def close_followup(self, meeting_id: str, followup_id: str) -> bool:
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE followups SET status='done' WHERE id=? AND meeting_id=?",
                (followup_id, meeting_id),
            )
        return cur.rowcount == 1

    def add_transcript(self, meeting_id: str, utterances: list[dict]) -> str:
        tid = new_id()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO transcripts(id, meeting_id, created, body) VALUES(?,?,?,?)",
                (tid, meeting_id, _now(), json.dumps(utterances)),
            )
        return tid

    def latest_transcript(self, meeting_id: str) -> tuple[str, list[dict]] | None:
        with self._lock:
            r = self._db.execute(
                "SELECT id, body FROM transcripts WHERE meeting_id=? ORDER BY created DESC, rowid DESC LIMIT 1",
                (meeting_id,),
            ).fetchone()
        return (r["id"], json.loads(r["body"])) if r else None

    def add_notes(self, meeting_id: str, transcript_id: str, body: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO notes(meeting_id, transcript_id, created, body) VALUES(?,?,?,?)",
                (meeting_id, transcript_id, _now(), body),
            )

    def latest_notes(self, meeting_id: str) -> str | None:
        with self._lock:
            r = self._db.execute(
                "SELECT body FROM notes WHERE meeting_id=? ORDER BY id DESC LIMIT 1", (meeting_id,)
            ).fetchone()
        return r["body"] if r else None
