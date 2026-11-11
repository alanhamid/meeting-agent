import pytest

from conftest import participant
from meeting_agent.ask import ask
from meeting_agent.models import MeetingStatus, Outcome, Release


def run(q, m, index, gw, policy, store):
    return ask(q, m, index, gw, policy, store)


def test_public_question_answered_with_sources(index, gw, policy, store, make_meeting):
    m = make_meeting([participant(status="not_signed")])
    r = run("How does Zebra Gateway approval work?", m, index, gw, policy, store)
    assert r.outcome is Outcome.ANSWERED
    assert r.sources and r.sources[0].chunk_id.startswith("docs/overview.md")


def test_uncleared_meeting_never_sends_nda_text_to_model(index, gw, policy, store, make_meeting):
    m = make_meeting([participant("Ann"), participant("Bob", status="not_signed")])
    r = run("Tell me about the Quartz ledger audit trail", m, index, gw, policy, store)
    assert r.outcome is Outcome.WITHHELD_NDA
    assert "signed NDA" in r.say
    assert r.uncleared == ["Bob"]
    assert gw.calls == []  # the model was never even called
    assert "Quartz" not in r.say


def test_nda_text_not_in_prompt_even_when_public_hit_also_present(
    index, gw, policy, store, make_meeting
):
    m = make_meeting([participant(status="pending")])
    run("How does Zebra Gateway approval and the Quartz ledger audit work?", m, index, gw, policy, store)
    assert "Quartz" not in gw.seen_text and "hash chained" not in gw.seen_text


def test_withheld_logs_followup_naming_blockers(index, gw, policy, store, make_meeting):
    m = make_meeting([participant("Ann", status="not_signed")])
    r = run("Explain the Marigold pricing tiers", m, index, gw, policy, store)
    assert r.outcome is Outcome.WITHHELD_NDA and r.followup_id
    f = store.followups(m.id)
    assert len(f) == 1 and f[0]["reason"] == "nda" and f[0]["who"] == ["Ann"]


def test_cleared_meeting_gets_nda_answer(index, gw, policy, store, make_meeting):
    m = make_meeting([participant("Ann"), participant("Bob")])
    r = run("Tell me about the Quartz ledger audit trail", m, index, gw, policy, store)
    assert r.outcome is Outcome.ANSWERED
    assert "Quartz" in r.say


def test_internal_never_reaches_model_but_shows_privately(index, gw, policy, store, make_meeting):
    m = make_meeting([participant("Ann"), participant("Bob")])
    r = run("Is the Falcon reconciliation module tested against a real bank?", m, index, gw, policy, store)
    assert "Falcon" not in gw.seen_text and "Falcon" not in r.say
    assert r.outcome is Outcome.NO_ANSWER
    assert any("Falcon" in n.excerpt for n in r.private_notes)


def test_unlisted_file_is_internal_in_answers(index, gw, policy, store, make_meeting):
    m = make_meeting()
    r = run("What is the Heron secret roadmap?", m, index, gw, policy, store)
    assert "Heron" not in r.say and "Heron" not in gw.seen_text


def test_do_not_say_section_never_spoken(index, gw, policy, store, make_meeting):
    m = make_meeting()
    r = run("Do you have Osprey certification?", m, index, gw, policy, store)
    assert "Osprey" not in gw.seen_text and "Osprey" not in r.say


def test_no_match_gives_no_answer_script_and_followup(index, gw, policy, store, make_meeting):
    m = make_meeting()
    r = run("What colour is the sky on Mars?", m, index, gw, policy, store)
    assert r.outcome is Outcome.NO_ANSWER and "confirmed answer" in r.say
    assert store.followups(m.id)[0]["reason"] == "no_answer"


def test_avoid_topic_short_circuits_before_retrieval(index, gw, policy, store, make_meeting):
    m = make_meeting(avoid_topics=["valuation"])
    r = run("What is the valuation of Zebra Gateway?", m, index, gw, policy, store)
    assert r.outcome is Outcome.AVOID_TOPIC and gw.calls == []


def test_release_is_single_use(index, gw, policy, store, make_meeting):
    m = make_meeting([participant(status="not_signed")])
    q = "Tell me about the Quartz ledger audit trail"
    first = run(q, m, index, gw, policy, store)
    cid = first.withheld[0].chunk_id
    m.releases.append(Release(chunk_id=cid, reason="Presenter approved for this one question"))
    store.save_meeting(m)
    second = run(q, m, index, gw, policy, store)
    assert second.outcome is Outcome.ANSWERED and "Quartz" in second.say
    third = run(q, store.get_meeting(m.id), index, gw, policy, store)
    assert third.outcome is Outcome.WITHHELD_NDA


@pytest.mark.parametrize("status", [MeetingStatus.DRAFT, MeetingStatus.ENDED])
def test_ask_requires_active_meeting(status, index, gw, policy, store, make_meeting):
    m = make_meeting()
    m.status = status
    with pytest.raises(PermissionError):
        run("Zebra Gateway approval", m, index, gw, policy, store)


def test_policy_warns_on_question_and_stakeholder_rule(index, gw, policy, store, make_meeting):
    m = make_meeting(stakeholder="microsoft")
    r = run("Is Zebra Gateway a Foundry agent and production ready?", m, index, gw, policy, store)
    ids = {w.rule_id for w in r.warnings}
    assert {"foundry", "production-ready"} <= ids
    inv = make_meeting(stakeholder="investor")
    r2 = run("Is Zebra Gateway a Foundry agent?", inv, index, gw, policy, store)
    assert "foundry" not in {w.rule_id for w in r2.warnings}


def test_every_ask_is_logged(index, gw, policy, store, make_meeting):
    m = make_meeting()
    run("Zebra Gateway approval", m, index, gw, policy, store)
    assert [e["kind"] for e in store.events(m.id)] == ["ask"]
