"""렌더링: 장면별 클립(켄번스 + 자막) → 이어붙이기 → 내레이션/BGM 합성.
부산물: subtitles.srt, description.txt(챕터 포함), thumbnail.jpg
"""
from __future__ import annotations

import math
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from . import images, tts
from .common import duration, fmt_ts, log, read_json, run, short_hash, write_json


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


def write_ass(cues: list[tuple[float, float, str]], path: Path, vc: dict, sc: dict) -> None:
    w, h = vc["width"], vc["height"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{sc.get('font', 'IPAGothic')},{sc.get('size', 62)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,{sc.get('outline', 4)},1,2,80,80,{sc.get('margin_bottom', 70)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{t}\n"
                   for a, b, t in cues)
    path.write_text(head + body, encoding="utf-8")


# ---------- 영상 ----------
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


def render_clip(img: Path, dur: float, ass: Path | None, out: Path, vc: dict, variant: int) -> None:
    w, h, fps = vc["width"], vc["height"], vc["fps"]
    frames = round(dur * fps)
    if vc.get("motion", "kenburns") == "kenburns":
        vf = kenburns_filter(variant, frames, w, h, fps)
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
    if ass:
        p = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",ass='{p}'"
    vf += ",format=yuv420p"
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(img),
         "-vf", vf, "-frames:v", str(frames), "-an",
         "-c:v", "libx264", "-preset", vc.get("preset", "veryfast"), "-crf", str(vc.get("crf", 20)),
         "-r", str(fps), "-video_track_timescale", "90000", str(out)])


def _silence(path: Path, sec: float) -> Path:
    if not path.exists():
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"anullsrc=r=48000:cl=mono", "-t", f"{sec:.3f}", str(path)])
    return path


def _concat_list(paths: list[Path], list_path: Path) -> Path:
    list_path.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in paths), encoding="utf-8")
    return list_path


# ---------- 썸네일 ----------
def make_thumbnail(script: dict, out: Path, cfg: dict, work: Path) -> None:
    prompt = script.get("thumbnail_image_prompt") or script["title"]
    bg = images.make_all([(prompt, "")], work / "images", 1280, 720, cfg["image"])[0]
    img = Image.open(bg).convert("RGB")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(img.width):  # 왼쪽을 어둡게 → 글자 가독성
        od.line([(x, 0), (x, img.height)], fill=(0, 0, 0, int(170 * max(0, 1 - x / (img.width * 0.75)))))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    text = script.get("thumbnail_text") or script["title"][:12]
    lines = [text] if len(text) <= 7 else [text[: math.ceil(len(text) / 2)], text[math.ceil(len(text) / 2):]]
    size = min(170, int(1100 / max(len(l) for l in lines)))
    font = images.find_font(size)
    d = ImageDraw.Draw(img)
    y = 360 - (len(lines) * size * 1.15) / 2
    for l in lines:
        d.text((60, y), l, font=font, fill=(255, 230, 0), stroke_width=max(6, size // 14), stroke_fill="black")
        y += size * 1.15
    img.save(out, quality=95)


# ---------- 메인 ----------
def build(project: Path, cfg: dict, only_thumbnail: bool = False) -> Path:
    script = read_json(project / "script.json")
    vc = {"width": 1920, "height": 1080, "fps": 30, **cfg.get("video", {})}
    sc = cfg.get("subtitle", {})
    tc = cfg.get("tts", {})
    work = project / "work"
    for d in ("audio", "images", "scenes", "clips"):
        (work / d).mkdir(parents=True, exist_ok=True)

    make_thumbnail(script, project / "thumbnail.jpg", cfg, work)
    log(f"[thumb] {project / 'thumbnail.jpg'}")
    if only_thumbnail:
        return project / "thumbnail.jpg"

    scenes = [(si, sec["heading"], sc_) for si, sec in enumerate(script["sections"]) for sc_ in sec["scenes"]]
    log(f"[build] {len(script['sections'])} chapters / {len(scenes)} scenes")

    # 1) 음성 (모든 문장 한 번에 병렬)
    per_scene = [tts.split_sentences(s["narration"]) for _, _, s in scenes]
    flat = [x for ss in per_scene for x in ss]
    flat_audio = dict(zip(flat, tts.synthesize_all(flat, work / "audio", tc)))

    # 2) 이미지
    img_paths = images.make_all([(s["image_prompt"], h) for _, h, s in scenes],
                                work / "images", vc["width"], vc["height"], cfg["image"])

    # 3) 장면별 오디오 + 자막 + 클립
    gap = float(vc.get("sentence_gap", 0.25))
    tail = float(vc.get("scene_tail", 0.6))
    fps = vc["fps"]
    gap_wav = _silence(work / f"gap_{gap}.wav", gap) if gap > 0 else None
    t0, srt, chapters, clips, scene_wavs, clip_jobs = 0.0, [], [], [], [], []
    last_section = -1
    max_chars = int(sc.get("max_chars", 24))
    for idx, ((si, heading, scene), sents, img) in enumerate(zip(scenes, per_scene, img_paths)):
        if si != last_section:
            chapters.append((t0, heading))
            last_section = si
        parts, cues, t = [], [], 0.0
        for k, s in enumerate(sents):
            wav, d = flat_audio[s]
            chunks = split_chunks(s, max_chars)
            total = sum(len(c) for c in chunks)
            ct = t
            for c in chunks:
                cd = d * len(c) / total
                cues.append((ct, ct + cd, wrap_lines(c, max_chars)))
                ct += cd
            parts.append(wav)
            t += d
            if gap_wav and k < len(sents) - 1:
                parts.append(gap_wav)
                t += gap
        scene_dur = math.ceil((t + tail) * fps) / fps  # 프레임 단위로 맞춰 싱크 누적 오차 제거
        key = short_hash([str(p) for p in parts], scene_dur)
        scene_wav = work / "scenes" / f"{key}.wav"
        if not scene_wav.exists():
            lst = _concat_list(parts, work / "scenes" / f"{key}.txt")
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-af", f"apad=whole_dur={scene_dur}", "-t", f"{scene_dur}", "-ar", "48000", "-ac", "1",
                 str(scene_wav)])
        scene_wavs.append(scene_wav)

        burn = sc.get("enabled", True) and sc.get("burn", True)
        variant = random.Random(idx).randint(0, 3)
        ckey = short_hash(str(img), scene_dur, cues if burn else None, vc, sc if burn else None, variant)
        clip = work / "clips" / f"{ckey}.mp4"
        if not clip.exists():
            ass = None
            if burn:
                ass = work / "clips" / f"{ckey}.ass"
                write_ass(cues, ass, vc, sc)
            clip_jobs.append((img, scene_dur, ass, clip, variant))
        clips.append(clip)
        srt += [(t0 + a, t0 + b, txt.replace("\\N", "\n")) for a, b, txt in cues]
        t0 += scene_dur

    if clip_jobs:
        log(f"[video] rendering {len(clip_jobs)} clips (total {fmt_ts(t0)})")
        done = 0

        def job(j):
            nonlocal done
            render_clip(j[0], j[1], j[2], j[3], vc, j[4])
            done += 1
            log(f"  [clip] {done}/{len(clip_jobs)}")

        with ThreadPoolExecutor(int(vc.get("workers", max(1, (os.cpu_count() or 2) // 2)))) as ex:
            list(ex.map(job, clip_jobs))

    # 4) 이어붙이기 + 오디오 합성
    log("[mux] concatenating…")
    narr = work / "narration.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(_concat_list(scene_wavs, work / "narration.txt")), "-c", "copy", str(narr)])
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

    # 5) SRT / 설명란
    (project / "subtitles.srt").write_text(
        "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(srt, 1)),
        encoding="utf-8")
    write_description(script, chapters, project / "description.txt")
    write_json(project / "timeline.json", {"duration": t0, "chapters": chapters})
    log(f"[done] {final}  ({fmt_ts(duration(final))})")
    return final


def _pick_bgm(path: str) -> Path | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_dir():
        files = [f for f in p.iterdir() if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
        return random.choice(files) if files else None
    return p if p.exists() else None


def write_description(script: dict, chapters: list, out: Path) -> None:
    lines = [script.get("description", "").strip(), ""]
    # YouTube 챕터 조건: 0:00 시작, 3개 이상, 각 10초 이상
    ok = len(chapters) >= 3 and all(b[0] - a[0] >= 10 for a, b in zip(chapters, chapters[1:]))
    if ok:
        lines += ["■ 目次"] + [f"{fmt_ts(t)} {h}" for t, h in chapters] + [""]
    tags = script.get("tags", [])
    if tags:
        lines.append(" ".join("#" + t.replace(" ", "") for t in tags[:3]))
    text = "\n".join(lines).strip() + "\n"
    meta = [f"【タイトル】{script['title']}"]
    if script.get("title_candidates"):
        meta += ["【タイトル候補】"] + [f"- {t}" for t in script["title_candidates"]]
    if tags:
        meta.append("【タグ】" + ", ".join(tags))
    out.write_text(text + "\n\n" + "=" * 30 + "\n" + "\n".join(meta) + "\n", encoding="utf-8")
