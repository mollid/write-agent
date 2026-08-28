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


def test_min_chapter_chars_default_and_override(tmp_path):
    from novel.project import NovelProject
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.generation.min_chapter_chars == 50  # default, and below demo prose (62 chars)

    text = proj.config_path.read_text(encoding="utf-8")
    proj.config_path.write_text(
        text.replace("generation:", "generation:\n  min_chapter_chars: 2000"),
        encoding="utf-8",
    )
    cfg2 = load_config(proj.config_path)
    assert cfg2.generation.min_chapter_chars == 2000


def test_generation_longform_fields_parse(tmp_path):
    from novel.config import load_config
    cfg_file = tmp_path / "project.config.yaml"
    cfg_file.write_text(
        "models: { default: { provider: zhipu, model: glm-4-plus } }\n"
        "generation:\n"
        "  target_chapters: 240\n"
        "  chapter_target_length: 3000\n"
        "  arc_detail_lookahead: 10\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.generation.target_chapters == 240
    assert cfg.generation.chapter_target_length == 3000
    assert cfg.generation.arc_detail_lookahead == 10


def test_generation_longform_fields_default_off():
    from novel.config import Generation
    g = Generation()
    assert g.target_chapters is None and g.chapter_target_length == 2500 and g.arc_detail_lookahead == 5


def test_network_proxy_config_parses(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.config_path.write_text(
        "models: { default: { provider: openai, model: x } }\n"
        "network:\n"
        "  proxy: http://127.0.0.1:7890\n"
        "  no_proxy: localhost,127.0.0.1\n",
        encoding="utf-8",
    )
    cfg = load_config(proj.config_path)
    assert cfg.network.proxy == "http://127.0.0.1:7890"
    assert cfg.network.no_proxy == "localhost,127.0.0.1"


def test_network_config_defaults_when_absent(tmp_path):
    from novel.config import NetworkConfig
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.network.proxy is None and cfg.network.no_proxy is None
    assert NetworkConfig().proxy is None
