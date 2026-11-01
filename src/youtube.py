"""YouTube に動画を上げる（YouTube Data API v3・無料。1日のアップロードは100回まで）

・GitHub の Secret に YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN を入れると動く（無ければ何もしない）
・publish_at を渡すと「予約公開」（その時刻まで非公開→自動で公開）
・同じ動画を二度上げないよう、上げたものは state/youtube.json に残す
"""
import json
import os
from pathlib import Path

import requests

from common import load_json, save_json, log, now

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


def _env(k):
    return "".join(os.environ.get(k, "").split())


def ready():
    return all(_env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def _token():
    r = requests.post(TOKEN_URL, data={"client_id": _env("YT_CLIENT_ID"), "client_secret": _env("YT_CLIENT_SECRET"),
                                       "refresh_token": _env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"YouTubeの鍵が使えない（{r.status_code} {r.text[:120]}）")
    return r.json()["access_token"]


def upload(path, title, description, tags=(), publish_at=None, key=None):
    """動画を上げて動画IDを返す。鍵が無い・上げ済みなら None"""
    if not ready():
        log("YouTube: 鍵（YT_CLIENT_ID など）が未登録なのでスキップ")
        return None
    st = load_json("youtube.json", {})
    done = st.setdefault("done", {})
    if key and key in done:
        log(f"YouTube: 上げ済み {key}")
        return None
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if publish_at:
        status = {"privacyStatus": "private", "publishAt": publish_at, "selfDeclaredMadeForKids": False}
    meta = {"snippet": {"title": title[:100], "description": description[:4900], "tags": list(tags)[:15],
                        "categoryId": "20", "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": status}
    tok = _token()
    size = Path(path).stat().st_size
    r = requests.post(UPLOAD_URL, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                                           "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                      data=json.dumps(meta, ensure_ascii=False).encode("utf-8"), timeout=60)
    if not r.ok:
        raise RuntimeError(f"YouTube: アップロードの準備に失敗 {r.status_code} {r.text[:200]}")
    with open(path, "rb") as f:
        r2 = requests.put(r.headers["Location"], headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"},
                          data=f, timeout=600)
    if not r2.ok:
        raise RuntimeError(f"YouTube: アップロード失敗 {r2.status_code} {r2.text[:200]}")
    vid = r2.json().get("id")
    log(f"YouTube: 上げた https://youtube.com/shorts/{vid} {title}")
    if key:
        done[key] = {"id": vid, "at": now().isoformat()}
        st["done"] = dict(list(done.items())[-200:])
        save_json("youtube.json", st)
    return vid
