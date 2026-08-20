from novel.models import Character, Concept, Event, Foreshadow
from novel.project import NovelProject
from novel.store.bible import StoryBible


def _bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    return StoryBible(proj)

def test_concept_round_trip_and_md_mirror(tmp_path):
    b = _bible(tmp_path)
    c = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"], target_length_words=30000, audience="a")
    b.set_concept(c)
    assert b.get_concept() == c
    assert "fantasy" in (b.proj.root / "bible" / "concept.md").read_text(encoding="utf-8")

def test_character_upsert_and_state_update(tmp_path):
    b = _bible(tmp_path)
    ch = Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                   motivation="m", arc="a")
    b.upsert_character(ch)
    ch.state.emotional_state = "angry"
    b.upsert_character(ch)
    assert b.get_character("c1").state.emotional_state == "angry"

def test_foreshadow_and_events(tmp_path):
    b = _bible(tmp_path)
    b.add_foreshadow(Foreshadow(id="f1", description="a dagger"))
    b.append_event(Event(id="e1", chapter=1, summary="meeting"))
    assert b.list_foreshadow()[0].id == "f1"
    assert b.list_events()[0].id == "e1"


def test_apply_chapter_updates_batches_canonical_writes(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    from novel.models import ChapterBeat, CharacterState, KeyEvent
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    writes = {"n": 0}
    real_save = proj.save_canonical

    def counting_save(data):
        writes["n"] += 1
        real_save(data)

    proj.save_canonical = counting_save  # type: ignore[method-assign]
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d",
                       characters=["c1"], plants=["the bell"], payoffs=[])
    upd = ChapterUpdates(
        character_states={"c1": CharacterState(emotional_state="resolve", location_end="tower")},
        voice_samples={"c1": "drawl"}, mannerisms_used={"c1": ["taps table"]},
        key_events=[KeyEvent(event="bell rings", significance="pivot", affected_characters=["c1"])])
    bible.apply_chapter_updates(1, upd, [beat])
    c1 = bible.get_character("c1")
    assert c1.state.emotional_state == "resolve" and c1.last_updated_chapter == 1
    assert c1.voice_fingerprint["sample_1"] == "drawl"
    assert writes["n"] == 1            # ONE canonical write for the whole chapter
    assert any(e.id == "evt_1_1" for e in bible.list_events())
    assert any(f.description == "the bell" for f in bible.list_foreshadow())


def test_voice_compaction_keeps_earliest_and_recent_nine(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.upsert_character(Character(id="c1", slug="a", name="Ara", role="p",
                                     backstory="b", motivation="m", arc="a"))
    for n in range(1, 16):   # 15 chapters of samples
        bible.apply_chapter_updates(n, ChapterUpdates(voice_samples={"c1": f"v{n}"}), [])
    vf = bible.get_character("c1").voice_fingerprint
    assert len(vf) == 10
    assert vf["sample_1"] == "v1"            # 定调样本保留
    assert vf["sample_15"] == "v15"          # 最近样本保留
    assert "sample_2" not in vf


def test_payoff_archives_to_resolved_jsonl(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    from novel.models import ChapterBeat
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.add_foreshadow(Foreshadow(id="fs-1", description="the bell", planted_ch=1))
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d",
                       characters=["c1"], payoffs=["the bell"])
    bible.apply_chapter_updates(9, ChapterUpdates(), [beat])
    assert bible.list_foreshadow() == []     # paid-off: gone from the open ledger
    resolved = (proj.root / ".meta" / "threads_resolved.jsonl").read_text(encoding="utf-8")
    assert '"status":"paid_off"' in resolved.replace(" ", "") and '"payoff_ch":9' in resolved


def test_list_events_tail_only(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    for i in range(1, 11):
        bible.append_event(Event(id=f"e{i}", chapter=i, summary=f"s{i}"))
    tail = bible.list_events(last=3)
    assert [e.id for e in tail] == ["e8", "e9", "e10"]
    assert len(bible.list_events()) == 10
