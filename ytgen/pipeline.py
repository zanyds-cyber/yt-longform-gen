"""CLI·웹·앱이 함께 쓰는 단계 함수 (조사 → 주제 → 대본)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .common import log, read_json, slugify, write_json


def new_project(root: Path, name: str) -> Path:
    p = root / f"{datetime.now():%Y%m%d_%H%M}_{slugify(name)}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def do_research(cfg, out_root: Path, keyword, trending, days, duration, category) -> Path:
    from . import research
    res = research.run_research(None if trending else keyword, days=days, duration=duration, category=category)
    proj = new_project(out_root, keyword if not trending else f"trending_{category}")
    write_json(proj / "research.json", res)
    (proj / "research.md").write_text(research.report_md(res), encoding="utf-8")
    log(f"[research] → {proj / 'research.md'}")
    return proj


def do_topics(cfg, proj: Path, notes: str = "") -> dict:
    from . import script
    data = script.propose_topics(cfg, read_json(proj / "research.json"), 3, notes)
    write_json(proj / "topics.json", data)
    return data


def do_script(cfg, proj: Path, pick: int, minutes: int | None = None, notes: str = "") -> dict:
    from . import script
    topics = read_json(proj / "topics.json")["topics"]
    t = topics[pick - 1]
    res = read_json(proj / "research.json") if (proj / "research.json").exists() else None
    brief = script.topic_brief(t, res) + (("\n\n" + notes) if notes else "")
    data = script.generate(cfg, t["title"], minutes or t["minutes"], brief, out_path=proj / "script.json")
    data["picked_topic"] = t
    write_json(proj / "script.json", data)
    return data
