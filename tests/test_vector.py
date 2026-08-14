from novel.project import NovelProject
from novel.store.vector import VectorMemory, hash_embed


def test_add_and_retrieve(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    vm = VectorMemory(proj, embed=hash_embed)
    vm.add_chapter(1, "The thief entered the cathedral at midnight.")
    vm.add_summary("chapter", "ch1", "Ara meets the informant in the tavern.")
    hits = vm.retrieve("cathedral midnight", k=2)
    assert any("cathedral" in h for h in hits)

def test_hash_embed_dimension_stable(tmp_path):
    e = hash_embed("hello world")
    assert len(e) == len(hash_embed("hi"))
    assert all(-1.0 <= x <= 1.0 for x in e)
