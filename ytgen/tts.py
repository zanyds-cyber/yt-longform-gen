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
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .common import duration, log, run, short_hash

SUB_BREAK = "⏎"   # 편집기에서 Enter로 넣는 '자막 나누기' 표시 (음성에는 영향 없음)
SENT_RE = re.compile(r"[^。！？!?\n]+[。！？!?」』）]*")
SPEAKER_RE = re.compile(r"^\s*([^\s：:「」{}]{1,12})\s*(\{[^{}]*\})?\s*[：:]\s*(.+)$")
OPTS_ONLY_RE = re.compile(r"^\s*(\{[^{}]*\})\s*(.+)$")   # 내레이션 모드: "{v:3}本文"

# 줄별 옵션 (편집기 '선택한 대사' 패널): 목소리·속도·높이·억양, 자막 크기·색·굵기·테두리
OPT_TYPES = {"v": int, "speed": float, "pitch": float, "into": float,
             "size": int, "color": str, "bold": int, "outline": int}


def parse_opts(raw: str | None) -> dict:
    out = {}
    for part in (raw or "").strip("{}").split(","):
        if ":" not in part:
            continue
        k, v = (x.strip() for x in part.split(":", 1))
        if k in OPT_TYPES and v != "":
            try:
                out[k] = OPT_TYPES[k](v)
            except ValueError:
                pass
    return out


def format_opts(opts: dict | None) -> str:
    items = [f"{k}:{opts[k]}" for k in OPT_TYPES if opts and opts.get(k) not in (None, "")]
    return "{" + ",".join(items) + "}" if items else ""


def split_line(line: str, names: set[str]) -> tuple[str | None, dict, str]:
    """'이름{옵션}：대사' / '{옵션}대사' / '대사' → (이름|None, 옵션, 대사)."""
    m = SPEAKER_RE.match(line)
    if names and m and m.group(1) in names:
        return m.group(1), parse_opts(m.group(2)), m.group(3)
    m = OPTS_ONLY_RE.match(line)
    if m:
        return None, parse_opts(m.group(1)), m.group(2)
    return None, {}, line


@dataclass
class Utt:
    text: str          # 읽을 문장
    speaker: str       # 캐릭터 이름 ('' = 내레이터)
    opts: dict = field(default_factory=dict)   # 줄별 목소리/자막 옵션


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
        spk, opts, line = split_line(line, names if dialogue else set())
        if spk:
            cur = spk
        out += [Utt(s, cur if dialogue else "", opts) for s in split_sentences(line)]
    return out


def voice_for(speaker: str, cfg: dict) -> dict:
    """화자 이름 → 엔진별 음성 설정."""
    for c in cfg.get("characters") or []:
        if c["name"] == speaker:
            return c
    return {"speaker": cfg.get("voicevox_speaker", 3), "edge_voice": cfg.get("edge_voice")}


def voice_with_opts(v: dict, opts: dict) -> dict:
    """줄별 옵션으로 목소리(VOICEVOX 스타일 ID)·속도·높이·억양 덮어쓰기."""
    if not opts:
        return v
    v = dict(v)
    if "v" in opts:
        v["speaker"] = opts["v"]
    vv = dict(v.get("voicevox") or {})
    for k, name in (("speed", "speedScale"), ("pitch", "pitchScale"), ("into", "intonationScale")):
        if k in opts:
            vv[name] = opts[k]
    if vv:
        v["voicevox"] = vv
    return v


def used_voice_ids(utts: list[Utt], cfg: dict) -> set[int]:
    return {int(voice_with_opts(voice_for(u.speaker, cfg), u.opts).get("speaker", 3)) for u in utts}


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
        v = voice_with_opts(voice_for(u.speaker, cfg), u.opts)
        spoken = u.text.replace(SUB_BREAK, "")
        key = (engine, spoken, v.get("speaker"), v.get("edge_voice"), v.get("voicevox"),
               cfg.get("voicevox"), cfg.get("edge_rate"))
        jobs.append((spoken, audio_dir / f"{short_hash(*key)}.wav", v))
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


def credits(cfg: dict, used_speakers: set[str], used_ids: set[int] | None = None) -> list[str]:
    """VOICEVOX 이용 규약: 영상 설명란에 'VOICEVOX:캐릭터명' 크레딧 표기가 필요.
    실제로 사용한 스타일 ID로 캐릭터를 찾는다 (편집기에서 목소리를 바꿔도 정확하게)."""
    if cfg.get("engine") != "voicevox":
        return []
    names: list[str] = []
    if used_ids:
        try:
            by_id = {s["id"]: s["name"] for s in voicevox_speakers(cfg)}
            names = [by_id[i] for i in sorted(used_ids) if i in by_id]
        except Exception:
            names = []
    if not names:
        chars = cfg.get("characters") or []
        if cfg.get("mode") == "dialogue" and chars:
            names = [c.get("credit") or c["name"] for c in chars if c["name"] in used_speakers]
        elif cfg.get("voicevox_credit"):
            names = [cfg["voicevox_credit"]]
    return [f"VOICEVOX:{n}" for n in dict.fromkeys(names)]
