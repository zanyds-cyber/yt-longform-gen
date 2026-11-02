"""롱폼 대본에서 숏츠(9:16, 3분 이하) 하위 프로젝트를 만든다: <project>/shorts/<n>/"""
from __future__ import annotations

from pathlib import Path

from . import script as script_mod
from .common import log, read_json, write_json

VERTICAL = {
    "video": {"width": 1080, "height": 1920, "scene_tail": 0.3, "character_scale": 0.6},
    "subtitle": {"size": 72, "max_chars": 14, "margin_bottom": 600, "margin_lr": 60},
    "thumbnail": False,   # 숏츠는 API로 맞춤 썸네일을 지정할 수 없음
}


def make_shorts(project: Path, cfg: dict, count: int = 2, seconds: int = 50) -> list[Path]:
    long_script = read_json(project / "script.json")
    shorts = script_mod.shorts_from_script(cfg, long_script, count, seconds)
    out = []
    for i, s in enumerate(shorts, 1):
        d = project / "shorts" / str(i)
        d.mkdir(parents=True, exist_ok=True)
        title = s["title"] if "#shorts" in s["title"].lower() else f"{s['title']} #Shorts"
        write_json(d / "script.json", {
            "title": title, "title_candidates": [], "description": s["description"],
            "tags": long_script.get("tags", [])[:10] + ["Shorts"], "thumbnail_text": s["thumbnail_text"],
            "thumbnail_image_prompt": "", "parent": str(project),
            "sections": [{"heading": s["title"], "scenes": s["scenes"]}],
        })
        write_json(d / "config_override.json", VERTICAL)
        log(f"[shorts] {d}: {title}")
        out.append(d)
    return out
