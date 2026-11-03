"""브루식 편집기(/edit)와 설정 화면(/settings)의 라우트."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import abort, jsonify, request, send_file

from . import editor_ui, media as media_mod, setup_tools, tts as tts_mod
from .common import (data_dir, load_config, read_json, save_env, save_settings, short_hash,
                     write_json)

KEYS = ["YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "OPENAI_API_KEY"]


def ass_to_css(c: str | None) -> str:
    c = (c or "").upper().replace("&H", "").rjust(8, "0")
    try:
        bb, gg, rr = c[2:4], c[4:6], c[6:8]
        return f"#{rr}{gg}{bb}"
    except Exception:
        return "#ffffff"


def css_to_ass(c: str) -> str:
    c = c.lstrip("#")
    return f"&H00{c[4:6]}{c[2:4]}{c[0:2]}".upper() if len(c) == 6 else "&H00FFFFFF"


def register(app, cfg, out_root: Path, config_path, *, proj, rel, start, scene_at, ok):
    def reload_cfg():
        new = load_config(config_path)
        cfg.clear()
        cfg.update(new)

    def tc() -> dict:
        return cfg.get("tts", {})

    def names() -> list[str]:
        t = tc()
        return [c["name"] for c in t.get("characters") or []] if t.get("mode") == "dialogue" else []

    def parse_lines(narr: str) -> list[dict]:
        ns, out = names(), []
        for line in narr.splitlines():
            line = line.strip()
            if not line:
                continue
            m = tts_mod.SPEAKER_RE.match(line)
            if ns and m and m.group(1) in ns:
                out.append({"speaker": m.group(1), "text": m.group(2)})
            else:
                out.append({"speaker": out[-1]["speaker"] if out else (ns[0] if ns else ""), "text": line})
        return out

    def join_lines(lines: list[dict]) -> str:
        ns = names()
        def clean(t: str) -> str:  # 편집기의 줄바꿈 = 자막 나누기
            parts = [p.strip() for p in t.replace("\r", "").replace(tts_mod.SUB_BREAK, "\n").split("\n")]
            return tts_mod.SUB_BREAK.join(p for p in parts if p)
        return "\n".join((f"{x['speaker']}：{clean(x['text'])}" if ns and x.get("speaker") in ns else clean(x["text"]))
                         for x in lines if clean(x.get("text", "")))

    # ---------- 편집기 ----------
    @app.get("/edit")
    def edit_page():
        p = proj(request.args.get("name"))
        if not (p / "script.json").exists():
            abort(404)
        return editor_ui.editor_page(rel(p))

    @app.get("/api/doc")
    def doc():
        p = proj(request.args.get("name"))
        sc = read_json(p / "script.json")
        name = rel(p)
        chars = [{"name": c["name"], "color": ass_to_css(c.get("color")),
                  "image": f"/charimg/{i}" if c.get("image") and Path(c["image"]).exists() else "",
                  "position": c.get("position", "right")}
                 for i, c in enumerate(tc().get("characters") or [])] if names() else []
        chapters, idx = [], 0
        for sec in sc["sections"]:
            scenes = []
            for scene in sec["scenes"]:
                m = (scene.get("media") or [None])[0]
                mm = None
                if m and (p / m["path"]).exists():
                    mm = {"type": m["type"], "source": m.get("source", ""),
                          "url": f"/f?name={quote(name)}&path={quote(m['path'])}"}
                scenes.append({"index": idx, "lines": parse_lines(scene["narration"]),
                               "stock_query": scene.get("stock_query", ""), "image_prompt": scene.get("image_prompt", ""),
                               "media": mm, "n_media": len(scene.get("media") or [])})
                idx += 1
            chapters.append({"heading": sec["heading"], "scenes": scenes})
        final = p / "final.mp4"
        vc = cfg.get("video", {})
        return jsonify({"name": name, "title": sc["title"], "chapters": chapters, "characters": chars,
                        "subtitle": subtitle_style(), "width": vc.get("width", 1920), "height": vc.get("height", 1080),
                        "break_mark": tts_mod.SUB_BREAK,
                        "dialogue": bool(names()), "gap": vc.get("sentence_gap", 0.2),
                        "portrait": vc.get("height", 1080) > vc.get("width", 1920),
                        "final": f"/f?name={quote(name)}&path=final.mp4&v={int(final.stat().st_mtime)}" if final.exists() else None})

    @app.post("/api/scene_lines")
    def scene_lines():
        b = request.get_json()
        p = proj(b.get("project"))
        sc = read_json(p / "script.json")
        _, _, scene = scene_at(sc, int(b["index"]))
        scene["narration"] = join_lines(b.get("lines", [])) or "（セリフ）"
        if "stock_query" in b and b["stock_query"] != scene.get("stock_query"):
            scene["stock_query"] = b["stock_query"]
        write_json(p / "script.json", sc)
        return ok()

    STYLE_DEFAULTS = {"font": "", "size": 62, "bold": True, "outline": 5, "outline_color": "#000000",
                      "color_mode": "speaker", "color": "#FFFFFF", "margin_bottom": 60, "margin_lr": 420,
                      "max_chars": 24, "box": False, "box_color": "#000000", "box_opacity": 60, "shadow": 1}

    def subtitle_style() -> dict:
        from .render import subtitle_font
        sub = cfg.get("subtitle", {})
        st = {k: sub.get(k, v) for k, v in STYLE_DEFAULTS.items()}
        st["font"] = subtitle_font(sub)
        st["color"] = st["color"] if str(st["color"]).startswith("#") else ass_to_css(st["color"])
        return st

    @app.post("/api/subtitle_style")
    def subtitle_style_save():
        b = request.get_json() or {}
        if b.get("reset"):
            vals = dict(STYLE_DEFAULTS)
            vals.pop("font")
        else:
            vals = {}
            for k, d in STYLE_DEFAULTS.items():
                if k not in b:
                    continue
                v = b[k]
                if isinstance(d, bool):
                    v = bool(v)
                elif isinstance(d, int):
                    v = int(float(v))
                else:
                    v = str(v).strip()
                vals[k] = v
        save_settings({"subtitle": vals})
        reload_cfg()
        return ok(subtitle=subtitle_style())

    @app.post("/api/heading")
    def heading():
        b = request.get_json()
        p = proj(b.get("project"))
        sc = read_json(p / "script.json")
        sc["sections"][int(b["section"])]["heading"] = b["heading"].strip() or "…"
        write_json(p / "script.json", sc)
        return ok()

    @app.get("/api/line_audio")
    def line_audio():
        """대사 한 줄의 음성(wav). 문장 단위 캐시를 렌더링과 공유한다."""
        p = proj(request.args.get("name"))
        spk, text = request.args.get("speaker", ""), request.args.get("text", "").strip()
        if not text:
            abort(400)
        t = tc()
        sents = tts_mod.split_sentences(text) or [text]
        utts = [tts_mod.Utt(s, spk if names() else "") for s in sents]
        res = tts_mod.synthesize_all(utts, p / "work" / "audio", t)
        if len(res) == 1:
            return send_file(res[0][0], mimetype="audio/wav", conditional=True)
        from .render import _concat_list, _silence
        gap = float(cfg.get("video", {}).get("sentence_gap", 0.2))
        out = p / "work" / "lines" / f"{short_hash([str(a) for a, _ in res], gap)}.wav"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            g = _silence(p / "work" / f"gap_{gap}.wav", gap)
            parts = [x for a, _ in res for x in (a, g)][:-1]
            from .common import run
            run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", str(_concat_list(parts, out.with_suffix(".txt"))), "-c", "copy", str(out)])
        return send_file(out, mimetype="audio/wav", conditional=True)

    @app.get("/api/stock_search")
    def stock_search():
        q = request.args.get("q", "").strip()
        portrait = request.args.get("portrait") == "1"
        items, errors = [], []
        for n in cfg.get("media", {}).get("sources", ["pexels", "pixabay"]):
            try:
                items += media_mod.SOURCES[n](q, portrait, 24)
            except Exception as e:
                errors.append(f"{n}: {str(e)[:120]}")
        missing = [k for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY") if not os.environ.get(k)]
        return jsonify({"items": items, "errors": errors, "missing_keys": missing})

    @app.post("/api/set_stock")
    def set_stock():
        b = request.get_json()
        p = proj(b.get("project"))
        it = b["item"]
        host = (urlparse(str(it.get("url", ""))).hostname or "").lower()
        if it.get("source") not in media_mod.SOURCES or not host.endswith(("pexels.com", "pixabay.com", "vimeo.com", "vimeocdn.com")):
            abort(400)
        dst = p / "work" / "stock" / f"{it['source']}_{int(it['id'])}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        media_mod._download(it["url"], dst)
        sc = read_json(p / "script.json")
        _, _, scene = scene_at(sc, int(b["index"]))
        entry = {"type": "video", "path": str(dst.relative_to(p)), "source": it["source"], "id": str(it["id"]),
                 "credit": it.get("credit", "")}
        scene["media"] = ([*(scene.get("media") or [])] if b.get("mode") == "add" else []) + [entry]
        write_json(p / "script.json", sc)
        return ok()

    @app.post("/api/auto_media")
    def auto_media():
        b = request.get_json()
        p = proj(b.get("project"))
        idx = int(b["index"])
        sc = read_json(p / "script.json")
        _, _, scene = scene_at(sc, idx)
        if b.get("replace"):
            media_mod.replace(scene)
        vc = {"width": 1920, "height": 1080, **cfg.get("video", {})}
        est = max(4.0, len(scene["narration"]) * 0.15)
        used = {f"{m['source']}:{m.get('id')}" for sec in sc["sections"] for s in sec["scenes"]
                for m in s.get("media") or [] if m.get("id")}
        media_mod.resolve_scene(p, scene, est, vc["width"], vc["height"], cfg, used, scene.get("stock_query", ""))
        write_json(p / "script.json", sc)
        return ok()

    @app.post("/api/scene_add")
    def scene_add():
        b = request.get_json()
        p = proj(b.get("project"))
        sc = read_json(p / "script.json")
        sec, j, scene = scene_at(sc, int(b["index"]))
        ns = names()
        first = f"{ns[0]}：" if ns else ""
        sec["scenes"].insert(j + 1, {"narration": first + "（ここにセリフ）", "image_prompt": scene.get("image_prompt", ""),
                                     "stock_query": scene.get("stock_query", "")})
        write_json(p / "script.json", sc)
        return ok()

    @app.post("/api/scene_delete")
    def scene_delete():
        b = request.get_json()
        p = proj(b.get("project"))
        sc = read_json(p / "script.json")
        if sum(len(s["scenes"]) for s in sc["sections"]) <= 1:
            raise RuntimeError("마지막 장면은 삭제할 수 없습니다")
        sec, j, _ = scene_at(sc, int(b["index"]))
        sec["scenes"].pop(j)
        sc["sections"] = [s for s in sc["sections"] if s["scenes"]]
        write_json(p / "script.json", sc)
        return ok()

    @app.get("/charimg/<int:i>")
    def charimg(i):
        cs = tc().get("characters") or []
        if i >= len(cs) or not cs[i].get("image") or not Path(cs[i]["image"]).exists():
            abort(404)
        return send_file(cs[i]["image"])

    # ---------- 설정 ----------
    @app.get("/settings")
    def settings_page():
        return editor_ui.settings_page()

    @app.get("/api/settings")
    def settings_get():
        reload_cfg()
        t = tc()
        speakers, vv = [], setup_tools.voicevox_version(t)
        if vv:
            try:
                speakers = tts_mod.voicevox_speakers(t)
            except Exception:
                pass
        return jsonify({
            "keys": {k: bool(os.environ.get(k)) for k in KEYS},
            "ffmpeg": setup_tools.ffmpeg_status(),
            "voicevox": {"version": vv, "url": t.get("voicevox_url", "http://127.0.0.1:50021"),
                         "path": t.get("voicevox_path", ""), "speakers": speakers},
            "tts": {"engine": t.get("engine", "voicevox"), "mode": t.get("mode", "dialogue"),
                    "voicevox_speaker": t.get("voicevox_speaker", 3),
                    "speed": (t.get("voicevox") or {}).get("speedScale", 1.0),
                    "characters": [{"name": c["name"], "speaker": c.get("speaker", 3), "role": c.get("role", ""),
                                    "color": ass_to_css(c.get("color")), "position": c.get("position", "right"),
                                    "image": f"/charimg/{i}" if c.get("image") and Path(c["image"]).exists() else ""}
                                   for i, c in enumerate(t.get("characters") or [])]},
            "subtitle": {"font": cfg.get("subtitle", {}).get("font", ""), "burn": cfg.get("subtitle", {}).get("burn", True)},
            "channel_style": cfg.get("claude", {}).get("channel_style", ""),
            "data_dir": str(data_dir()),
        })

    @app.post("/api/settings")
    def settings_save():
        b = request.get_json()
        save_env({k: v for k, v in (b.get("keys") or {}).items() if k in KEYS})
        t = b.get("tts") or {}
        old = tc().get("characters") or []
        chars = []
        for i, c in enumerate(t.get("characters") or []):
            prev = old[i] if i < len(old) else {}
            chars.append({**prev, "name": c["name"].strip(), "speaker": int(c["speaker"]), "role": c.get("role", ""),
                          "color": css_to_ass(c.get("color", "#ffffff")), "position": c.get("position", "right")})
        changes = {"tts": {"engine": t.get("engine", "voicevox"), "mode": t.get("mode", "dialogue"),
                           "voicevox_speaker": int(t.get("voicevox_speaker", 3)),
                           "voicevox": {**(tc().get("voicevox") or {}), "speedScale": float(t.get("speed", 1.0))},
                           "characters": chars}}
        if b.get("voicevox_path") is not None:
            changes["tts"]["voicevox_path"] = b["voicevox_path"].strip()
        if b.get("subtitle"):
            changes["subtitle"] = {"font": b["subtitle"].get("font", "").strip() or "IPAGothic",
                                   "burn": bool(b["subtitle"].get("burn", True))}
        if b.get("channel_style") is not None:
            changes["claude"] = {"channel_style": b["channel_style"]}
        save_settings(changes)
        reload_cfg()
        return ok()

    @app.post("/api/char_image")
    def char_image():
        i = int(request.form["index"])
        f = request.files["file"]
        if Path(f.filename or "").suffix.lower() not in (".png", ".webp"):
            raise RuntimeError("투명 배경 PNG(또는 WEBP) 파일을 올려 주세요")
        d = data_dir() / "assets"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / f"character_{i}_{uuid.uuid4().hex[:6]}{Path(f.filename).suffix.lower()}"
        f.save(dst)
        chars = [dict(c) for c in tc().get("characters") or []]
        if i >= len(chars):
            abort(400)
        chars[i]["image"] = str(dst)
        save_settings({"tts": {"characters": chars}})
        reload_cfg()
        return ok()

    @app.post("/api/install_ffmpeg")
    def install_ffmpeg():
        return ok(job=start(data_dir(), "ffmpeg 설치", setup_tools.install_ffmpeg))

    @app.post("/api/launch_voicevox")
    def launch_voicevox():
        return ok(path=setup_tools.launch_voicevox(tc()))

    @app.post("/api/open_folder")
    def open_folder():
        d = out_root
        if sys_platform() == "win32":
            os.startfile(str(d))  # type: ignore[attr-defined]
        elif sys_platform() == "darwin":
            import subprocess
            subprocess.Popen(["open", str(d)])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(d)]) if shutil.which("xdg-open") else None
        return ok(path=str(d))


def sys_platform() -> str:
    import sys
    return sys.platform
