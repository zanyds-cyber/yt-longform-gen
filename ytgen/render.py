"""5단계: 렌더링.

장면마다: 음성(문장 단위) → 화면 소스(스톡 영상/이미지) → 캐릭터 립 없는 스탠딩 이미지 + 자막 → 클립
→ 전체 이어붙이기 → 내레이션/BGM 합성.
부산물: subtitles.srt, description.txt(챕터·크레딧), thumbnail.jpg, timeline.json
"""
from __future__ import annotations

import math
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import images, media, tts
from .common import duration, fmt_ts, log, project_config, read_json, run, short_hash, write_json


# ---------- 자막 ----------
def split_chunks(sentence: str, max_chars: int) -> list[str]:
    """한 문장을 화면에 표시할 덩어리(각 최대 2줄)로 나눈다. 구두점 위치를 우선."""
    limit = max_chars * 2
    parts, rest = [], sentence
    while len(rest) > limit:
        target = len(rest) / math.ceil(len(rest) / limit)
        cands = [m.end() for m in re.finditer(r"[、，,」』）]", rest) if 4 < m.end() <= limit]
        cut = min(cands, key=lambda c: abs(c - target), default=None)
        if cut is None or abs(cut - target) > target * 0.4:
            cut = min(limit, round(target))
        parts.append(rest[:cut])
        rest = rest[cut:]
    return parts + ([rest] if rest else [])


def wrap_lines(chunk: str, max_chars: int) -> str:
    if len(chunk) <= max_chars:
        return chunk
    mid = len(chunk) / 2
    cands = [m.end() for m in re.finditer(r"[、，,」』）]", chunk)
             if m.end() <= max_chars + 1 and len(chunk) - m.end() <= max_chars + 1]
    cut = min(cands, key=lambda c: abs(c - mid), default=math.ceil(mid))
    return chunk[:cut] + "\\N" + chunk[cut:]


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _style_name(speaker: str) -> str:
    return "S_" + short_hash(speaker) if speaker else "Default"


def effective_chars(sc: dict, vc: dict) -> int:
    """한 줄 글자 수: 설정값과 '화면 폭(좌우 여백 제외) ÷ 글자 크기' 중 작은 값 (잘림 방지)."""
    mc = int(sc.get("max_chars", 24))
    avail = vc["width"] - 2 * int(sc.get("margin_lr", 80))
    fit = int(avail / (int(sc.get("size", 62)) * 1.02))
    return max(6, min(mc, fit))


def ass_color(c, alpha: int = 0, default: str = "&H00FFFFFF") -> str:
    """'#RRGGBB'(설정 화면) 또는 '&HAABBGGRR'(ASS) → ASS 색."""
    if not c:
        return default
    c = str(c).strip()
    if c.upper().startswith("&H"):
        return c.upper()
    h = c.lstrip("#")
    if len(h) != 6:
        return default
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def subtitle_font(sc: dict) -> str:
    font = sc.get("font") or "IPAGothic"
    if font == "IPAGothic" and sys.platform in ("darwin", "win32"):
        font = "Hiragino Sans" if sys.platform == "darwin" else "Meiryo"
    return font


def write_ass(cues: list, path: Path, vc: dict, sc: dict, chars: list[dict]) -> None:
    w, h = vc["width"], vc["height"]
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")
    margin_lr = int(sc.get("margin_lr", 80))
    font = subtitle_font(sc)
    size = int(sc.get("size", 62))
    bold = -1 if sc.get("bold", True) else 0
    if sc.get("box"):
        # 배경 박스: BorderStyle 3 — 박스 색은 OutlineColour, Outline 값은 박스 여백
        alpha = round((100 - int(sc.get("box_opacity", 60))) / 100 * 255)
        border, edge, shadow = 3, max(6, size // 5), 0
        outline_col = ass_color(sc.get("box_color", "#000000"), alpha, "&H80000000")
    else:
        border, edge, shadow = 1, int(sc.get("outline", 4)), int(sc.get("shadow", 1))
        outline_col = ass_color(sc.get("outline_color", "#000000"), 0, "&H00000000")
    fixed = sc.get("color_mode") == "fixed"
    default_fill = ass_color(sc.get("color", "#FFFFFF"))

    def style(name, color):
        fill = default_fill if fixed else ass_color(color, 0, default_fill)
        return (f"Style: {name},{font},{size},{fill},&H00FFFFFF,{outline_col},&H80000000,"
                f"{bold},0,0,0,100,100,{sc.get('spacing', 1)},0,{border},{edge},{shadow},2,"
                f"{margin_lr},{margin_lr},{sc.get('margin_bottom', 70)},1")

    styles = [style("Default", sc.get("color", "#FFFFFF"))]
    styles += [style(_style_name(c["name"]), c.get("color", "&H00FFFFFF")) for c in chars]
    body = "".join(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{_style_name(spk)},,0,0,0,,{t}\n"
                   for a, b, t, spk in cues)
    path.write_text(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n"
                    f"[V4+ Styles]\n{fmt}\n" + "\n".join(styles) +
                    "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                    + body, encoding="utf-8")


# ---------- 클립 ----------
def kenburns_filter(variant: int, frames: int, w: int, h: int, fps: int) -> str:
    W, H = w * 2, h * 2  # 업스케일해 줌 떨림 감소
    N = max(frames, 1)
    z, x, y = {
        0: (f"1+0.12*on/{N}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        1: (f"1.12-0.12*on/{N}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        2: ("1.12", f"(iw-iw/zoom)*on/{N}", "ih/2-(ih/zoom/2)"),
        3: ("1.12", f"(iw-iw/zoom)*(1-on/{N})", "ih/2-(ih/zoom/2)"),
    }[variant % 4]
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={fps}")


def _esc(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_clip(project: Path, items: list[dict], dur: float, ass: Path | None, out: Path,
                vc: dict, variant: int, chars: list[dict], audio: Path | None = None) -> None:
    w, h, fps = vc["width"], vc["height"], vc["fps"]
    frames = round(dur * fps)
    args, filters, n = [], [], 0
    if items[0]["type"] == "image":
        args += ["-loop", "1", "-framerate", str(fps), "-i", str(project / items[0]["path"])]
        if vc.get("motion", "kenburns") == "kenburns":
            filters.append(f"[0:v]{kenburns_filter(variant, frames, w, h, fps)},setsar=1[base]")
        else:
            filters.append(f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1[base]")
        n = 1
    else:
        seg = dur / len(items)
        for i, m in enumerate(items):
            args += ["-stream_loop", "-1", "-i", str(project / m["path"])]
            filters.append(f"[{i}:v]trim=duration={seg + 0.1:.3f},setpts=PTS-STARTPTS,"
                           f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1[v{i}]")
        n = len(items)
        if n > 1:
            filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[base]")
        else:
            filters[-1] = filters[-1].replace("[v0]", "[base]")
    cur = "base"
    for c in chars:  # 캐릭터 스탠딩 이미지
        img = c.get("image")
        if not img or not Path(img).exists():
            continue
        args += ["-loop", "1", "-i", str(img)]
        ch = int(h * float(c.get("height", 0.42)) * float(vc.get("character_scale", 1.0)))
        x = "W-w-20" if c.get("position", "right") == "right" else "20"
        filters.append(f"[{n}:v]scale=-1:{ch}[c{n}]")
        filters.append(f"[{cur}][c{n}]overlay=x={x}:y=H-h:shortest=1[o{n}]")
        cur = f"o{n}"
        n += 1
    last = f"[{cur}]"
    if ass:
        filters.append(f"{last}ass='{_esc(ass)}'[s]")
        last = "[s]"
    filters.append(f"{last}format=yuv420p[vout]")
    cmd = ["ffmpeg", "-y", "-v", "error", *args]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
    if audio:
        cmd += ["-map", f"{n}:a", "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-an"]
    cmd += ["-frames:v", str(frames), "-c:v", "libx264", "-preset", vc.get("preset", "veryfast"),
            "-crf", str(vc.get("crf", 20)), "-r", str(fps), "-video_track_timescale", "90000", str(out)]
    run(cmd)


def _silence(path: Path, sec: float) -> Path:
    if not path.exists():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             "anullsrc=r=48000:cl=mono", "-t", f"{sec:.3f}", str(path)])
    return path


def _concat_list(paths: list[Path], list_path: Path) -> Path:
    list_path.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), encoding="utf-8")
    return list_path


# ---------- 계획 ----------
@dataclass
class ScenePlan:
    index: int
    section: int
    heading: str
    scene: dict
    cues: list = field(default_factory=list)   # (start, end, text, speaker)
    wav: Path | None = None
    dur: float = 0.0
    speakers: set = field(default_factory=set)


def _settings(cfg: dict):
    vc = {"width": 1920, "height": 1080, "fps": 30, **cfg.get("video", {})}
    return vc, cfg.get("subtitle", {}), cfg.get("tts", {})


def _chars(tc: dict) -> list[dict]:
    return tc.get("characters") or [] if tc.get("mode") == "dialogue" else []


def plan_audio(project: Path, cfg: dict, script: dict, only: int | None = None) -> list[ScenePlan]:
    """음성 합성 + 장면 길이/자막 큐 계산."""
    vc, sc, tc = _settings(cfg)
    work = project / "work"
    plans, idx = [], 0
    for si, sec in enumerate(script["sections"]):
        for scene in sec["scenes"]:
            if only is None or only == idx:
                plans.append(ScenePlan(idx, si, sec["heading"], scene))
            idx += 1
    utts = [tts.parse_narration(p.scene["narration"], tc) for p in plans]
    flat = [u for us in utts for u in us]
    audio = tts.synthesize_all(flat, work / "audio", tc)
    it = iter(audio)
    gap = float(vc.get("sentence_gap", 0.25))
    tail = float(vc.get("scene_tail", 0.6))
    fps = vc["fps"]
    max_chars = effective_chars(sc, vc)
    gap_wav = _silence(work / f"gap_{gap}.wav", gap) if gap > 0 else None
    (work / "scenes").mkdir(parents=True, exist_ok=True)
    for p, us in zip(plans, utts):
        parts, t = [], 0.0
        for k, u in enumerate(us):
            wav, d = next(it)
            chunks = [c for part in u.text.split(tts.SUB_BREAK) if part.strip()
                      for c in split_chunks(part.strip(), max_chars)]
            total = sum(len(c) for c in chunks) or 1
            ct = t
            for c in chunks:
                cd = d * len(c) / total
                p.cues.append((ct, ct + cd, wrap_lines(c, max_chars), u.speaker))
                ct += cd
            p.speakers.add(u.speaker)
            parts.append(wav)
            t += d
            if gap_wav and k < len(us) - 1:
                parts.append(gap_wav)
                t += gap
        if not parts:
            parts, t = [_silence(work / "silence_1.wav", 1.0)], 1.0
        p.dur = math.ceil((t + tail) * fps) / fps  # 프레임 단위로 맞춰 싱크 누적 오차 제거
        key = short_hash([str(x) for x in parts], p.dur)
        p.wav = work / "scenes" / f"{key}.wav"
        if not p.wav.exists():
            lst = _concat_list(parts, work / "scenes" / f"{key}.txt")
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-af", f"apad=whole_dur={p.dur}", "-t", f"{p.dur}", "-ar", "48000", "-ac", "1", str(p.wav)])
    return plans


def _scene_media(project: Path, plans: list[ScenePlan], cfg: dict, script: dict) -> None:
    vc, _, _ = _settings(cfg)
    used = {f"{m['source']}:{m.get('id')}" for sec in script["sections"] for s in sec["scenes"]
            for m in s.get("media") or [] if m.get("id")}
    for p in plans:
        media.resolve_scene(project, p.scene, p.dur, vc["width"], vc["height"], cfg, used, p.heading)


def _clip_for(project: Path, p: ScenePlan, cfg: dict) -> tuple[Path, tuple | None]:
    vc, sc, tc = _settings(cfg)
    burn = sc.get("enabled", True) and sc.get("burn", True)
    chars = _chars(tc)
    variant = random.Random(p.index).randint(0, 3)
    items = p.scene["media"]
    ckey = short_hash([m["path"] for m in items], p.dur, p.cues if burn else None, vc,
                      sc if burn else None, variant, [(c.get("image"), c.get("position"), c.get("height"),
                                                       c.get("color")) for c in chars])
    clip = project / "work" / "clips" / f"{ckey}.mp4"
    if clip.exists():
        return clip, None
    ass = None
    if burn:
        ass = project / "work" / "clips" / f"{ckey}.ass"
        write_ass(p.cues, ass, vc, sc, chars)
    return clip, (items, p.dur, ass, clip, variant)


# ---------- 썸네일 ----------
def make_thumbnail(script: dict, out: Path, cfg: dict, work: Path) -> None:
    prompt = script.get("thumbnail_image_prompt") or script["title"]
    bg = images.make_all([(prompt, "")], work / "images", 1280, 720, cfg["image"])[0]
    img = Image.open(bg).convert("RGB")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(img.width):  # 왼쪽을 어둡게 → 글자 가독성
        od.line([(x, 0), (x, img.height)], fill=(0, 0, 0, int(170 * max(0, 1 - x / (img.width * 0.75)))))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    # 캐릭터가 있으면 오른쪽에 크게
    for c in _chars(cfg.get("tts", {}))[:1] or []:
        if c.get("image") and Path(c["image"]).exists():
            ch = Image.open(c["image"]).convert("RGBA")
            s = 680 / ch.height
            ch = ch.resize((int(ch.width * s), 680))
            img.alpha_composite(ch, (img.width - ch.width - 10, img.height - ch.height))
    img = img.convert("RGB")
    text = script.get("thumbnail_text") or script["title"][:12]
    lines = [text] if len(text) <= 7 else [text[: math.ceil(len(text) / 2)], text[math.ceil(len(text) / 2):]]
    size = min(170, int(1000 / max(len(l) for l in lines)))
    font = images.find_font(size)
    d = ImageDraw.Draw(img)
    y = 360 - (len(lines) * size * 1.15) / 2
    for l in lines:
        d.text((50, y), l, font=font, fill=(255, 230, 0), stroke_width=max(6, size // 14), stroke_fill="black")
        y += size * 1.15
    img.save(out, quality=95)


# ---------- 메인 ----------
def build(project: Path, cfg: dict, only_thumbnail: bool = False) -> Path:
    cfg = project_config(cfg, project)
    script = read_json(project / "script.json")
    vc, sc, tc = _settings(cfg)
    work = project / "work"
    for d in ("audio", "images", "scenes", "clips", "stock"):
        (work / d).mkdir(parents=True, exist_ok=True)

    if cfg.get("thumbnail", True):
        make_thumbnail(script, project / "thumbnail.jpg", cfg, work)
        log(f"[thumb] {project / 'thumbnail.jpg'}")
    if only_thumbnail:
        return project / "thumbnail.jpg"

    n_scenes = sum(len(s["scenes"]) for s in script["sections"])
    log(f"[build] {len(script['sections'])} chapters / {n_scenes} scenes")
    plans = plan_audio(project, cfg, script)
    _scene_media(project, plans, cfg, script)
    write_json(project / "script.json", script)  # 선택된 소스 기록

    clips, jobs, srt, chapters, t0, speakers = [], [], [], [], 0.0, set()
    last_section = -1
    for p in plans:
        if p.section != last_section:
            chapters.append((t0, p.heading))
            last_section = p.section
        clip, job = _clip_for(project, p, cfg)
        clips.append(clip)
        if job:
            jobs.append(job)
        srt += [(t0 + a, t0 + b, txt.replace("\\N", "\n")) for a, b, txt, _ in p.cues]
        speakers |= p.speakers
        t0 += p.dur

    if jobs:
        log(f"[video] rendering {len(jobs)} clips (total {fmt_ts(t0)})")
        done = 0
        chars = _chars(tc)

        def job(j):
            nonlocal done
            render_clip(project, j[0], j[1], j[2], j[3], vc, j[4], chars)
            done += 1
            log(f"  [clip] {done}/{len(jobs)}")

        with ThreadPoolExecutor(int(vc.get("workers", max(1, (os.cpu_count() or 2) // 2)))) as ex:
            list(ex.map(job, jobs))

    log("[mux] concatenating…")
    narr = work / "narration.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(_concat_list([p.wav for p in plans], work / "narration.txt")), "-c", "copy", str(narr)])
    video_only = work / "video_only.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(_concat_list(clips, work / "clips.txt")), "-c", "copy", str(video_only)])

    final = project / "final.mp4"
    bgm = _pick_bgm(cfg.get("bgm", {}).get("path", ""))
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video_only), "-i", str(narr)]
    if bgm:
        vol = cfg["bgm"].get("volume", 0.1)
        cmd += ["-stream_loop", "-1", "-i", str(bgm), "-filter_complex",
                f"[2:a]volume={vol},aformat=sample_rates=48000:channel_layouts=stereo[b];"
                f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[n];"
                f"[n][b]amix=inputs=2:duration=first:normalize=0,"
                f"afade=t=out:st={max(0, t0 - 3):.2f}:d=3[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a", "-ac", "2"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{t0:.3f}", str(final)]
    run(cmd)

    (project / "subtitles.srt").write_text(
        "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(srt, 1)),
        encoding="utf-8")
    credit_lines = tts.credits(tc, speakers) + media_credits(script)
    write_description(script, chapters, project / "description.txt", credit_lines, cfg)
    write_json(project / "timeline.json", {"duration": t0, "chapters": chapters, "credits": credit_lines})
    log(f"[done] {final}  ({fmt_ts(duration(final))})")
    return final


def preview_scene(project: Path, cfg: dict, index: int) -> Path:
    """한 장면만 음성 포함 미리보기 mp4 로 렌더링 (편집 화면용)."""
    cfg = project_config(cfg, project)
    script = read_json(project / "script.json")
    vc, sc, tc = _settings(cfg)
    for d in ("audio", "images", "scenes", "clips", "stock", "preview"):
        (project / "work" / d).mkdir(parents=True, exist_ok=True)
    plans = plan_audio(project, cfg, script, only=index)
    if not plans:
        raise IndexError(index)
    _scene_media(project, plans, cfg, script)
    write_json(project / "script.json", script)
    p = plans[0]
    clip, job = _clip_for(project, p, cfg)
    if job:
        render_clip(project, job[0], job[1], job[2], job[3], vc, job[4], _chars(tc))
    out = project / "work" / "preview" / f"scene_{index:03d}.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-i", str(p.wav), "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-shortest", str(out)])
    log(f"[preview] scene {index} → {out}")
    return out


def media_credits(script: dict) -> list[str]:
    """설명란 출처: Pexels/Pixabay 는 한 줄, CC·퍼블릭 도메인 소재는 항목별(제목/작성자/라이선스/링크)."""
    stock, items, seen = set(), [], set()
    for sec in script["sections"]:
        for s in sec["scenes"]:
            for m in s.get("media") or []:
                if m.get("source") in ("pexels", "pixabay"):
                    stock.add(m["source"].capitalize())
                elif m.get("source") in media.LICENSED:
                    key = (m["source"], m.get("id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    name = {"wikimedia": "Wikimedia Commons", "archive": "Internet Archive", "nasa": "NASA"}[m["source"]]
                    parts = [m.get("title") or name, m.get("credit") or name, m.get("license") or "", m.get("page") or ""]
                    items.append("・" + " / ".join(p for p in parts if p))
    lines = [f"動画素材: {', '.join(sorted(stock))}"] if stock else []
    if items:
        lines += ["映像素材（クリエイティブ・コモンズ／パブリックドメイン）:"] + items
    return lines


def _pick_bgm(path: str) -> Path | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_dir():
        files = [f for f in p.iterdir() if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
        return random.choice(files) if files else None
    return p if p.exists() else None


def write_description(script: dict, chapters: list, out: Path, credits: list[str], cfg: dict) -> None:
    lines = [script.get("description", "").strip(), ""]
    # YouTube 챕터 조건: 0:00 시작, 3개 이상, 각 10초 이상
    ok = len(chapters) >= 3 and all(b[0] - a[0] >= 10 for a, b in zip(chapters, chapters[1:]))
    if ok:
        lines += ["■ 目次"] + [f"{fmt_ts(t)} {h}" for t, h in chapters] + [""]
    if credits:
        lines += ["■ クレジット"] + credits + [""]
    extra = cfg.get("upload", {}).get("description_footer", "").strip()
    if extra:
        lines += [extra, ""]
    tags = script.get("tags", [])
    if tags:
        lines.append(" ".join("#" + t.replace(" ", "") for t in tags[:3]))
    out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
