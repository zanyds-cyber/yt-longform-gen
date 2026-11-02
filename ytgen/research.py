"""1단계: YouTube 조사 — 키워드 검색 / 일본 급상승 영상 수집 + 지표 계산.

지표
- views_per_day : 하루 평균 조회수 (최근성 보정)
- outlier       : 조회수 ÷ 구독자 수  → 채널 규모 대비 '떡상' 정도. 1 이상이면 구독자보다 많이 봄
쿼터(기본/일): search.list 100회, 그 외 10,000 unit. 한 번 조사 ≈ search 1회 + 수 unit.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from .common import fmt_ts, log

API = "https://www.googleapis.com/youtube/v3"

CATEGORIES = {  # 일본에서 자주 쓰는 카테고리 ID
    "all": None, "film": "1", "autos": "2", "music": "10", "pets": "15", "sports": "17",
    "travel": "19", "gaming": "20", "people": "22", "comedy": "23", "entertainment": "24",
    "news": "25", "howto": "26", "education": "27", "science": "28",
}


def _get(path: str, **params) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY 가 없습니다 (.env 에 설정)")
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"YouTube API error: {data['error'].get('message')}")
    return data


def _iso_dur(s: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _enrich(video_items: list[dict]) -> list[dict]:
    """videos.list 결과 + 채널 구독자 수 → 지표 계산."""
    ch_ids = list({v["snippet"]["channelId"] for v in video_items})
    subs = {}
    for i in range(0, len(ch_ids), 50):
        for c in _get("channels", part="statistics", id=",".join(ch_ids[i:i + 50])).get("items", []):
            st = c.get("statistics", {})
            subs[c["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
    now = datetime.now(timezone.utc)
    out = []
    for v in video_items:
        sn, st = v["snippet"], v.get("statistics", {})
        pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        days = max((now - pub).total_seconds() / 86400, 0.5)
        views = int(st.get("viewCount", 0))
        sub = subs.get(sn["channelId"])
        dur = _iso_dur(v.get("contentDetails", {}).get("duration", ""))
        out.append({
            "id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}",
            "title": sn["title"], "channel": sn["channelTitle"], "channel_id": sn["channelId"],
            "published": sn["publishedAt"][:10], "days": round(days, 1),
            "views": views, "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
            "subscribers": sub, "duration_sec": dur, "duration": fmt_ts(dur),
            "is_short": dur <= 180, "tags": sn.get("tags", [])[:15],
            "description": sn.get("description", "")[:300],
            "thumbnail": sn.get("thumbnails", {}).get("high", {}).get("url", ""),
            "views_per_day": round(views / days),
            "outlier": round(views / sub, 2) if sub else None,
        })
    return out


def _videos(ids: list[str]) -> list[dict]:
    items = []
    for i in range(0, len(ids), 50):
        items += _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))["items"]
    return items


def search(keyword: str, days: int = 30, duration: str = "any", order: str = "viewCount",
           region: str = "JP", max_results: int = 50) -> list[dict]:
    """duration: any | short(<4분) | medium(4~20분) | long(>20분)"""
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = dict(part="snippet", q=keyword, type="video", order=order, regionCode=region,
                  relevanceLanguage="ja", publishedAfter=after, maxResults=min(max_results, 50))
    if duration != "any":
        params["videoDuration"] = duration
    ids = [it["id"]["videoId"] for it in _get("search", **params).get("items", [])]
    return _enrich(_videos(ids)) if ids else []


def trending(category: str = "all", region: str = "JP", max_results: int = 50) -> list[dict]:
    params = dict(part="snippet,statistics,contentDetails", chart="mostPopular",
                  regionCode=region, maxResults=min(max_results, 50))
    cat = CATEGORIES.get(category, category)
    if cat:
        params["videoCategoryId"] = cat
    return _enrich(_get("videos", **params).get("items", []))


def top_comments(video_id: str, n: int = 15) -> list[str]:
    try:
        d = _get("commentThreads", part="snippet", videoId=video_id, order="relevance",
                 maxResults=n, textFormat="plainText")
    except RuntimeError:
        return []  # 댓글 비활성화 영상
    return [it["snippet"]["topLevelComment"]["snippet"]["textDisplay"][:200] for it in d.get("items", [])]


def run_research(keyword: str | None, days: int = 30, duration: str = "any",
                 category: str = "all", comments_for: int = 3) -> dict:
    if keyword:
        log(f"[research] search '{keyword}' (last {days} days, duration={duration})")
        vids = search(keyword, days=days, duration=duration)
    else:
        log(f"[research] trending JP (category={category})")
        vids = trending(category)
    # 정렬: 떡상 지수(없으면 하루 조회수) 우선
    vids.sort(key=lambda v: (v["outlier"] or 0, v["views_per_day"]), reverse=True)
    for v in vids[:comments_for]:
        v["top_comments"] = top_comments(v["id"])
    words = Counter()
    for v in vids:
        for t in v["tags"]:
            words[t] += 1
    res = {
        "keyword": keyword, "category": category, "days": days, "duration": duration,
        "fetched_at": datetime.now().isoformat(timespec="minutes"),
        "videos": vids,
        "common_tags": [w for w, _ in words.most_common(25)],
        "stats": {
            "count": len(vids),
            "shorts": sum(v["is_short"] for v in vids),
            "median_duration_min": round(sorted(v["duration_sec"] for v in vids)[len(vids) // 2] / 60, 1) if vids else 0,
        },
    }
    log(f"[research] {len(vids)} videos")
    return res


def report_md(res: dict, top: int = 20) -> str:
    title = f"「{res['keyword']}」検索" if res["keyword"] else f"急上昇 ({res['category']})"
    lines = [f"# 조사 리포트: {title}", "",
             f"- 수집: {res['fetched_at']} / {res['stats']['count']}개 (숏츠 {res['stats']['shorts']}개)",
             f"- 중간 길이: {res['stats']['median_duration_min']}분",
             f"- 자주 쓰인 태그: {', '.join(res['common_tags'][:15])}", "",
             "| # | 제목 | 채널 | 조회수 | 구독자 | 떡상지수 | 일평균 | 길이 | 업로드 |",
             "|---|---|---|---:|---:|---:|---:|---|---|"]
    for i, v in enumerate(res["videos"][:top], 1):
        sub = f"{v['subscribers']:,}" if v["subscribers"] is not None else "비공개"
        out = f"{v['outlier']}x" if v["outlier"] is not None else "-"
        t = v["title"].replace("|", "｜")
        lines.append(f"| {i} | [{t}]({v['url']}) | {v['channel']} | {v['views']:,} | {sub} | {out} | "
                     f"{v['views_per_day']:,} | {v['duration']} | {v['published']} |")
    return "\n".join(lines) + "\n"
