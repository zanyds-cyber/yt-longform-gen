"""TTS: 문장 단위로 음성을 만들어 정확한 자막 타이밍을 얻는다."""
from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .common import duration, log, run, short_hash

SENT_RE = re.compile(r"[^。！？!?\n]+[。！？!?」』）]*")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_RE.findall(text) if s.strip()]


def _to_wav(src: Path, dst: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "48000", "-ac", "1", str(dst)])


def _edge(text: str, out: Path, cfg: dict) -> None:
    import edge_tts

    async def go():
        tmp = out.with_suffix(".mp3")
        await edge_tts.Communicate(text, cfg.get("edge_voice", "ja-JP-NanamiNeural"),
                                   rate=cfg.get("edge_rate", "+0%")).save(str(tmp))
        return tmp

    for attempt in range(3):
        try:
            tmp = asyncio.run(go())
            _to_wav(tmp, out)
            tmp.unlink(missing_ok=True)
            return
        except Exception as e:  # 네트워크 오류 재시도
            if attempt == 2:
                raise
            log(f"  [tts] retry ({e})")


def _voicevox(text: str, out: Path, cfg: dict) -> None:
    base = cfg.get("voicevox_url", "http://127.0.0.1:50021")
    spk = cfg.get("voicevox_speaker", 3)
    q = requests.post(f"{base}/audio_query", params={"text": text, "speaker": spk}, timeout=60)
    q.raise_for_status()
    s = requests.post(f"{base}/synthesis", params={"speaker": spk}, json=q.json(), timeout=300)
    s.raise_for_status()
    tmp = out.with_suffix(".raw.wav")
    tmp.write_bytes(s.content)
    _to_wav(tmp, out)
    tmp.unlink(missing_ok=True)


def _dummy(text: str, out: Path, cfg: dict) -> None:
    """테스트용: 글자 수에 비례한 길이의 낮은 톤."""
    d = max(0.8, len(text) * 0.16)
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"sine=frequency=220:sample_rate=48000:duration={d}", "-af", "volume=0.05",
         "-ac", "1", str(out)])


ENGINES = {"edge": _edge, "voicevox": _voicevox, "dummy": _dummy}


def synthesize_all(sentences: list[str], audio_dir: Path, cfg: dict) -> list[tuple[Path, float]]:
    """각 문장 → (wav 경로, 길이). 이미 있으면 재사용."""
    engine = cfg.get("engine", "edge")
    fn = ENGINES[engine]
    key = {k: v for k, v in cfg.items() if k != "concurrency"}
    audio_dir.mkdir(parents=True, exist_ok=True)
    paths = [audio_dir / f"{short_hash(s, key)}.wav" for s in sentences]
    todo = [(s, p) for s, p in zip(sentences, paths) if not p.exists()]
    if todo:
        log(f"[tts] {engine}: {len(todo)} sentences")
        done = 0

        def job(sp):
            nonlocal done
            fn(sp[0], sp[1], cfg)
            done += 1
            if done % 20 == 0 or done == len(todo):
                log(f"  [tts] {done}/{len(todo)}")

        with ThreadPoolExecutor(cfg.get("concurrency", 4)) as ex:
            list(ex.map(job, todo))
    return [(p, duration(p)) for p in paths]
