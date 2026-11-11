from meeting_agent.classification import Confidence, Level, Topic
from meeting_agent.kb.loader import Chunk, load_kb
from meeting_agent.kb.search import Index, stem, tokens


def C(cid, title, text, level=Level.PUBLIC):
    return Chunk(cid, "d.md", title, text, level, Topic.GENERAL, Confidence.UNREVIEWED)


def test_stemming_matches_inflections():
    assert stem("payments") == stem("payment") and stem("tampering") == stem("tamper")
    assert "limit" in tokens("How are limits widened?")


def test_title_and_phrase_boost_rank_the_right_chunk():
    cs = [
        C("a", "Overview", "The kill is mentioned. A switch is separate. Audit audit audit entries."),
        C("b", "Kill switch", "One admin can narrow immediately."),
        C("c", "Other", "Kill switch appears here only in passing among many unrelated words about audit."),
    ]
    top = Index(cs).search("how does the kill switch work")[0]
    assert top.chunk.chunk_id == "b"


def test_levels_filter_applies():
    cs = [C("p", "Alpha topic", "alpha beta gamma"), C("i", "Alpha topic", "alpha beta gamma", Level.INTERNAL)]
    ix = Index(cs)
    assert [h.chunk.chunk_id for h in ix.search("alpha beta", levels={Level.PUBLIC})] == ["p"]
    assert [h.chunk.chunk_id for h in ix.search("alpha beta", levels={Level.INTERNAL})] == ["i"]


def test_table_rows_become_separate_chunks(tmp_path):
    (tmp_path / "t.md").write_text(
        "# Q&A\n\n| Question | Answer |\n|---|---|\n| Moat? | We have none yet |\n"
        "| Stablecoins? | Simulated only |\n| Customer? | None signed |\n"
    )
    (tmp_path / "manifest.yaml").write_text('entries:\n  - {path: "t.md", level: public}\n')
    chunks = load_kb(tmp_path)
    rows = [c for c in chunks if "Simulated" in c.text or "None signed" in c.text]
    assert len(rows) == 2 and all(c.text.count("|") <= 4 for c in rows)
    top = Index(chunks).search("do you have stablecoins")[0]
    assert "Simulated" in top.chunk.text


def test_internal_chunks_cannot_crowd_out_answerable_ones(index, gw, policy, store, make_meeting):
    from meeting_agent.ask import ask
    from meeting_agent.models import Outcome

    m = make_meeting()
    r = ask("How does Zebra Gateway approval work", m, index, gw, policy, store)
    assert r.outcome is Outcome.ANSWERED
