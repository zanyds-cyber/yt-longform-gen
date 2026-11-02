"""YouTube 롱폼 영상 생성기 CLI.

  python -m ytgen script "テーマ" --minutes 20      # Claude로 대본(script.json) 생성
  python -m ytgen import 台本.txt --title "タイトル"  # 직접 쓴 대본 가져오기 (무료)
  python -m ytgen build output/<프로젝트>            # 음성·이미지·영상 생성
  python -m ytgen run "テーマ" --minutes 20          # script + build 한 번에
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import render, script
from .common import load_config, log, slugify, write_json


def new_project(root: Path, name: str) -> Path:
    p = root / f"{datetime.now():%Y%m%d_%H%M}_{slugify(name)}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ytgen", description="YouTube long-form video generator")
    ap.add_argument("-c", "--config", help="config.yaml path")
    ap.add_argument("-o", "--out", default="output", help="output root (default: ./output)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("script", "run"):
        s = sub.add_parser(name)
        s.add_argument("topic")
        s.add_argument("--minutes", type=int, default=15)
        s.add_argument("--notes", default="", help="대본에 반영할 추가 지시/자료")
        s.add_argument("--notes-file", help="참고 자료 텍스트 파일")

    s = sub.add_parser("import")
    s.add_argument("file")
    s.add_argument("--title", required=True)

    s = sub.add_parser("build")
    s.add_argument("project")
    s.add_argument("--thumbnail-only", action="store_true")

    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    out_root = Path(a.out)

    if a.cmd in ("script", "run"):
        notes = a.notes
        if a.notes_file:
            notes += "\n\n" + Path(a.notes_file).read_text(encoding="utf-8")
        proj = new_project(out_root, a.topic)
        path = proj / "script.json"
        data = script.generate(cfg, a.topic, a.minutes, notes, out_path=path)
        write_json(path, data)
        log(f"[script] saved → {path}")
        if a.cmd == "script":
            log(f"내용을 확인·수정한 뒤:  python -m ytgen build {proj}")
            return 0
        render.build(proj, cfg)
        return 0

    if a.cmd == "import":
        data = script.from_text(Path(a.file).read_text(encoding="utf-8"), a.title)
        proj = new_project(out_root, a.title)
        write_json(proj / "script.json", data)
        n = sum(len(s["scenes"]) for s in data["sections"])
        log(f"[import] {len(data['sections'])} chapters / {n} scenes → {proj / 'script.json'}")
        log(f"다음:  python -m ytgen build {proj}")
        return 0

    if a.cmd == "build":
        render.build(Path(a.project), cfg, only_thumbnail=a.thumbnail_only)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
