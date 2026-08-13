from novel.config import load_config
from novel.project import NovelProject


def test_load_config_and_model_lookup(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.thresholds.score_min == 80
    assert cfg.thresholds.max_retries == 3
    mc = cfg.model_for("writer")
    assert mc.provider == "zhipu" and mc.model == "glm-4-plus"
    # scorer uses a different provider than writer
    assert cfg.model_for("scorer").provider != cfg.model_for("writer").provider

def test_unknown_agent_falls_back_to_default(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    mc = cfg.model_for("does-not-exist")
    assert mc.provider and mc.model
