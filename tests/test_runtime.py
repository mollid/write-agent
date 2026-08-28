"""make_provider 的代理导出：network.proxy -> HTTP(S)_PROXY 环境变量（仅 live 模式）。

litellm/openai 走 httpx trust_env，必须在首个 httpx client 构建前设置；
这里只验证环境变量副作用，不真正发起网络请求。
"""
import os

import pytest

from novel.config import NetworkConfig, ProjectConfig
from novel.runtime import make_provider

_PROXY_VARS = ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
               "ALL_PROXY", "all_proxy"]
_ALL_VARS = _PROXY_VARS + ["NO_PROXY", "no_proxy"]


@pytest.fixture(autouse=True)
def _clean_proxy_state(monkeypatch):
    for var in _ALL_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("novel.runtime._proxy_env_backup", {})
    monkeypatch.setattr("novel.runtime._applied_proxy_vars", set())


def _cfg(proxy: str | None = None, no_proxy: str | None = None) -> ProjectConfig:
    return ProjectConfig(network=NetworkConfig(proxy=proxy, no_proxy=no_proxy))


def test_live_mode_exports_proxy_env(monkeypatch):
    monkeypatch.setenv("NOVEL_LIVE", "1")
    make_provider(_cfg(proxy="http://127.0.0.1:7890"))
    for var in _PROXY_VARS:
        assert os.environ[var] == "http://127.0.0.1:7890"
    # no_proxy not configured -> untouched
    assert "NO_PROXY" not in os.environ and "no_proxy" not in os.environ


def test_live_mode_exports_no_proxy(monkeypatch):
    monkeypatch.setenv("NOVEL_LIVE", "1")
    make_provider(_cfg(proxy="http://p:1", no_proxy="localhost,.corp.cn"))
    assert os.environ["NO_PROXY"] == "localhost,.corp.cn"
    assert os.environ["no_proxy"] == "localhost,.corp.cn"


def test_project_without_network_restores_user_env(monkeypatch):
    """GUI 长进程里先后跑两个项目：无 network 配置的项目不得继承上个项目的代理，
    也不得清掉用户 shell 里自带的环境变量。"""
    monkeypatch.setenv("NOVEL_LIVE", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://user-env:1")
    monkeypatch.setenv("NO_PROXY", "localhost")

    make_provider(_cfg(proxy="http://cfg-a:7890"))
    assert os.environ["HTTPS_PROXY"] == "http://cfg-a:7890"

    make_provider(_cfg())  # project B: no network section
    assert os.environ["HTTPS_PROXY"] == "http://user-env:1"
    assert os.environ["NO_PROXY"] == "localhost"
    for var in _PROXY_VARS:
        if var != "HTTPS_PROXY":
            assert var not in os.environ


def test_switching_between_proxied_projects(monkeypatch):
    monkeypatch.setenv("NOVEL_LIVE", "1")
    make_provider(_cfg(proxy="http://a:1"))
    make_provider(_cfg(proxy="http://b:2"))
    assert os.environ["HTTP_PROXY"] == "http://b:2"


def test_demo_mode_never_touches_env(monkeypatch):
    monkeypatch.delenv("NOVEL_LIVE", raising=False)
    make_provider(_cfg(proxy="http://127.0.0.1:7890"))
    for var in _ALL_VARS:
        assert var not in os.environ
