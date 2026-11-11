from meeting_agent.classification import Level


def by_doc(chunks, doc):
    return [c for c in chunks if c.doc == doc]


def test_levels_follow_manifest(chunks):
    assert {c.level for c in by_doc(chunks, "docs/overview.md")} == {Level.PUBLIC}
    assert {c.level for c in by_doc(chunks, "docs/architecture.md")} == {Level.NDA}
    assert {c.level for c in by_doc(chunks, "docs/testlog.md")} == {Level.INTERNAL}


def test_unlisted_file_fails_closed_to_internal(chunks):
    unlisted = by_doc(chunks, "unlisted.md")
    assert unlisted and {c.level for c in unlisted} == {Level.INTERNAL}


def test_section_override_makes_do_not_say_internal(chunks):
    pitch = by_doc(chunks, "docs/pitch.md")
    dns = [c for c in pitch if "Osprey" in c.text]
    story = [c for c in pitch if "credit unions" in c.text]
    assert dns and all(c.level is Level.INTERNAL for c in dns)
    assert story and all(c.level is Level.PUBLIC for c in story)


def test_no_public_chunk_contains_internal_text(chunks):
    for c in chunks:
        if c.level is Level.PUBLIC:
            assert "Osprey" not in c.text and "Falcon" not in c.text and "Heron" not in c.text


def test_chunk_ids_unique(chunks):
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
