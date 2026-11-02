"""6단계: YouTube 업로드 (YouTube Data API v3, OAuth).

준비
1. Google Cloud Console → 프로젝트 → 'YouTube Data API v3' 사용 설정
2. 사용자 인증 정보 → OAuth 클라이언트 ID → 유형 '데스크톱 앱' → JSON 다운로드
3. 그 파일을 credentials/client_secret.json 으로 저장
첫 실행 때 브라우저가 열리고 채널 계정으로 로그인하면 credentials/token.json 이 저장됩니다.
"""
from __future__ import annotations

import time
from pathlib import Path

from .common import ROOT, log, read_json, write_json

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


def _service(cfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    uc = cfg.get("upload", {})
    secret = ROOT / uc.get("client_secret", "credentials/client_secret.json")
    token = ROOT / uc.get("token", "credentials/token.json")
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secret.exists():
                raise RuntimeError(f"OAuth 클라이언트 파일이 없습니다: {secret}  (README의 '유튜브 업로드 설정' 참고)")
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _trim_tags(tags: list[str], limit: int = 480) -> list[str]:
    out, total = [], 0
    for t in tags:
        t = t.replace("<", "").replace(">", "").strip()
        if not t:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if total + cost > limit:
            break
        out.append(t)
        total += cost
    return out


def upload(project: Path, cfg: dict, privacy: str | None = None, publish_at: str | None = None) -> str:
    """publish_at: ISO8601 (예: 2026-11-10T19:00:00+09:00) → 예약 공개 (privacy 는 private 로 업로드)."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    uc = cfg.get("upload", {})
    script = read_json(project / "script.json")
    video = project / "final.mp4"
    if not video.exists():
        raise RuntimeError("final.mp4 가 없습니다. 먼저 build 하세요.")
    desc_path = project / "description.txt"
    description = desc_path.read_text(encoding="utf-8") if desc_path.exists() else script.get("description", "")
    privacy = privacy or uc.get("privacy", "private")
    status = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": bool(uc.get("made_for_kids", False)),
        "containsSyntheticMedia": bool(uc.get("contains_synthetic_media", False)),
    }
    if publish_at:
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": description[:5000],
            "tags": _trim_tags(script.get("tags", [])),
            "categoryId": str(uc.get("category_id", 27)),
            "defaultLanguage": "ja", "defaultAudioLanguage": "ja",
        },
        "status": status,
    }
    yt = _service(cfg)
    log(f"[upload] {script['title']}  ({status['privacyStatus']}{' → ' + publish_at if publish_at else ''})")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=16 * 1024 * 1024, resumable=True))
    resp, retry = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                log(f"  [upload] {int(st.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < 5:
                retry += 1
                time.sleep(2 ** retry)
                continue
            raise
    vid = resp["id"]
    log(f"[upload] done: https://youtu.be/{vid}")

    thumb = project / "thumbnail.jpg"
    if thumb.exists() and cfg.get("thumbnail", True):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
            log("[upload] thumbnail set")
        except HttpError as e:
            log(f"[upload] thumbnail failed (채널 전화번호 인증이 필요할 수 있음): {e}")

    srt = project / "subtitles.srt"
    if srt.exists() and uc.get("upload_captions", True):
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "ja",
                                                                   "name": "日本語", "isDraft": False}},
                                 media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
            log("[upload] captions uploaded")
        except HttpError as e:
            log(f"[upload] captions failed: {e}")

    write_json(project / "upload.json", {"video_id": vid, "url": f"https://youtu.be/{vid}",
                                         "privacy": status["privacyStatus"], "publish_at": publish_at})
    return vid
