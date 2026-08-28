"""edge-tts 封装：预设音色表、参数校验、合成到文件（重试 + 原子替换）。

设计要点（spec §3）：接入层隔离在此模块，后续可替换云端 TTS；
demo 模式的静音 MP3 分支由 Job 层决定，不在此判断。
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Self

import edge_tts

TTS_VOICES: dict[str, str] = {
    "zh-CN-XiaoxiaoNeural": "晓晓（女 · 温暖通用）",
    "zh-CN-XiaoyiNeural": "晓伊（女 · 活泼）",
    "zh-CN-XiaochenNeural": "晓辰（女 · 知性）",
    "zh-CN-XiaomengNeural": "晓梦（女 · 温柔）",
    "zh-CN-XiaoqiuNeural": "晓秋（女 · 文艺）",
    "zh-CN-YunxiNeural": "云希（男 · 阳光）",
    "zh-CN-YunjianNeural": "云健（男 · 浑厚）",
    "zh-CN-YunyangNeural": "云扬（男 · 新闻）",
    "zh-CN-YunyeNeural": "云野（男 · 成熟）",
    "zh-CN-YunxiaNeural": "云夏（男 · 少年）",
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

_RATE_RE = re.compile(r"^[+-]\d+%$")
_VOLUME_RE = re.compile(r"^[+-]\d+%$")
_PITCH_RE = re.compile(r"^[+-]\d+Hz$")

# a few-KB valid silent MPEG frame; demo-mode artifact so the whole flow
# (job → file → audio player) is testable offline
SILENT_MP3 = (
    b"\xff\xfb\x90\x00" + b"\x00" * 413
) * 8  # 8 tiny frames ≈ 3.3 KB

_MAX_RETRIES = 2


class _AudioSink(str):
    """Path string passed to ``Communicate.save``.

    Real edge-tts only needs a filesystem path (it opens the file itself), while
    test doubles write via ``.write()``; support both by buffering ``write()``
    calls and flushing them to disk if any were made.
    """

    _buf: bytearray

    def __new__(cls, path: Path) -> Self:
        sink = super().__new__(cls, str(path))
        sink._buf = bytearray()
        return sink

    def write(self, data: bytes) -> None:
        self._buf += data

    def flush_to_disk(self) -> None:
        if self._buf:
            Path(self).write_bytes(bytes(self._buf))


def validate_tts_params(voice: str, rate: str, volume: str, pitch: str) -> None:
    if voice not in TTS_VOICES:
        raise ValueError(f"未知音色: {voice}")
    if not _RATE_RE.match(rate):
        raise ValueError(f"语速格式非法（应为 +20% 这样的百分比）: {rate}")
    if not _VOLUME_RE.match(volume):
        raise ValueError(f"音量格式非法（应为 -10% 这样的百分比）: {volume}")
    if not _PITCH_RE.match(pitch):
        raise ValueError(f"音调格式非法（应为 +5Hz 这样的赫兹值）: {pitch}")


def synth_to_file(text: str, voice: str, rate: str, volume: str, pitch: str,
                  out_path: Path, proxy: str | None = None) -> None:
    """Synthesize `text` to `out_path` (atomic replace); retry twice on failure.

    Runs in a Job thread: drive the asyncio API with asyncio.run per attempt.
    `proxy` (from project config `network.proxy`) routes the Microsoft endpoint
    through a local VPN/proxy; None = direct connection.
    """
    validate_tts_params(voice, rate, volume, pitch)
    last_err: Exception | None = None
    for _attempt in range(_MAX_RETRIES + 1):
        try:
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            sink = _AudioSink(tmp)

            async def _run(sink: _AudioSink) -> None:
                comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume,
                                            pitch=pitch, proxy=proxy)
                await comm.save(sink)

            asyncio.run(_run(sink))
            sink.flush_to_disk()
            os.replace(tmp, out_path)
            return
        except Exception as e:  # noqa: BLE001 - retried/surfaced to the job
            last_err = e
            time.sleep(2)
    assert last_err is not None
    raise last_err
