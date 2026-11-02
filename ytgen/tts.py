"""4단계: TTS. 문장 단위로 음성을 만들어 정확한 자막 타이밍을 얻는다.

엔진
- voicevox : 무료·로컬. ずんだもん/四国めたん 등 캐릭터 음성. 대화(掛け合い) 모드 지원 (기본)
- edge     : 무료·클라우드. Microsoft Edge 음성
- dummy    : 테스트용 무음
"""
from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import requests

from .common import duration, log, run, short_hash

SENT_RE = re.compile(r"[^。！？!?\n]+[。！？!?」』）]*")
SPEAKER_RE = re.compile(r"^\s*([^\s：:「」]{1,12})\s*[：:]\s*(.+)$")


@dataclass
class Utt:
    text: str          # 읽을 문장
    speaker: str       # 캐릭터 이름 ('' = 내레이터)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_RE.findall(text) if s.strip()]


def parse_narration(text: str, cfg: dict) -> list[Utt]:
    """대화 모드면 '이름：대사' 줄을 화자별로 나누고, 각 줄을 문장 단위로 분할."""
    names = {c["name"] for c in cfg.get("characters") or []}
    dialogue = cfg.get("mode") == "dialogue" and names
    out, cur = [], (next(iter(names)) if dialogue else "")
    if dialogue:
        cur = (cfg["characters"][0]["name"])
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if dialogue and (m := SPEAKER_RE.match(line)) and m.group(1) in names:
            cur, line = m.group(1), m.group(2)
        out += [Utt(s, cur if dialogue else "") for s in split_sentences(line)]
    return out


def voice_for(speaker: str, cfg: dict) -> dict:
    """화자 이름 → 엔진별 음성 설정."""
    for c in cfg.get("characters") or []:
        if c["name"] == speaker:
            return c
    return {"speaker": cfg.get("voicevox_speaker", 3), "edge_voice": cfg.get("edge_voice")}


def _to_wav(src: Path, dst: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "48000", "-ac", "1", str(dst)])


def _edge(text: str, out: Path, cfg: dict, voice: dict) -> None:
    import edge_tts

    async def go():
        tmp = out.with_suffix(".mp3")
        await edge_tts.Communicate(text, voice.get("edge_voice") or cfg.get("edge_voice", "ja-JP-NanamiNeural"),
                                   rate=cfg.get("edge_rate", "+0%")).save(str(tmp))
        return tmp

    for attempt in range(3):
        try:
            tmp = asyncio.run(go())
            _to_wav(tmp, out)
            tmp.unlink(missing_ok=True)
            return
        except Exception as e:
            if attempt == 2:
                raise
            log(f"  [tts] retry ({e})")


def _voicevox(text: str, out: Path, cfg: dict, voice: dict) -> None:
    base = cfg.get("voicevox_url", "http://127.0.0.1:50021")
    spk = voice.get("speaker", cfg.get("voicevox_speaker", 3))
    try:
        q = requests.post(f"{base}/audio_query", params={"text": text, "speaker": spk}, timeout=60)
    except requests.ConnectionError:
        raise RuntimeError(f"VOICEVOX 엔진에 연결할 수 없습니다 ({base}). VOICEVOX 앱을 먼저 실행하세요.")
    q.raise_for_status()
    query = q.json()
    vv = {**cfg.get("voicevox", {}), **voice.get("voicevox", {})}
    for k in ("speedScale", "pitchScale", "intonationScale", "volumeScale",
              "prePhonemeLength", "postPhonemeLength"):
        if k in vv:
            query[k] = vv[k]
    s = requests.post(f"{base}/synthesis", params={"speaker": spk}, json=query, timeout=300)
    s.raise_for_status()
    tmp = out.with_suffix(".raw.wav")
    tmp.write_bytes(s.content)
    _to_wav(tmp, out)
    tmp.unlink(missing_ok=True)


def _dummy(text: str, out: Path, cfg: dict, voice: dict) -> None:
    d = max(0.8, len(text) * 0.16)
    freq = 180 + (hash(str(voice.get("speaker"))) % 5) * 40
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:sample_rate=48000:duration={d}", "-af", "volume=0.05",
         "-ac", "1", str(out)])


ENGINES = {"edge": _edge, "voicevox": _voicevox, "dummy": _dummy}


def synthesize_all(utts: list[Utt], audio_dir: Path, cfg: dict) -> list[tuple[Path, float]]:
    """각 발화 → (wav 경로, 길이). 텍스트·음성 설정 해시로 캐시."""
    engine = cfg.get("engine", "voicevox")
    fn = ENGINES[engine]
    audio_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for u in utts:
        v = voice_for(u.speaker, cfg)
        key = (engine, u.text, v.get("speaker"), v.get("edge_voice"), v.get("voicevox"),
               cfg.get("voicevox"), cfg.get("edge_rate"))
        jobs.append((u.text, audio_dir / f"{short_hash(*key)}.wav", v))
    todo = [j for j in jobs if not j[1].exists()]
    if todo:
        log(f"[tts] {engine}: {len(todo)} sentences")
        done = 0

        def job(j):
            nonlocal done
            fn(j[0], j[1], cfg, j[2])
            done += 1
            if done % 20 == 0 or done == len(todo):
                log(f"  [tts] {done}/{len(todo)}")

        with ThreadPoolExecutor(cfg.get("concurrency", 2 if engine == "voicevox" else 4)) as ex:
            list(ex.map(job, todo))
    return [(p, duration(p)) for _, p, _ in jobs]


# ---------- VOICEVOX 보조 ----------
def voicevox_speakers(cfg: dict) -> list[dict]:
    base = cfg.get("voicevox_url", "http://127.0.0.1:50021")
    r = requests.get(f"{base}/speakers", timeout=10)
    r.raise_for_status()
    return [{"id": st["id"], "name": sp["name"], "style": st["name"]}
            for sp in r.json() for st in sp["styles"]]


def credits(cfg: dict, used_speakers: set[str]) -> list[str]:
    """VOICEVOX 이용 규약: 영상 설명란에 'VOICEVOX:캐릭터명' 크레딧 표기가 필요."""
    if cfg.get("engine") != "voicevox":
        return []
    names = []
    chars = cfg.get("characters") or []
    if cfg.get("mode") == "dialogue" and chars:
        names = [c.get("credit") or c["name"] for c in chars if c["name"] in used_speakers]
    else:
        name = cfg.get("voicevox_credit")
        if not name:
            try:
                sid = cfg.get("voicevox_speaker", 3)
                name = next(s["name"] for s in voicevox_speakers(cfg) if s["id"] == sid)
            except Exception:
                name = None
        names = [name] if name else []
    return [f"VOICEVOX:{n}" for n in dict.fromkeys(names)]
