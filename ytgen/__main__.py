"""YouTube 자동 운영 파이프라인 CLI.

  python -m ytgen research "雑学 動物" --days 30 --duration medium   # 1. 조사 → 프로젝트 생성
  python -m ytgen research --trending --category education
  python -m ytgen topics output/<프로젝트>                          # 2. 주제 3개 제안
  python -m ytgen script output/<프로젝트> --pick 1                 #    선택한 주제로 대본
  python -m ytgen script-topic "テーマ" --minutes 15                 #    (조사 없이 바로 대본)
  python -m ytgen build output/<프로젝트>                           # 3~5. 소스·음성·영상
  python -m ytgen preview output/<프로젝트> 5                       #    장면 5만 미리보기
  python -m ytgen shorts output/<프로젝트> --count 2                #    숏츠 하위 프로젝트 생성
  python -m ytgen upload output/<프로젝트> --privacy private        # 6. 업로드
  python -m ytgen web                                               # 편집 화면 (http://127.0.0.1:8765)
  python -m ytgen voices                                            # VOICEVOX 화자 ID 목록
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .common import load_config, log, read_json, slugify, write_json


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ytgen", description="YouTube automation pipeline")
    ap.add_argument("-c", "--config", help="config.yaml path")
    ap.add_argument("-o", "--out", default="output", help="output root (default: ./output)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("research")
    s.add_argument("keyword", nargs="?")
    s.add_argument("--trending", action="store_true")
    s.add_argument("--category", default="all")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--duration", default="any", choices=["any", "short", "medium", "long"])

    s = sub.add_parser("topics"); s.add_argument("project"); s.add_argument("--notes", default="")

    s = sub.add_parser("script")
    s.add_argument("project"); s.add_argument("--pick", type=int, required=True)
    s.add_argument("--minutes", type=int); s.add_argument("--notes", default="")

    s = sub.add_parser("script-topic")
    s.add_argument("topic"); s.add_argument("--minutes", type=int, default=15); s.add_argument("--notes", default="")

    s = sub.add_parser("import"); s.add_argument("file"); s.add_argument("--title", required=True)

    s = sub.add_parser("build"); s.add_argument("project"); s.add_argument("--thumbnail-only", action="store_true")
    s = sub.add_parser("preview"); s.add_argument("project"); s.add_argument("scene", type=int)

    s = sub.add_parser("shorts")
    s.add_argument("project"); s.add_argument("--count", type=int, default=2)
    s.add_argument("--seconds", type=int, default=50); s.add_argument("--build", action="store_true")

    s = sub.add_parser("upload")
    s.add_argument("project"); s.add_argument("--privacy", choices=["private", "unlisted", "public"])
    s.add_argument("--publish-at", help="예약 공개 ISO8601, 예: 2026-11-10T19:00:00+09:00")

    s = sub.add_parser("web"); s.add_argument("--port", type=int, default=8765); s.add_argument("--host", default="127.0.0.1")
    sub.add_parser("voices")

    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    out_root = Path(a.out)

    if a.cmd == "research":
        if not a.keyword and not a.trending:
            ap.error("keyword 또는 --trending 이 필요합니다")
        proj = do_research(cfg, out_root, a.keyword, a.trending, a.days, a.duration, a.category)
        print((proj / "research.md").read_text(encoding="utf-8"))
        log(f"다음:  python -m ytgen topics {proj}")
    elif a.cmd == "topics":
        data = do_topics(cfg, Path(a.project), a.notes)
        print("\n■ 시장 분석\n" + data["insights"])
        for i, t in enumerate(data["topics"], 1):
            print(f"\n[{i}] {t['title']}  ({t['minutes']}분)\n  각도: {t['angle']}\n  근거: {t['why']}\n"
                  f"  훅: {t['hook']}\n  주의: {t['risk']}")
        log(f"\n다음:  python -m ytgen script {a.project} --pick 1")
    elif a.cmd == "script":
        do_script(cfg, Path(a.project), a.pick, a.minutes, a.notes)
        log(f"[script] 확인·수정 후:  python -m ytgen build {a.project}   (또는 web 편집 화면)")
    elif a.cmd == "script-topic":
        from . import script
        proj = new_project(out_root, a.topic)
        write_json(proj / "script.json", script.generate(cfg, a.topic, a.minutes, a.notes, out_path=proj / "script.json"))
        log(f"[script] → {proj / 'script.json'}")
    elif a.cmd == "import":
        from . import script
        data = script.from_text(Path(a.file).read_text(encoding="utf-8"), a.title)
        proj = new_project(out_root, a.title)
        write_json(proj / "script.json", data)
        log(f"[import] → {proj / 'script.json'}")
    elif a.cmd == "build":
        from . import render
        render.build(Path(a.project), cfg, only_thumbnail=a.thumbnail_only)
    elif a.cmd == "preview":
        from . import render
        render.preview_scene(Path(a.project), cfg, a.scene)
    elif a.cmd == "shorts":
        from . import render, shorts
        for d in shorts.make_shorts(Path(a.project), cfg, a.count, a.seconds):
            if a.build:
                render.build(d, cfg)
    elif a.cmd == "upload":
        from . import upload
        upload.upload(Path(a.project), cfg, a.privacy, a.publish_at)
    elif a.cmd == "web":
        from . import web
        web.serve(cfg, out_root, a.host, a.port)
    elif a.cmd == "voices":
        from . import tts
        for s in tts.voicevox_speakers(cfg.get("tts", {})):
            print(f"{s['id']:>4}  {s['name']} ({s['style']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
