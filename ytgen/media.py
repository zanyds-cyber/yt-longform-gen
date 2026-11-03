"""3단계: 장면별 화면 소스 — 합법적으로 재사용할 수 있는 영상만 검색·다운로드, 없으면 이미지.

소스                라이선스                       비고
- pexels / pixabay  자체 무료 라이선스(상업 OK)    고화질 스톡
- wikimedia         CC BY / BY-SA / 퍼블릭 도메인   위키미디어 공용. 출처 표기 필수 (설명란 자동)
- archive           퍼블릭 도메인 / CC             인터넷 아카이브. 기록·역사 영상(예: 한국전쟁 미군 기록필름)
- nasa              퍼블릭 도메인                  NASA 영상
긴 영상은 필요한 구간만 잘라서(ffmpeg) 저장한다. 남의 유튜브 영상은 사용하지 않는다(약관·저작권).

장면의 결정된 소스는 script.json 의 scene["media"] 에 기록된다 (편집 화면에서 교체 가능):
  "media": [{"type": "video"|"image", "path": "work/stock/xxx.mp4", "source": "pexels", "id": "123"}]
  "exclude": ["pexels:123", ...]   ← '다른 소스로 교체' 시 다시 고르지 않을 ID
"""
from __future__ import annotations

import html as _html
import math
import os
import random
import re
from pathlib import Path

import requests

from . import images
from .common import log, run, short_hash

UA = {"User-Agent": "ytgen-studio/1.0 (https://github.com/zanyds-cyber/yt-longform-gen)"}


def _strip_html(t: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()


def _pexels(query: str, portrait: bool, n: int = 20) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait" if portrait else "landscape",
                             "per_page": n, "size": "medium"}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("width") and f.get("link")
                 and f.get("file_type", "").endswith("mp4")]
        if not files:
            continue
        target = 1080 if portrait else 1920
        files.sort(key=lambda f: (abs(min(f["width"], f["height"]) - min(target, 1080)), f["width"]))
        small = min(files, key=lambda f: f["width"])
        pics = v.get("video_pictures") or []
        out.append({"source": "pexels", "id": str(v["id"]), "url": files[0]["link"],
                    "duration": v.get("duration", 0), "credit": v.get("user", {}).get("name", ""),
                    "thumb": v.get("image") or (pics[0]["picture"] if pics else ""), "preview": small["link"]})
    return out


def _pixabay(query: str, portrait: bool, n: int = 20) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": key, "q": query[:100], "per_page": n, "safesearch": "true"}, timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        vids = h.get("videos", {})
        f = vids.get("large") if vids.get("large", {}).get("url") else vids.get("medium", {})
        if not f or not f.get("url"):
            continue
        if portrait != (f.get("height", 0) > f.get("width", 1)):
            continue
        tiny = vids.get("tiny") or vids.get("small") or f
        out.append({"source": "pixabay", "id": str(h["id"]), "url": f["url"],
                    "duration": h.get("duration", 0), "credit": h.get("user", ""),
                    "thumb": f.get("thumbnail") or tiny.get("thumbnail", ""), "preview": tiny.get("url", f["url"])})
    return out


def _wikimedia(query: str, portrait: bool, n: int = 20) -> list[dict]:
    """위키미디어 공용 동영상 (CC/퍼블릭 도메인만 존재)."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"filetype:video {query}", "gsrlimit": n,
        "prop": "videoinfo|imageinfo", "viprop": "url|size|mime|extmetadata|derivatives",
        "iiprop": "url", "iiurlwidth": 480})
    r.raise_for_status()
    out = []
    for pg in (r.json().get("query", {}).get("pages") or {}).values():
        vi = (pg.get("videoinfo") or [{}])[0]
        if not vi.get("url"):
            continue
        meta = vi.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        derivs = [d for d in vi.get("derivatives", []) if d.get("src") and (d.get("height") or 0) <= 1080
                  and ("webm" in d.get("type", "") or "mp4" in d.get("type", ""))]
        derivs.sort(key=lambda d: d.get("height") or 0, reverse=True)
        src = derivs[0]["src"] if derivs else vi["url"]
        if (vi.get("height") or 0) and portrait != (vi["height"] > (vi.get("width") or 1)):
            continue
        thumb = ((pg.get("imageinfo") or [{}])[0]).get("thumburl", "")
        out.append({"source": "wikimedia", "id": str(pg["pageid"]), "url": src, "duration": round(vi.get("duration") or 0),
                    "credit": _strip_html(meta.get("Artist", {}).get("value", ""))[:80] or "Wikimedia Commons",
                    "license": lic, "page": vi.get("descriptionurl", ""), "title": pg.get("title", "").replace("File:", ""),
                    "thumb": thumb, "preview": "", "height": vi.get("height") or 0})
    return out


def _archive(query: str, portrait: bool, n: int = 20) -> list[dict]:
    """인터넷 아카이브 영상 (퍼블릭 도메인/CC 라이선스가 명시된 것만)."""
    q = (f"({query}) AND mediatype:(movies) AND "
         "(licenseurl:*publicdomain* OR licenseurl:*creativecommons.org/licenses/by/* "
         "OR licenseurl:*creativecommons.org/licenses/by-sa/* OR licenseurl:*creativecommons.org/publicdomain*)")
    r = requests.get("https://archive.org/advancedsearch.php", headers=UA, timeout=30, params={
        "q": q, "fl[]": ["identifier", "title", "licenseurl", "creator", "year"], "rows": n, "output": "json"})
    r.raise_for_status()
    out = []
    for d in r.json().get("response", {}).get("docs", []):
        ident = d["identifier"]
        lic = d.get("licenseurl", "")
        lic = "Public Domain" if "publicdomain" in lic else ("CC BY-SA" if "by-sa" in lic else "CC BY")
        creator = d.get("creator", "")
        out.append({"source": "archive", "id": ident, "url": None, "duration": 0,
                    "credit": (creator[0] if isinstance(creator, list) else creator) or "Internet Archive",
                    "license": lic, "page": f"https://archive.org/details/{ident}",
                    "title": str(d.get("title", ident))[:120], "thumb": f"https://archive.org/services/img/{ident}", "preview": ""})
    return out


def _archive_file(ident: str) -> tuple[str, float]:
    """아카이브 항목에서 쓸 mp4 파일 URL과 길이(초)."""
    m = requests.get(f"https://archive.org/metadata/{ident}", headers=UA, timeout=30).json()
    files = [f for f in m.get("files", []) if f.get("name", "").lower().endswith(".mp4")]
    if not files:
        raise RuntimeError("mp4 파일이 없는 항목")

    def length(f):
        v = str(f.get("length", "0"))
        if ":" in v:
            sec = 0.0
            for part in v.split(":"):
                sec = sec * 60 + float(part or 0)
            return sec
        try:
            return float(v)
        except ValueError:
            return 0.0
    # 720p 이상 중 가장 작은 파일, 없으면 가장 큰 해상도
    good = [f for f in files if int(f.get("height") or 0) >= 720]
    f = min(good, key=lambda x: int(x.get("size") or 0)) if good else max(files, key=lambda x: int(x.get("height") or 0))
    return f"https://archive.org/download/{ident}/{f['name']}", length(f)


def _nasa(query: str, portrait: bool, n: int = 20) -> list[dict]:
    r = requests.get("https://images-api.nasa.gov/search", headers=UA, timeout=30,
                     params={"q": query, "media_type": "video", "page_size": n})
    r.raise_for_status()
    out = []
    for it in r.json().get("collection", {}).get("items", [])[:n]:
        d = (it.get("data") or [{}])[0]
        out.append({"source": "nasa", "id": d.get("nasa_id", ""), "url": None, "duration": 0,
                    "credit": "NASA" + (f" / {d['center']}" if d.get("center") else ""), "license": "Public Domain",
                    "page": f"https://images.nasa.gov/details/{d.get('nasa_id', '')}", "title": d.get("title", "")[:120],
                    "thumb": ((it.get("links") or [{}])[0]).get("href", ""), "preview": "", "assets": it.get("href", "")})
    return out


def _nasa_file(c: dict) -> str:
    assets = requests.get(c["assets"] or f"https://images-assets.nasa.gov/video/{c['id']}/collection.json",
                          headers=UA, timeout=30).json()
    mp4 = [a for a in assets if str(a).lower().endswith(".mp4")]
    for key in ("~large.mp4", "~medium.mp4", "~orig.mp4", "~mobile.mp4"):
        for a in mp4:
            if a.endswith(key):
                return a.replace("http://", "https://")
    if mp4:
        return mp4[0].replace("http://", "https://")
    raise RuntimeError("mp4 없음")


SOURCES = {"pexels": _pexels, "pixabay": _pixabay, "wikimedia": _wikimedia, "archive": _archive, "nasa": _nasa}
LICENSED = {"wikimedia", "archive", "nasa"}   # 설명란에 개별 출처 표기
ALLOWED_HOSTS = ("pexels.com", "pixabay.com", "vimeo.com", "vimeocdn.com", "wikimedia.org", "archive.org",
                 "nasa.gov")


def _cut(src: str, dst: Path, start: float, length: float, headers: bool = True) -> None:
    """원본(파일 또는 URL)에서 [start, start+length] 구간만 1080p 이하 H.264로 저장."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if headers and src.startswith("http"):
        cmd += ["-user_agent", UA["User-Agent"]]
    cmd += ["-ss", f"{start:.2f}", "-i", src, "-t", f"{length:.2f}", "-an",
            "-vf", "scale=-2:'min(1080,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(dst)]
    run(cmd)


def fetch(project: Path, c: dict, seconds: float = 20) -> Path:
    """후보 영상을 내려받아 work/stock 에 저장(긴 영상은 필요한 구간만 잘라서)."""
    d = project / "work" / "stock"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(c["id"]))[:80]
    dst = d / f"{c['source']}_{safe}.mp4"
    if dst.exists():
        return dst
    if c["source"] in ("pexels", "pixabay"):
        return _download(c["url"], dst)
    if c["source"] == "archive":
        url, total = _archive_file(c["id"])
    elif c["source"] == "nasa":
        url, total = _nasa_file(c), float(c.get("duration") or 0)
    else:
        url, total = c["url"], float(c.get("duration") or 0)
    # 앞부분(제목 화면)을 피해 영상 중간쯤에서 자른다
    start = 0.0
    if total > seconds * 2:
        start = random.Random(c["id"]).uniform(total * 0.15, max(total * 0.15, total * 0.7 - seconds))
    elif c["source"] == "archive" and not total:
        start = 60.0
    try:
        _cut(url, dst, start, seconds)
    except Exception as e:  # 원격 구간 읽기 실패 → 통째로 받아서 자르기 (최대 600MB)
        log(f"  [media] 원격 자르기 실패, 전체 다운로드로 재시도 ({str(e)[:80]})")
        tmp = d / f"_full_{safe}"
        _download(url, tmp, max_bytes=600 * 1024 * 1024)
        try:
            _cut(str(tmp), dst, start if start < 1e9 else 0, seconds, headers=False)
        except Exception:
            _cut(str(tmp), dst, 0, seconds, headers=False)
        tmp.unlink(missing_ok=True)
    return dst


def entry(project: Path, c: dict, path: Path) -> dict:
    e = {"type": "video", "path": str(path.relative_to(project)), "source": c["source"], "id": str(c["id"]),
         "credit": c.get("credit", "")}
    for k in ("license", "page", "title"):
        if c.get(k):
            e[k] = c[k]
    return e


def _download(url: str, dst: Path, max_bytes: int | None = None) -> Path:
    if dst.exists():
        return dst
    tmp = dst.with_suffix(".part")
    got = 0
    with requests.get(url, stream=True, timeout=120, headers=UA) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                got += len(chunk)
                if max_bytes and got > max_bytes:
                    break
    tmp.rename(dst)
    return dst


def resolve_scene(project: Path, scene: dict, scene_dur: float, w: int, h: int,
                  cfg: dict, used: set[str], label: str = "") -> list[dict]:
    """장면의 소스 목록을 정해 scene['media'] 에 기록하고 반환."""
    existing = [m for m in scene.get("media") or [] if (project / m["path"]).exists()]
    if existing:
        return existing
    mc = cfg.get("media", {})
    mode = mc.get("mode", "auto")  # auto | video | image
    portrait = h > w
    exclude = set(scene.get("exclude", []))
    chosen: list[dict] = []
    if mode in ("auto", "video"):
        seg = float(mc.get("segment_seconds", 7))
        need = max(1, min(int(mc.get("max_clips_per_scene", 4)), math.ceil(scene_dur / seg)))
        query = scene.get("stock_query") or scene.get("image_prompt", "")
        cands: list[dict] = []
        for name in mc.get("sources", ["pexels", "pixabay"]):
            try:
                cands += SOURCES[name](query, portrait)
            except Exception as e:
                log(f"  [media] {name} search failed: {str(e)[:100]}")
        cands = [c for c in cands if f"{c['source']}:{c['id']}" not in exclude | used]
        random.Random(query).shuffle(cands)
        for c in cands:
            if len(chosen) >= need:
                break
            try:
                dst = fetch(project, c, seconds=max(seg * 1.5, 10))
            except Exception as e:
                log(f"  [media] download failed: {str(e)[:100]}")
                continue
            used.add(f"{c['source']}:{c['id']}")
            chosen.append(entry(project, c, dst))
        if not chosen and mode == "video":
            log(f"  [media] no stock video for '{query}', falling back to image")
    if not chosen:
        ic = cfg.get("image", {})
        job = (scene.get("image_prompt") or label, label) + ((scene["image_seed"],) if scene.get("image_seed") else ())
        p = images.make_all([job], project / "work" / "images", w, h, ic)[0]
        chosen = [{"type": "image", "path": str(p.relative_to(project)), "source": ic.get("provider", "image")}]
    scene["media"] = chosen
    return chosen


def replace(scene: dict) -> None:
    """'다른 소스로 교체': 현재 소스를 제외 목록에 넣고 비운다 (이미지는 캐시 파일 삭제는 호출측)."""
    ex = set(scene.get("exclude", []))
    for m in scene.get("media") or []:
        if m.get("source") in SOURCES:
            ex.add(f"{m['source']}:{m['id']}")
    scene["exclude"] = sorted(ex)
    scene["media"] = []
    # 이미지면 프롬프트에 변화를 줘서 새로 생성되게 함
    scene["image_seed"] = short_hash(scene.get("image_seed", ""), "next")
