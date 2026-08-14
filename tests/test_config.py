from novel.config import ModelConfig, load_config
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


def test_language_defaults_to_en(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.language == "en"


def test_language_reads_zh(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.config_path.write_text(
        "language: zh\nmodels:\n  default: { provider: deepseek, model: x }\n",
        encoding="utf-8",
    )
    cfg = load_config(proj.config_path)
    assert cfg.language == "zh"


def test_model_config_api_base_and_api_key(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.config_path.write_text(
        "models:\n"
        "  outliner: { provider: openai, model: gpt-5.6-terra,\n"
        "              api_base: https://api.gemai.cc/v1, api_key: sk-xyz }\n"
        "  default: { provider: deepseek, model: deepseek-v4-pro }\n",
        encoding="utf-8",
    )
    cfg = load_config(proj.config_path)
    mc = cfg.model_for("outliner")
    assert mc.api_base == "https://api.gemai.cc/v1"
    assert mc.api_key == "sk-xyz"
    assert cfg.model_for("default").api_base is None


def test_model_config_timeout(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.config_path.write_text(
        "models:\n"
        "  default: { provider: ollama, model: qwen2.5:14b,\n"
        "            api_base: http://localhost:11434/v1, timeout: 300 }\n",
        encoding="utf-8",
    )
    cfg = load_config(proj.config_path)
    mc = cfg.model_for("default")
    assert mc.timeout == 300
    # timeout absent -> None (litellm default)
    assert ModelConfig("openai", "x").timeout is None
