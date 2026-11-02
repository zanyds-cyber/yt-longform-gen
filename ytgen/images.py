"""장면 이미지 생성/수집. 실패하면 플레이스홀더로 대체해 렌더링이 멈추지 않게 한다."""
from __future__ import annotations

import base64
import io
import os
import random
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import log, short_hash

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def _pollinations(prompt: str, w: int, h: int, cfg: dict) -> Image.Image:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    r = requests.get(url, params={"width": w, "height": h, "nologo": "true",
                                  "seed": random.randint(1, 10**6)}, timeout=180)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))


def _openai(prompt: str, w: int, h: int, cfg: dict) -> Image.Image:
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": cfg.get("openai_model", "gpt-image-1"), "prompt": prompt,
              "size": "1536x1024" if w >= h else "1024x1536",
              "quality": cfg.get("openai_quality", "medium"), "n": 1},
        timeout=300,
    )
    r.raise_for_status()
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"])))


def _pexels(prompt: str, w: int, h: int, cfg: dict) -> Image.Image:
    key = os.environ["PEXELS_API_KEY"]
    q = cfg.get("_query") or prompt
    q = " ".join(q.split(",")[0].split()[:6])  # 검색어는 짧게
    r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                     params={"query": q, "orientation": "landscape", "per_page": 15}, timeout=60)
    r.raise_for_status()
    photos = r.json().get("photos") or []
    if not photos:
        raise RuntimeError(f"no pexels result for '{q}'")
    url = random.choice(photos[:8])["src"]["large2x"]
    return Image.open(io.BytesIO(requests.get(url, timeout=120).content))


def placeholder(text: str, w: int, h: int, seed: str = "") -> Image.Image:
    rnd = random.Random(seed or text)
    c1 = tuple(rnd.randint(20, 90) for _ in range(3))
    c2 = tuple(rnd.randint(90, 170) for _ in range(3))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    for _ in range(12):
        r = rnd.randint(h // 10, h // 3)
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(min(255, v + 25) for v in c2))
    img = img.filter(ImageFilter.GaussianBlur(40))
    if not text:
        return img
    d = ImageDraw.Draw(img)
    f = find_font(h // 12)
    d.text((w // 2, h // 2 - h // 10), text[:24], font=f, fill="white", anchor="mm",
           stroke_width=3, stroke_fill="black")
    return img


PROVIDERS = {"pollinations": _pollinations, "openai": _openai, "pexels": _pexels}


def make_image(prompt: str, out: Path, w: int, h: int, cfg: dict, label: str = "") -> Path:
    if out.exists():
        return out
    provider = cfg.get("provider", "pollinations")
    full = f"{prompt}, {cfg['style']}" if cfg.get("style") and provider != "pexels" else prompt
    img = None
    if provider in PROVIDERS:
        for attempt in range(3):
            try:
                img = PROVIDERS[provider](full, w, h, {**cfg, "_query": prompt})
                break
            except Exception as e:
                log(f"  [image] {provider} failed ({attempt+1}/3): {str(e)[:120]}")
    if img is None:
        img = placeholder(label, w, h, seed=prompt)
    _fit(img, w, h).save(out, quality=92)
    return out


def make_all(jobs: list[tuple[str, str]], img_dir: Path, w: int, h: int, cfg: dict) -> list[Path]:
    """jobs: [(prompt, label)] → 이미지 경로 목록 (프롬프트 해시로 캐시)."""
    img_dir.mkdir(parents=True, exist_ok=True)
    key = {k: cfg.get(k) for k in ("provider", "style", "openai_model", "openai_quality")}
    paths = [img_dir / f"{short_hash(p, key, w, h)}.jpg" for p, _ in jobs]
    todo = [(j, p) for j, p in zip(jobs, paths) if not p.exists()]
    if todo:
        log(f"[image] {cfg.get('provider')}: {len(todo)} images")
        with ThreadPoolExecutor(cfg.get("concurrency", 3)) as ex:
            list(ex.map(lambda jp: make_image(jp[0][0], jp[1], w, h, cfg, jp[0][1]), todo))
    return paths
