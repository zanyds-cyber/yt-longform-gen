"""2단계: 주제 제안 + 대본 생성 (Claude API), 텍스트 대본 가져오기, 숏츠 대본.

script.json 형식:
{
  "title", "title_candidates", "description", "tags", "thumbnail_text", "thumbnail_image_prompt",
  "sections": [
    {"heading": str,
     "scenes": [{"narration": str, "image_prompt": str, "stock_query": str, "media": [..]?}]}
  ]
}
대화 모드에서 narration 은 "四国めたん：…\nずんだもん：…" 처럼 한 줄에 한 화자.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import log

SCENE_ITEM = {
    "type": "object",
    "properties": {
        "narration": {"type": "string"},
        "image_prompt": {"type": "string"},
        "stock_query": {"type": "string"},
    },
    "required": ["narration", "image_prompt", "stock_query"],
    "additionalProperties": False,
}

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "title_candidates": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "thumbnail_image_prompt": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "target_chars": {"type": "integer"},
                },
                "required": ["heading", "summary", "key_points", "target_chars"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "title_candidates", "description", "tags",
                 "thumbnail_text", "thumbnail_image_prompt", "sections"],
    "additionalProperties": False,
}

SECTION_SCHEMA = {
    "type": "object",
    "properties": {"scenes": {"type": "array", "items": SCENE_ITEM}},
    "required": ["scenes"],
    "additionalProperties": False,
}

TOPICS_SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "angle": {"type": "string"},
                    "why": {"type": "string"},
                    "hook": {"type": "string"},
                    "outline": {"type": "array", "items": {"type": "string"}},
                    "minutes": {"type": "integer"},
                    "reference_ids": {"type": "array", "items": {"type": "string"}},
                    "risk": {"type": "string"},
                },
                "required": ["title", "angle", "why", "hook", "outline", "minutes",
                             "reference_ids", "risk"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["insights", "topics"],
    "additionalProperties": False,
}

SHORTS_SCHEMA = {
    "type": "object",
    "properties": {
        "shorts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "thumbnail_text": {"type": "string"},
                    "scenes": {"type": "array", "items": SCENE_ITEM},
                },
                "required": ["title", "description", "thumbnail_text", "scenes"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["shorts"],
    "additionalProperties": False,
}

SYSTEM = """You are a professional scriptwriter and strategist for a Japanese YouTube channel.
All viewer-facing text (titles, description, tags, narration, thumbnail text) must be natural, native Japanese.
image_prompt: English, one concrete visual (subject, setting, composition, mood), no text or logos.
stock_query: 2–4 plain English keywords to search a stock-footage site for that scene (e.g. "office worker night", "tokyo street rain").

Channel style:
{style}

{voice}

Principles for retention:
- Open with a strong hook within the first 30 seconds (surprising fact, question, or stakes), then promise what the viewer will learn.
- Use open loops and smooth transitions between chapters.
- Prefer concrete examples, numbers, stories and comparisons over abstract statements.
- Written for the ear: short-to-medium sentences ending with 。！？, no bullet points, no stage directions, no emoji, no URLs.
- Only state facts you are confident are accurate; when uncertain, phrase it as a commonly held view rather than inventing specifics such as exact figures, names or dates.
- Never copy titles or scripts of reference videos; offer a distinct angle and original structure.
- The final section wraps up and invites the viewer to subscribe / comment naturally."""


def voice_instructions(cfg: dict) -> str:
    t = cfg.get("tts", {})
    chars = t.get("characters") or []
    if t.get("mode") == "dialogue" and len(chars) >= 2:
        desc = "\n".join(f"- {c['name']}: {c.get('role', '')}" for c in chars)
        names = "、".join(c["name"] for c in chars)
        return f"""FORMAT: two-character dialogue (掛け合い解説) between {names}.
{desc}
Write every narration as dialogue lines, ONE line per utterance, each starting with the exact speaker name and a full-width colon, e.g.
{chars[0]['name']}：…
{chars[1]['name']}：…
Keep each character's speech style consistent. Let them react, ask, and joke a little, but keep the information dense."""
    return "FORMAT: single narrator voice-over (no speaker names in the narration)."


def _client():
    import anthropic
    return anthropic.Anthropic()


def _call(cfg: dict, prompt: str, schema: dict) -> dict:
    c = cfg.get("claude", {})
    client = _client()
    with client.beta.messages.stream(
        model=c.get("model", "claude-opus-5-5"),
        max_tokens=64000,
        system=SYSTEM.format(style=c.get("channel_style", ""), voice=voice_instructions(cfg)),
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": c.get("effort", "high"),
                       "format": {"type": "json_schema", "schema": schema}},
        # 정책 판단으로 거절될 경우 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined this request: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Output hit max_tokens; try fewer minutes per section.")
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text)


# ---------- 주제 제안 ----------
def research_digest(res: dict, top: int = 25) -> str:
    rows = []
    for v in res["videos"][:top]:
        out = f"{v['outlier']}x subs" if v.get("outlier") is not None else "subs hidden"
        rows.append(f"[{v['id']}] {v['title']} | {v['channel']} | {v['views']:,} views | {out} | "
                    f"{v['views_per_day']:,}/day | {v['duration']} | {v['published']}")
    comments = []
    for v in res["videos"]:
        if v.get("top_comments"):
            comments.append(f"Comments on [{v['id']}]:\n" + "\n".join("- " + c for c in v["top_comments"][:10]))
    return (f"Research ({'keyword: ' + res['keyword'] if res.get('keyword') else 'JP trending ' + str(res.get('category'))}, "
            f"last {res.get('days')} days)\nCommon tags: {', '.join(res.get('common_tags', [])[:20])}\n"
            f"Median duration: {res['stats']['median_duration_min']} min\n\nVideos (sorted by outlier score):\n"
            + "\n".join(rows) + "\n\n" + "\n\n".join(comments))


def propose_topics(cfg: dict, res: dict, n: int = 3, notes: str = "") -> dict:
    log(f"[topics] proposing {n} topics from {len(res['videos'])} videos")
    return _call(cfg, f"""Below is YouTube research data from the Japanese market.
{research_digest(res)}

{('Creator notes: ' + notes) if notes else ''}

Analyse what is working (themes, title patterns, length, emotional triggers, gaps the audience asks for in comments)
and propose exactly {n} distinct video topics for my channel that ride this demand with an original angle.
For each topic:
- title: Japanese working title (≤ 40 chars)
- angle: how it differs from the existing videos (Korean)
- why: data-backed reason it should perform, citing the reference videos (Korean)
- hook: the first 1–2 lines of narration (Japanese)
- outline: 5–8 chapter ideas (Japanese)
- minutes: recommended length (based on what performs)
- reference_ids: the video ids that inspired it
- risk: copyright / factual / policy cautions (Korean)
insights: 3–6 lines summarising the market patterns (Korean).""", TOPICS_SCHEMA)


# ---------- 대본 ----------
def generate(cfg: dict, topic: str, minutes: int, notes: str = "",
             out_path: Path | None = None) -> dict:
    cpm = cfg.get("claude", {}).get("chars_per_minute", 330)
    total_chars = minutes * cpm
    n_sections = max(4, min(12, round(minutes / 2.5)))

    notes_block = f"Extra notes / research from the creator:\n{notes}" if notes else ""
    log(f"[script] outline: {topic} ({minutes}min ≈ {total_chars} chars, ~{n_sections} chapters)")
    outline = _call(cfg, f"""Plan a {minutes}-minute Japanese YouTube video.

Topic: {topic}
{notes_block}

Return:
- title: click-worthy but honest Japanese title (≤ 40 chars)
- title_candidates: 3 alternative titles
- description: 2–4 short paragraphs for the YouTube description (no chapter list; it is added automatically)
- tags: 10–15 search tags
- thumbnail_text: very short punchy Japanese text for the thumbnail (≤ 12 chars)
- thumbnail_image_prompt: English prompt for an eye-catching thumbnail background
- sections: about {n_sections} chapters. The first is the hook/intro, the last is the wrap-up.
  Each has a short Japanese heading (used as a YouTube chapter name, ≤ 20 chars), a summary,
  key_points, and target_chars so that the total is about {total_chars} Japanese characters.""",
        OUTLINE_SCHEMA)

    script = {k: outline[k] for k in ("title", "title_candidates", "description", "tags",
                                      "thumbnail_text", "thumbnail_image_prompt")}
    script["topic"] = topic
    script["sections"] = []
    outline_text = "\n".join(
        f"{i+1}. {s['heading']} — {s['summary']}" for i, s in enumerate(outline["sections"]))

    for i, sec in enumerate(outline["sections"]):
        log(f"[script] section {i+1}/{len(outline['sections'])}: {sec['heading']}")
        prev = ""
        if script["sections"]:
            last = script["sections"][-1]["scenes"][-2:]
            prev = "\n".join(s["narration"] for s in last)
        context = (
            f"The previous chapter ended with:\n{prev}\nContinue naturally from there (do not repeat it)."
            if prev else
            "This is the opening of the video: start with the hook immediately (no self-introduction first)."
        )
        body = _call(cfg, f"""Video title: {script['title']}
Full chapter outline:
{outline_text}

Write the full narration for chapter {i+1}: 「{sec['heading']}」
Summary: {sec['summary']}
Key points: {'; '.join(sec['key_points'])}
Length: about {sec['target_chars']} Japanese characters in total.
{context}

Split the narration into scenes. Each scene is 2–5 sentences/lines (about 80–220 characters) sharing one visual,
with an English image_prompt and stock_query for that visual. Vary the visuals between scenes.""",
            SECTION_SCHEMA)
        script["sections"].append({"heading": sec["heading"], "scenes": body["scenes"]})
        if out_path:  # 중간 저장
            out_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script


def topic_brief(topic: dict, res: dict | None) -> str:
    """선택한 주제 + 참고 영상 정보를 대본 생성용 메모로."""
    lines = [f"Angle: {topic['angle']}", f"Hook idea: {topic['hook']}",
             "Planned chapters:\n" + "\n".join("- " + o for o in topic["outline"])]
    if res:
        refs = [v for v in res["videos"] if v["id"] in topic.get("reference_ids", [])]
        if refs:
            lines.append("Reference videos (for demand only — do not copy):\n" +
                         "\n".join(f"- {v['title']} ({v['views']:,} views, {v['duration']})" for v in refs))
            for v in refs:
                if v.get("top_comments"):
                    lines.append("Viewer comments on a reference video (what the audience cares about):\n" +
                                 "\n".join("- " + c for c in v["top_comments"][:8]))
    return "\n\n".join(lines)


# ---------- 숏츠 ----------
def shorts_from_script(cfg: dict, script: dict, count: int = 2, seconds: int = 50) -> list[dict]:
    log(f"[shorts] {count} shorts from 「{script['title']}」")
    full = "\n\n".join(f"## {s['heading']}\n" + "\n".join(sc["narration"] for sc in s["scenes"])
                       for s in script["sections"])
    cpm = cfg.get("claude", {}).get("chars_per_minute", 330)
    out = _call(cfg, f"""Here is the script of my long-form video 「{script['title']}」:

{full}

Create {count} YouTube Shorts (vertical, about {seconds} seconds ≈ {int(seconds / 60 * cpm)} Japanese characters each)
from the most surprising / emotional parts. Each must stand alone, open with a hook in the first line,
deliver one satisfying point, and end by teasing the full video (本編). 3–5 scenes each.
title ≤ 40 chars including #Shorts at the end; description 1–2 lines.""", SHORTS_SCHEMA)
    return out["shorts"]


# ---------- 텍스트 대본 가져오기 ----------
def from_text(text: str, title: str) -> dict:
    """직접 쓴 텍스트 대본 → script.json

    # 見出し        → 챕터
    빈 줄로 구분    → 장면
    [img: prompt]   → 이미지 프롬프트 / 스톡 검색어 (선택)
    대화 모드는 줄마다  ずんだもん：…  형식
    """
    sections: list[dict] = []
    cur = None
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        narr, prompt = [], ""
        for l in lines:
            if l.startswith("#"):
                cur = {"heading": l.lstrip("#").strip(), "scenes": []}
                sections.append(cur)
            elif m := re.match(r"^\[img:\s*(.+?)\]$", l, re.I):
                prompt = m.group(1)
            else:
                narr.append(l)
        if not narr:
            continue
        if cur is None:
            cur = {"heading": "オープニング", "scenes": []}
            sections.append(cur)
        cur["scenes"].append({"narration": "\n".join(narr),
                              "image_prompt": prompt or cur["heading"],
                              "stock_query": prompt or cur["heading"]})
    return {"title": title, "title_candidates": [], "description": "", "tags": [],
            "thumbnail_text": title[:12], "thumbnail_image_prompt": title,
            "sections": [s for s in sections if s["scenes"]]}
