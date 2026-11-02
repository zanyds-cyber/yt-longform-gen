"""대본 생성 (Claude API) 및 텍스트 파일 가져오기.

script.json 형식:
{
  "title": str, "title_candidates": [str], "description": str, "tags": [str],
  "thumbnail_text": str,
  "sections": [
    {"heading": str, "scenes": [{"narration": str, "image_prompt": str}]}
  ]
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import log

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
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "image_prompt": {"type": "string"},
                },
                "required": ["narration", "image_prompt"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

SYSTEM = """You are a professional scriptwriter for a Japanese long-form YouTube channel.
All viewer-facing text (titles, description, tags, narration, thumbnail text) must be natural, native Japanese.
Image prompts must be written in English, describing one concrete visual (subject, setting, composition, mood) with no text or logos in the image.

Channel style:
{style}

Principles for long-form retention:
- The first section opens with a strong hook within the first 30 seconds: a surprising fact, question, or stakes, then a promise of what the viewer will learn.
- Use open loops and smooth transitions between chapters so viewers keep watching.
- Prefer concrete examples, numbers, stories and comparisons over abstract statements.
- Narration is written for the ear: short-to-medium sentences, each ending with 。！？, no bullet points, no stage directions, no parentheses with readings, no emoji, no URLs.
- Only state facts you are confident are accurate; when uncertain, phrase it as a commonly held view rather than inventing specifics.
- The final section wraps up and invites the viewer to subscribe / comment in a natural way."""


def _client():
    import anthropic
    return anthropic.Anthropic()


def _call(cfg: dict, prompt: str, schema: dict) -> dict:
    c = cfg.get("claude", {})
    client = _client()
    with client.beta.messages.stream(
        model=c.get("model", "claude-opus-5-5"),
        max_tokens=64000,
        system=SYSTEM.format(style=c.get("channel_style", "")),
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


def generate(cfg: dict, topic: str, minutes: int, notes: str = "",
             out_path: Path | None = None) -> dict:
    cpm = cfg.get("claude", {}).get("chars_per_minute", 330)
    total_chars = minutes * cpm
    n_sections = max(4, min(12, round(minutes / 2.5)))

    log(f"[script] outline: {topic} ({minutes}min ≈ {total_chars} chars, ~{n_sections} chapters)")
    outline = _call(cfg, f"""Plan a {minutes}-minute Japanese YouTube video.

Topic: {topic}
{('Extra notes from the creator: ' + notes) if notes else ''}

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

Split the narration into scenes. Each scene is 2–4 sentences (about 80–200 characters) that share one visual,
with an English image_prompt for that visual. Vary the visuals between scenes.""",
            SECTION_SCHEMA)
        script["sections"].append({"heading": sec["heading"], "scenes": body["scenes"]})
        if out_path:  # 중간 저장
            out_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script


def from_text(text: str, title: str) -> dict:
    """무료 모드: 직접 쓴 텍스트 대본을 script.json 으로 변환.

    # 見出し        → 챕터(섹션)
    빈 줄로 구분    → 장면(scene)
    [img: prompt]   → 그 장면의 이미지 프롬프트 (선택)
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
        cur["scenes"].append({"narration": "".join(narr),
                              "image_prompt": prompt or cur["heading"]})
    return {"title": title, "title_candidates": [], "description": "", "tags": [],
            "thumbnail_text": title[:12], "thumbnail_image_prompt": title,
            "sections": [s for s in sections if s["scenes"]]}
