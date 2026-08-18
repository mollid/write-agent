from novel.models import WeakDim
from novel.project import NovelProject
from novel.store.notes import WritingNotes


def _proj(tmp_path):
    return NovelProject.scaffold("n", genre="g", root=tmp_path)


def test_feedback_roundtrip_and_dedup(tmp_path):
    notes = WritingNotes(_proj(tmp_path))
    assert notes.add_feedback("setup:world", "基调更黑暗") is True
    assert notes.add_feedback("setup:world", "基调更黑暗") is False  # identical → dedup
    assert notes.add_feedback("setup:world", "少用长段独白") is True  # same source, new text
    assert notes.add_feedback("setup:concept", "基调更黑暗") is True  # same text, new source
    assert notes.add_feedback("setup:outline", "   ") is False        # blank → ignored
    fb = notes.recent_feedback()
    assert [n.text for n in fb] == ["基调更黑暗", "少用长段独白", "基调更黑暗"]
    assert fb[0].source == "setup:world" and fb[0].kind == "feedback"


def test_recent_feedback_limit_keeps_latest(tmp_path):
    notes = WritingNotes(_proj(tmp_path))
    for i in range(15):
        notes.add_feedback("setup:world", f"意见{i}")
    fb = notes.recent_feedback()
    assert len(fb) == 12
    assert fb[0].text == "意见3" and fb[-1].text == "意见14"


def test_weak_notes_latest_attempt_wins_and_window_caps(tmp_path):
    notes = WritingNotes(_proj(tmp_path))
    notes.add_weak(1, {"prose": (76, "对白过多"), "pacing": (70, "前松后紧")})
    notes.add_weak(1, {"prose": (74, "对白仍多")})  # attempt 2: prose overwritten, pacing kept
    for ch in (2, 3, 4, 5, 6, 7):                    # chapters beyond the 5-chapter window
        notes.add_weak(ch, {"prose": (60, "x")})
    by_ch = notes.weak_by_chapter()
    assert sorted(by_ch) == [3, 4, 5, 6, 7]          # only the latest 5 chapters
    # merge semantics on a fresh store: later attempts overwrite per dimension
    notes2 = WritingNotes(NovelProject.scaffold("n2", genre="g", root=tmp_path))
    notes2.add_weak(1, {"prose": (76, "对白过多"), "pacing": (70, "前松后紧")})
    notes2.add_weak(1, {"prose": (74, "对白仍多")})
    assert notes2.weak_by_chapter() == {1: {
        "prose": WeakDim(score=74, critique="对白仍多"),
        "pacing": WeakDim(score=70, critique="前松后紧"),
    }}


def test_torn_trailing_line_skipped(tmp_path):
    proj = _proj(tmp_path)
    notes = WritingNotes(proj)
    notes.add_feedback("setup:world", "基调更黑暗")
    with notes.path().open("a", encoding="utf-8") as f:
        f.write('{"kind": "feedba')  # crash mid-append
    assert len(WritingNotes(proj).list_all()) == 1
