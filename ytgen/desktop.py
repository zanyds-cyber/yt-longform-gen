"""PC 앱 진입점: 로컬 서버를 띄우고 앱 창(pywebview)으로 편집기를 연다.

pywebview 가 없거나 창을 못 띄우면 기본 브라우저로 연다.
YTGEN_NO_WINDOW=1 이면 창 없이 서버만 (테스트용), YTGEN_PORT 로 포트 지정.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

from werkzeug.serving import make_server

from . import web
from .common import data_dir, ffmpeg_ok, load_config, log

APP_NAME = "ytgen Studio"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    cfg = load_config()
    out_root = data_dir() / "output"
    app = web.create_app(cfg, out_root)
    port = int(os.environ.get("YTGEN_PORT") or _free_port())
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # 처음 실행(ffmpeg 없음/키 없음)이면 설정 화면부터
    first = not ffmpeg_ok() or not (data_dir() / ".env").exists()
    url = f"http://127.0.0.1:{port}/" + ("settings" if first else "")
    log(f"{APP_NAME}: {url}  (data: {data_dir()})")

    if os.environ.get("YTGEN_NO_WINDOW"):
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    try:
        import webview  # pywebview
        webview.create_window(APP_NAME, url, width=1440, height=920, min_size=(1000, 680))
        webview.start()
    except Exception as e:  # pywebview 미설치/런타임 없음 → 브라우저
        log(f"앱 창을 열 수 없어 브라우저로 엽니다 ({e})")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
