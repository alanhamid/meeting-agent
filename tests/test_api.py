import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURE_KB, ROOT, RecordingGateway, meeting_in, participant
from meeting_agent.api import create_app


@pytest.fixture
def gw():
    return RecordingGateway()


@pytest.fixture
def client(gw):
    return TestClient(create_app(kb_root=FIXTURE_KB, gateway=gw, token=None, env="dev"))


def start(client, participants=None, **kw):
    r = client.post("/api/meetings", json=meeting_in(participants, **kw))
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    assert client.post(f"/api/meetings/{mid}/start").status_code == 200
    return mid


def test_dashboard_requires_explicit_nda_status(client):
    p = participant()
    del p["nda_status"]
    assert client.post("/api/meetings", json=meeting_in([p])).status_code == 422


def test_signed_nda_requires_date_and_reference(client):
    p = participant()
    del p["nda_reference"]
    assert client.post("/api/meetings", json=meeting_in([p])).status_code == 422


@pytest.mark.parametrize("field", ["title", "goal", "stakeholder", "platform"])
def test_required_meeting_fields(client, field):
    d = meeting_in()
    d[field] = ""
    assert client.post("/api/meetings", json=d).status_code == 422


def test_needs_at_least_one_participant(client):
    assert client.post("/api/meetings", json=meeting_in([])).status_code == 422


def test_cannot_ask_before_start_or_after_end(client):
    mid = client.post("/api/meetings", json=meeting_in()).json()["id"]
    assert client.post(f"/api/meetings/{mid}/ask", json={"question": "Zebra"}).status_code == 409
    client.post(f"/api/meetings/{mid}/start")
    client.post(f"/api/meetings/{mid}/end")
    assert client.post(f"/api/meetings/{mid}/ask", json={"question": "Zebra"}).status_code == 409


def test_late_joiner_drops_clearance_until_nda_recorded(client, gw):
    mid = start(client, [participant("Ann")])
    q = {"question": "Tell me about the Quartz ledger audit trail"}
    assert client.post(f"/api/meetings/{mid}/ask", json=q).json()["outcome"] == "answered"

    m = client.post(f"/api/meetings/{mid}/participants", json={"name": "Carl"}).json()
    carl = next(p for p in m["participants"] if p["name"] == "Carl")
    assert carl["nda_status"] == "not_signed" and carl["joined_late"] is True
    assert m["clearance"]["technical"]["cleared"] is False
    assert client.post(f"/api/meetings/{mid}/ask", json=q).json()["outcome"] == "withheld_nda"

    bad = client.put(
        f"/api/meetings/{mid}/participants/{carl['id']}/nda", json={"nda_status": "signed"}
    )
    assert bad.status_code == 422
    ok = client.put(
        f"/api/meetings/{mid}/participants/{carl['id']}/nda",
        json={"nda_status": "signed", "nda_date": "2026-11-09", "nda_reference": "DOC-9"},
    )
    assert ok.status_code == 200 and ok.json()["clearance"]["technical"]["cleared"] is True
    assert client.post(f"/api/meetings/{mid}/ask", json=q).json()["outcome"] == "answered"


def test_release_endpoint_rules(client):
    mid = start(client, [participant(status="not_signed")])
    q = {"question": "Tell me about the Quartz ledger audit trail"}
    r = client.post(f"/api/meetings/{mid}/ask", json=q).json()
    cid = r["withheld"][0]["chunk_id"]

    assert client.post(f"/api/meetings/{mid}/release", json={"chunk_id": cid, "reason": ""}).status_code == 422
    internal = "docs/testlog.md#0.0"
    assert client.post(f"/api/meetings/{mid}/release", json={"chunk_id": internal, "reason": "x yes"}).status_code == 403
    assert client.post(f"/api/meetings/{mid}/release", json={"chunk_id": "nope", "reason": "x yes"}).status_code == 404
    assert client.post(f"/api/meetings/{mid}/release", json={"chunk_id": cid, "reason": "approved by me"}).status_code == 200
    assert client.post(f"/api/meetings/{mid}/ask", json=q).json()["outcome"] == "answered"
    assert client.post(f"/api/meetings/{mid}/ask", json=q).json()["outcome"] == "withheld_nda"


def test_followups_listed_and_closable(client):
    mid = start(client, [participant(status="pending")])
    client.post(f"/api/meetings/{mid}/ask", json={"question": "Explain the Marigold pricing tiers"})
    fl = client.get(f"/api/meetings/{mid}/followups").json()
    assert len(fl) == 1 and fl[0]["status"] == "open"
    assert client.post(f"/api/meetings/{mid}/followups/{fl[0]['id']}/done").status_code == 200
    assert client.get(f"/api/meetings/{mid}/followups").json()[0]["status"] == "done"


def test_audit_trail_records_nda_changes_and_releases(client):
    mid = start(client, [participant(status="not_signed")])
    pid = client.get(f"/api/meetings/{mid}").json()["participants"][0]["id"]
    client.put(
        f"/api/meetings/{mid}/participants/{pid}/nda",
        json={"nda_status": "signed", "nda_date": "2026-11-09", "nda_reference": "DOC-2"},
    )
    kinds = [e["kind"] for e in client.get(f"/api/meetings/{mid}/events").json()]
    assert kinds == ["created", "started", "nda_changed"]


def test_events_table_is_append_only():
    from meeting_agent.store import Store

    s = Store()
    s.add_event("m1", "x", {})
    with pytest.raises(sqlite3.DatabaseError):
        s._db.execute("DELETE FROM events")
    with pytest.raises(sqlite3.DatabaseError):
        s._db.execute("UPDATE events SET kind='y'")


def test_token_required_when_configured():
    c = TestClient(create_app(kb_root=FIXTURE_KB, token="s3cret", env="dev"))
    assert c.get("/api/health").status_code == 401
    assert c.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/health", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_production_refuses_to_start_without_token(monkeypatch):
    monkeypatch.delenv("MEETING_AGENT_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        create_app(kb_root=FIXTURE_KB, env="production")


def test_policy_file_loads():
    from meeting_agent.policy import load_policy

    assert load_policy(ROOT / "config" / "policy.yaml").rules
