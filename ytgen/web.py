"""편집 화면 (로컬 웹 UI): python -m ytgen web  →  http://127.0.0.1:8765

조사 → 주제 선택 → 대본 → 장면별 수정/소스 교체/미리보기 → 렌더링 → 숏츠 → 업로드 를 버튼으로.
"""
from __future__ import annotations

import html
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file

from . import media as media_mod
from .common import log, read_json, set_log_file, write_json

JOBS: dict[str, dict] = {}
BUSY: set[str] = set()


def serve(cfg: dict, out_root: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024**3

    # ---------- helpers ----------
    def proj(name: str | None) -> Path:
        if not name:
            abort(400)
        p = (out_root / name).resolve()
        if out_root not in p.parents or not p.is_dir():
            abort(404)
        return p

    def rel(p: Path) -> str:
        return str(p.relative_to(out_root))

    def start(p: Path, kind: str, fn) -> str:
        key = str(p)
        if key in BUSY:
            raise RuntimeError("이 프로젝트에서 이미 작업이 진행 중입니다")
        jid = uuid.uuid4().hex[:8]
        (p / "work").mkdir(parents=True, exist_ok=True)
        logp = p / "work" / f"job_{jid}.log"
        JOBS[jid] = {"status": "running", "log": logp, "kind": kind, "project": rel(p)}
        BUSY.add(key)

        def runner():
            set_log_file(logp)
            try:
                log(f"▶ {kind} 시작 {datetime.now():%H:%M:%S}")
                r = fn()
                JOBS[jid]["result"] = r if isinstance(r, (str, int, float, type(None))) else None
                JOBS[jid]["status"] = "done"
                log(f"✔ {kind} 완료 {datetime.now():%H:%M:%S}")
            except Exception as e:
                JOBS[jid]["status"] = "error"
                log(f"✖ 오류: {e}\n{traceback.format_exc()[-1500:]}")
            finally:
                BUSY.discard(key)
                set_log_file(None)

        threading.Thread(target=runner, daemon=True).start()
        return jid

    def scene_at(script: dict, idx: int):
        i = 0
        for sec in script["sections"]:
            for j, sc in enumerate(sec["scenes"]):
                if i == idx:
                    return sec, j, sc
                i += 1
        abort(404)

    def body() -> dict:
        return request.get_json(silent=True) or request.form.to_dict()

    def ok(**kw):
        return jsonify({"ok": True, **kw})

    @app.errorhandler(RuntimeError)
    def _err(e):
        return jsonify({"ok": False, "error": str(e)}), 400

    # ---------- pages ----------
    @app.get("/")
    def index():
        rows = []
        for d in sorted(out_root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            title = d.name
            if (d / "script.json").exists():
                title = read_json(d / "script.json").get("title", d.name)
            stage = ("업로드됨" if (d / "upload.json").exists() else "완성" if (d / "final.mp4").exists()
                     else "대본" if (d / "script.json").exists() else "주제" if (d / "topics.json").exists()
                     else "조사" if (d / "research.json").exists() else "-")
            rows.append(f"<tr><td><a href='/p?name={html.escape(d.name)}'>{html.escape(title)}</a></td>"
                        f"<td>{stage}</td><td class=muted>{html.escape(d.name[:13])}</td></tr>")
        return page("프로젝트", f"""
<h1>YouTube 자동 운영</h1>
<div class=grid2>
<section class=card><h2>1. 조사로 시작</h2>
 <label>키워드 <input id=kw placeholder="例: 雑学 動物 / ずんだもん 解説"></label>
 <div class=row><label>기간 <select id=days><option>7<option>14<option selected>30<option>90<option>180</select>일</label>
 <label>길이 <select id=dur><option value=any>전체<option value=medium selected>4~20분<option value=long>20분+<option value=short>4분 미만</select></label></div>
 <label><input type=checkbox id=trend> 키워드 대신 일본 급상승 영상</label>
 <label>카테고리 <select id=cat><option>all<option>education<option>entertainment<option>science<option>howto<option>people<option>gaming<option>news</select></label>
 <button onclick="api('research',{{keyword:kw.value,days:+days.value,duration:dur.value,trending:trend.checked,category:cat.value}})">조사 시작</button>
</section>
<section class=card><h2>또는 바로 대본</h2>
 <label>주제 <input id=tp placeholder="例: 猫が箱に入りたがる本当の理由"></label>
 <label>길이(분) <input id=tm type=number value=12></label>
 <button onclick="api('script_topic',{{topic:tp.value,minutes:+tm.value}})">대본 작성</button>
</section></div>
<section class=card><h2>프로젝트</h2><table><tr><th>제목</th><th>단계</th><th>생성</th></tr>{''.join(rows)}</table></section>
""")

    @app.get("/p")
    def project_page():
        p = proj(request.args.get("name"))
        name = rel(p)
        parts = [f"<p><a href='/'>← 프로젝트 목록</a></p><h1>{html.escape(name)}</h1>"]
        # 조사
        if (p / "research.json").exists():
            res = read_json(p / "research.json")
            trs = "".join(
                f"<tr><td><img class=th src='{v['thumbnail']}'></td><td><a target=_blank href='{v['url']}'>{html.escape(v['title'])}</a>"
                f"<div class=muted>{html.escape(v['channel'])} · {v['published']} · {v['duration']}</div></td>"
                f"<td class=num>{v['views']:,}</td><td class=num>{(v['subscribers'] or 0):,}</td>"
                f"<td class=num><b>{v['outlier'] if v['outlier'] is not None else '-'}x</b></td><td class=num>{v['views_per_day']:,}</td></tr>"
                for v in res["videos"][:20])
            parts.append(f"""<details class=card {'open' if not (p / 'topics.json').exists() else ''}><summary><h2>1. 조사 결과 — {html.escape(res['keyword'] or '급상승')}</h2></summary>
<p class=muted>떡상지수 = 조회수 ÷ 구독자. 높을수록 채널 규모 대비 잘 터진 영상 · 자주 쓰인 태그: {html.escape(', '.join(res['common_tags'][:12]))}</p>
<table><tr><th></th><th>영상</th><th>조회수</th><th>구독자</th><th>떡상</th><th>일평균</th></tr>{trs}</table>
<label>주제 제안에 반영할 메모 <input id=tnotes placeholder="예: 동물 잡학 위주로, 20~30대 대상"></label>
<button onclick="api('topics',{{project:'{name}',notes:tnotes.value}})">{'주제 다시 제안' if (p / 'topics.json').exists() else '2. 주제 3개 제안받기'}</button></details>""")
        # 주제
        if (p / "topics.json").exists():
            tp = read_json(p / "topics.json")
            cards = "".join(f"""<div class=topic><h3>[{i}] {html.escape(t['title'])}</h3>
<p><b>각도</b> {html.escape(t['angle'])}</p><p><b>근거</b> {html.escape(t['why'])}</p>
<p><b>훅</b> 「{html.escape(t['hook'])}」</p><ol>{''.join('<li>' + html.escape(o) for o in t['outline'])}</ol>
<p class=warn><b>주의</b> {html.escape(t['risk'])}</p>
<div class=row><label>길이 <input id=m{i} type=number value={t['minutes']} style='width:5em'>분</label>
<button onclick="api('script',{{project:'{name}',pick:{i},minutes:+m{i}.value}})">이 주제로 대본 작성</button></div></div>"""
                            for i, t in enumerate(tp["topics"], 1))
            parts.append(f"""<details class=card {'open' if not (p / 'script.json').exists() else ''}><summary><h2>2. 주제 선택</h2></summary>
<pre class=insight>{html.escape(tp['insights'])}</pre><div class=topics>{cards}</div></details>""")
        # 대본 + 장면
        if (p / "script.json").exists():
            sc = read_json(p / "script.json")
            parts.append(f"""<section class=card><h2>3. 대본 · 메타데이터</h2>
<label>제목 <input id=t_title value="{html.escape(sc['title'])}"></label>
<p class=muted>후보: {html.escape(' / '.join(sc.get('title_candidates', [])))}</p>
<label>설명 <textarea id=t_desc rows=4>{html.escape(sc.get('description', ''))}</textarea></label>
<label>태그 (쉼표) <input id=t_tags value="{html.escape(', '.join(sc.get('tags', [])))}"></label>
<label>썸네일 문구 <input id=t_thumb value="{html.escape(sc.get('thumbnail_text', ''))}"></label>
<button onclick="api('save_meta',{{project:'{name}',title:t_title.value,description:t_desc.value,tags:t_tags.value,thumbnail_text:t_thumb.value}},false)">저장</button></section>""")
            idx, scenes_html = 0, []
            for si, sec in enumerate(sc["sections"]):
                scenes_html.append(f"<h3 class=chap>{si + 1}. {html.escape(sec['heading'])}</h3>")
                for scene in sec["scenes"]:
                    scenes_html.append(scene_card(p, name, idx, scene))
                    idx += 1
            parts.append(f"<section class=card><h2>4. 장면 편집 ({idx}개)</h2>"
                         "<p class=muted>수정 후 [저장] → [미리보기]로 그 장면만 확인. [소스 교체]는 다른 스톡 영상/이미지로 바꿉니다.</p>"
                         + "".join(scenes_html) + "</section>")
            # 결과
            ver = int((p / "final.mp4").stat().st_mtime) if (p / "final.mp4").exists() else 0
            out = [f"<section class=card><h2>5. 완성 영상</h2><div class=row>"
                   f"<button class=primary onclick=\"api('build',{{project:'{name}'}})\">전체 렌더링</button>"
                   f"<button onclick=\"api('thumbnail',{{project:'{name}'}})\">썸네일만 다시</button></div>"]
            if ver:
                out.append(f"<video controls class=final src='/f?name={name}&path=final.mp4&v={ver}'></video>")
            if (p / "thumbnail.jpg").exists():
                tv = int((p / "thumbnail.jpg").stat().st_mtime)
                out.append(f"<img class=thumb src='/f?name={name}&path=thumbnail.jpg&v={tv}'>")
            if (p / "description.txt").exists():
                out.append(f"<label>설명란(업로드 시 그대로 사용) <textarea id=desc_txt rows=10>{html.escape((p / 'description.txt').read_text(encoding='utf-8'))}</textarea></label>"
                           f"<button onclick=\"api('save_desc',{{project:'{name}',text:desc_txt.value}},false)\">설명란 저장</button>")
            out.append("</section>")
            parts.append("".join(out))
            # 숏츠
            if "parent" not in sc:
                subs = sorted((p / "shorts").glob("*/script.json")) if (p / "shorts").exists() else []
                links = "".join(f"<li><a href='/p?name={rel(s.parent)}'>{html.escape(read_json(s)['title'])}</a>"
                                f"{' ✔' if (s.parent / 'final.mp4').exists() else ''}</li>" for s in subs)
                parts.append(f"""<section class=card><h2>숏츠</h2><ul>{links}</ul>
<div class=row><label>개수 <input id=scount type=number value=2 style='width:4em'></label>
<label><input type=checkbox id=sbuild checked> 바로 렌더링</label>
<button onclick="api('shorts',{{project:'{name}',count:+scount.value,build:sbuild.checked}})">롱폼에서 숏츠 만들기</button></div></section>""")
            # 업로드
            up = read_json(p / "upload.json") if (p / "upload.json").exists() else None
            parts.append(f"""<section class=card><h2>6. 유튜브 업로드</h2>
{f"<p>업로드됨: <a target=_blank href='{up['url']}'>{up['url']}</a> ({up['privacy']})</p>" if up else ''}
<div class=row><label>공개 <select id=priv><option value=private>비공개<option value=unlisted>일부 공개<option value=public>공개</select></label>
<label>예약 공개 <input id=pub type=datetime-local></label>
<button class=primary {'disabled' if not ver else ''} onclick="upload('{name}')">업로드</button></div>
<p class=muted>처음 한 번은 이 PC 브라우저에서 구글 로그인 창이 열립니다. 먼저 비공개로 올려 확인 후 공개하는 것을 권장합니다.</p></section>""")
        return page(name, "".join(parts), name)

    def scene_card(p: Path, name: str, idx: int, scene: dict) -> str:
        m = (scene.get("media") or [None])[0]
        prev = p / "work" / "preview" / f"scene_{idx:03d}.mp4"
        if prev.exists():
            mv = f"<video controls src='/f?name={name}&path={rel(prev)[len(name) + 1:]}&v={int(prev.stat().st_mtime)}'></video>"
        elif m and m["type"] == "video":
            mv = f"<video muted loop onmouseover='this.play()' onmouseout='this.pause()' preload=metadata src='/f?name={name}&path={m['path']}#t=0.5'></video>"
        elif m:
            mv = f"<img src='/f?name={name}&path={m['path']}'>"
        else:
            mv = "<div class=empty>소스 미정<br><small>렌더링/미리보기 때 자동 선택</small></div>"
        n_media = len(scene.get("media") or [])
        src = ", ".join(sorted({x.get("source", "") for x in scene.get("media") or []}))
        return f"""<div class=scene id=s{idx}><div class=media>{mv}<div class=muted>#{idx} {html.escape(src)} {f'({n_media}개)' if n_media > 1 else ''}</div></div>
<div class=edit><textarea id=n{idx} rows=5>{html.escape(scene['narration'])}</textarea>
<div class=row><input id=q{idx} value="{html.escape(scene.get('stock_query', ''))}" placeholder="스톡 검색어(영어)">
<input id=i{idx} value="{html.escape(scene.get('image_prompt', ''))}" placeholder="이미지 프롬프트(영어)"></div>
<div class=row>
<button onclick="saveScene('{name}',{idx})">저장</button>
<button onclick="saveScene('{name}',{idx}).then(()=>api('preview',{{project:'{name}',index:{idx}}}))">미리보기</button>
<button onclick="api('replace',{{project:'{name}',index:{idx}}})">소스 교체</button>
<label class=file>파일 올리기<input type=file accept="video/*,image/*" onchange="uploadMedia('{name}',{idx},this)"></label>
<button onclick="api('insert',{{project:'{name}',index:{idx}}},false)">＋아래 추가</button>
<button class=danger onclick="if(confirm('이 장면을 삭제할까요?'))api('delete',{{project:'{name}',index:{idx}}},false)">삭제</button>
</div></div></div>"""

    @app.get("/f")
    def file():
        p = proj(request.args.get("name"))
        f = (p / request.args.get("path", "")).resolve()
        if p not in f.parents or not f.is_file():
            abort(404)
        return send_file(f, conditional=True)

    @app.get("/job/<jid>")
    def job(jid):
        j = JOBS.get(jid) or abort(404)
        txt = j["log"].read_text(encoding="utf-8") if j["log"].exists() else ""
        return jsonify({"status": j["status"], "log": txt[-6000:], "project": j.get("project"),
                        "result": j.get("result")})

    # ---------- actions ----------
    @app.post("/api/<action>")
    def api(action):
        b = body()
        from . import __main__ as cli, render, script as script_mod, shorts, upload

        if action == "research":
            kw = (b.get("keyword") or "").strip()
            trending = b.get("trending") in (True, "true", "on")
            if not kw and not trending:
                raise RuntimeError("키워드를 입력하세요")
            p = cli.new_project(out_root, kw if not trending else f"trending_{b.get('category', 'all')}")

            def fn():
                from . import research
                res = research.run_research(None if trending else kw, days=int(b.get("days", 30)),
                                            duration=b.get("duration", "any"), category=b.get("category", "all"))
                write_json(p / "research.json", res)
                (p / "research.md").write_text(research.report_md(res), encoding="utf-8")
            return ok(job=start(p, "조사", fn), goto=rel(p))

        if action == "script_topic":
            topic = (b.get("topic") or "").strip() or abort(400)
            p = cli.new_project(out_root, topic)
            jid = start(p, "대본 작성", lambda: write_json(p / "script.json", script_mod.generate(
                cfg, topic, int(b.get("minutes", 12)), "", out_path=p / "script.json")))
            return ok(job=jid, goto=rel(p))

        p = proj(b.get("project"))
        if action == "topics":
            return ok(job=start(p, "주제 제안", lambda: cli.do_topics(cfg, p, b.get("notes", ""))))
        if action == "script":
            return ok(job=start(p, "대본 작성", lambda: cli.do_script(cfg, p, int(b["pick"]), int(b.get("minutes") or 0) or None)))
        if action == "build":
            return ok(job=start(p, "전체 렌더링", lambda: str(render.build(p, cfg))))
        if action == "thumbnail":
            return ok(job=start(p, "썸네일", lambda: str(render.build(p, cfg, only_thumbnail=True))))
        if action == "preview":
            return ok(job=start(p, f"장면 {b['index']} 미리보기", lambda: str(render.preview_scene(p, cfg, int(b["index"])))))
        if action == "shorts":
            def fn():
                for d in shorts.make_shorts(p, cfg, int(b.get("count", 2))):
                    if b.get("build") in (True, "true", "on"):
                        render.build(d, cfg)
            return ok(job=start(p, "숏츠 생성", fn))
        if action == "upload":
            return ok(job=start(p, "업로드", lambda: upload.upload(p, cfg, b.get("privacy"), b.get("publish_at") or None)))
        if action == "save_desc":
            (p / "description.txt").write_text(b.get("text", ""), encoding="utf-8")
            return ok()

        sp = p / "script.json"
        sc = read_json(sp)
        if action == "save_meta":
            sc["title"] = b.get("title", sc["title"])
            sc["description"] = b.get("description", "")
            sc["tags"] = [t.strip() for t in b.get("tags", "").split(",") if t.strip()]
            sc["thumbnail_text"] = b.get("thumbnail_text", "")
        elif action in ("save_scene", "replace", "insert", "delete"):
            sec, j, scene = scene_at(sc, int(b["index"]))
            if action == "save_scene":
                if scene.get("image_prompt") != b.get("image_prompt") or scene.get("stock_query") != b.get("stock_query"):
                    scene["media"] = []  # 검색어/프롬프트가 바뀌면 소스 다시 선택
                scene["narration"] = b.get("narration", scene["narration"])
                scene["image_prompt"] = b.get("image_prompt", "")
                scene["stock_query"] = b.get("stock_query", "")
            elif action == "replace":
                media_mod.replace(scene)
                write_json(sp, sc)
                return ok(job=start(p, f"장면 {b['index']} 소스 교체", lambda: str(render.preview_scene(p, cfg, int(b["index"])))))
            elif action == "insert":
                sec["scenes"].insert(j + 1, {"narration": "（ここにセリフ）", "image_prompt": scene.get("image_prompt", ""),
                                             "stock_query": scene.get("stock_query", "")})
            elif action == "delete":
                if sum(len(s["scenes"]) for s in sc["sections"]) <= 1:
                    raise RuntimeError("마지막 장면은 삭제할 수 없습니다")
                sec["scenes"].pop(j)
                sc["sections"] = [s for s in sc["sections"] if s["scenes"]]
                for f in (p / "work" / "preview").glob("scene_*.mp4"):  # 번호가 밀리므로 미리보기 정리
                    f.unlink()
        else:
            abort(404)
        write_json(sp, sc)
        return ok()

    @app.post("/upload_media")
    def upload_media():
        p = proj(request.form.get("project"))
        idx = int(request.form["index"])
        f = request.files["file"]
        ext = Path(f.filename or "").suffix.lower()
        if ext not in (".mp4", ".mov", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".webp"):
            raise RuntimeError("지원하지 않는 파일 형식")
        d = p / "work" / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / f"{idx:03d}_{uuid.uuid4().hex[:6]}{ext}"
        f.save(dst)
        sc = read_json(p / "script.json")
        _, _, scene = scene_at(sc, idx)
        scene["media"] = [{"type": "image" if ext in (".jpg", ".jpeg", ".png", ".webp") else "video",
                           "path": str(dst.relative_to(p)), "source": "upload"}]
        write_json(p / "script.json", sc)
        from . import render
        return ok(job=start(p, f"장면 {idx} 미리보기", lambda: str(render.preview_scene(p, cfg, idx))))

    log(f"편집 화면: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#6b7385;--line:#e3e6ec;--acc:#e5484d;--acc2:#2f6fed}
@media (prefers-color-scheme:dark){:root{--bg:#14161b;--card:#1d2027;--ink:#e8eaf0;--muted:#9aa2b3;--line:#2c313b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Hiragino Sans","Noto Sans JP","Malgun Gothic",sans-serif;padding:16px 16px 260px}
main{max-width:1180px;margin:auto}h1{font-size:22px}h2{font-size:17px;margin:0 0 10px;display:inline}h3{font-size:15px;margin:6px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
summary{cursor:pointer;margin-bottom:8px}label{display:block;margin:6px 0;color:var(--muted);font-size:13px}
input,select,textarea{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:inherit}
input[type=checkbox]{width:auto}textarea{resize:vertical}
button,.file{display:inline-block;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);cursor:pointer;font:inherit;font-size:13px;margin:4px 4px 0 0;white-space:nowrap}
button:hover,.file:hover{border-color:var(--acc2)}button.primary{background:var(--acc);border-color:var(--acc);color:#fff}button.danger{color:var(--acc)}
button:disabled{opacity:.4}.file input{display:none}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.row>label,.row>input{flex:1;min-width:160px}.row>label.file{flex:0;min-width:0;color:var(--ink);font-size:13px;margin:4px 4px 0 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:800px){.grid2{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.num{text-align:right;white-space:nowrap}.th{width:96px;border-radius:6px}.muted{color:var(--muted);font-size:12px}
.topics{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.topic{border:1px solid var(--line);border-radius:10px;padding:12px;font-size:13px}.topic p{margin:4px 0}.warn{color:#c47f00}
.insight{white-space:pre-wrap;background:var(--bg);padding:10px;border-radius:8px;font:inherit;font-size:13px}
.chap{margin-top:18px;border-left:4px solid var(--acc);padding-left:8px}
.scene{display:grid;grid-template-columns:300px 1fr;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)}
@media(max-width:800px){.scene{grid-template-columns:1fr}}
.media video,.media img{width:100%;border-radius:8px;background:#000;aspect-ratio:16/9;object-fit:cover}
.empty{aspect-ratio:16/9;border:1px dashed var(--line);border-radius:8px;display:grid;place-items:center;text-align:center;color:var(--muted)}
.final{width:100%;max-height:70vh;background:#000;border-radius:8px}.thumb{width:320px;margin-top:8px;border-radius:8px}
#log{position:fixed;left:0;right:0;bottom:0;max-height:230px;overflow:auto;background:#0d0f14;color:#cfe3cf;font:12px/1.4 ui-monospace,monospace;padding:10px 16px;white-space:pre-wrap;display:none;border-top:2px solid var(--acc)}
"""

JS = """
let polling=null;
async function api(action,data,isJob=true){
  const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const j=await r.json(); if(!j.ok){alert(j.error||'오류');return j}
  if(j.job){watch(j.job,j.goto)} else if(!isJob){location.reload()}
  return j;
}
async function saveScene(name,i){
  return api('save_scene',{project:name,index:i,narration:document.getElementById('n'+i).value,
    stock_query:document.getElementById('q'+i).value,image_prompt:document.getElementById('i'+i).value},true);
}
async function uploadMedia(name,i,input){
  const fd=new FormData();fd.append('project',name);fd.append('index',i);fd.append('file',input.files[0]);
  const j=await (await fetch('/upload_media',{method:'POST',body:fd})).json();
  if(!j.ok){alert(j.error);return} watch(j.job);
}
function upload(name){
  let at=pub.value?new Date(pub.value).toISOString():'';
  if(!confirm('유튜브에 업로드할까요? ('+priv.value+(at?' / 예약 '+pub.value:'')+')'))return;
  api('upload',{project:name,privacy:priv.value,publish_at:at});
}
function watch(id,goto){
  const box=document.getElementById('log');box.style.display='block';localStorage.setItem('job',id);
  clearInterval(polling);
  polling=setInterval(async()=>{
    const r=await fetch('/job/'+id); if(!r.ok){clearInterval(polling);return}
    const j=await r.json(); box.textContent=j.log; box.scrollTop=box.scrollHeight;
    if(j.status!=='running'){clearInterval(polling);localStorage.removeItem('job');
      if(j.status==='done'){setTimeout(()=>{location.href=goto?'/p?name='+encodeURIComponent(goto):location.href.split('#')[0]},700)}}
  },1200);
}
const pending=localStorage.getItem('job'); if(pending) watch(pending);
"""


def page(title: str, content: str, name: str = "") -> str:
    return (f"<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)} · ytgen</title><style>{CSS}</style></head><body><main>{content}</main>"
            f"<pre id=log></pre><script>{JS}</script></body></html>")
