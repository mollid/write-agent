"""TTS 模块测试：参数校验、demo 静音 MP3、synth_to_file 重试与原子写（不联网）。"""
import pytest

from novel.tts import (
    DEFAULT_VOICE,
    SILENT_MP3,
    TTS_VOICES,
    synth_to_file,
    validate_tts_params,
)


def test_validate_accepts_defaults_and_bounds():
    validate_tts_params(DEFAULT_VOICE, "+0%", "+0%", "+0Hz")
    validate_tts_params(next(iter(TTS_VOICES)), "-50%", "+100%", "-50Hz")
    validate_tts_params(DEFAULT_VOICE, "+100%", "-50%", "+50Hz")


@pytest.mark.parametrize("voice,rate,volume,pitch", [
    ("zh-CN-NotAVoice", "+0%", "+0%", "+0Hz"),
    (DEFAULT_VOICE, "1.5x", "+0%", "+0Hz"),
    (DEFAULT_VOICE, "+0%", "loud", "+0Hz"),
    (DEFAULT_VOICE, "+0%", "+0%", "+10"),
    ("", "+0%", "+0%", "+0Hz"),
])
def test_validate_rejects_bad_params(voice, rate, volume, pitch):
    with pytest.raises(ValueError):
        validate_tts_params(voice, rate, volume, pitch)


def test_silent_mp3_is_valid_frame():
    assert SILENT_MP3[:3] == b"ID3" or SILENT_MP3[0] == 0xFF


def test_synth_to_file_passes_params_and_writes_atomically(tmp_path, monkeypatch):
    recorded = {}
    calls = {"n": 0}

    class _FakeCommunicate:
        def __init__(self, text, voice, *, rate, volume, pitch, **_kw):
            recorded.update(text=text, voice=voice, rate=rate, volume=volume, pitch=pitch)

        async def save(self, out):
            calls["n"] += 1
            out.write(b"\xff\xfbID3-fake-mp3-bytes")

    monkeypatch.setattr("novel.tts.edge_tts", type("M", (), {"Communicate": _FakeCommunicate}))
    out = tmp_path / "003.mp3"
    synth_to_file("正文", "zh-CN-YunxiNeural", "+20%", "-10%", "+5Hz", out)
    assert out.read_bytes() == b"\xff\xfbID3-fake-mp3-bytes"
    assert recorded == {"text": "正文", "voice": "zh-CN-YunxiNeural",
                        "rate": "+20%", "volume": "-10%", "pitch": "+5Hz"}
    assert not (tmp_path / "003.mp3.tmp").exists()


def test_synth_to_file_retries_then_raises(tmp_path, monkeypatch):
    attempts = {"n": 0}

    class _Broken:
        def __init__(self, *a, **k): pass

        async def save(self, out):
            attempts["n"] += 1
            raise OSError("network down")

    monkeypatch.setattr("novel.tts.edge_tts", type("M", (), {"Communicate": _Broken}))
    with pytest.raises(OSError):
        synth_to_file("x", DEFAULT_VOICE, "+0%", "+0%", "+0Hz", tmp_path / "a.mp3")
    assert attempts["n"] == 3  # 1 + 2 retries
