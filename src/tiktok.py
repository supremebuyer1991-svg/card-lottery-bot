"""TikTok に動画を「下書き」として送る（Content Posting API の Upload・受信箱へ。投稿は本人がアプリで曲をのせて行う）

・GitHub の Secret に TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET を入れておく
・最初の1回だけ連携：
    1) python src/tiktok.py url        … 許可のページのアドレスを出す（開いて「許可」→ サイトの tiktok-callback.html にコードが出る）
    2) python src/tiktok.py code コード … コードを鍵（リフレッシュトークン・1年有効）にかえて state/tiktok_meta.json に暗号化して保存
・あとは upload_draft(動画) を呼ぶだけ。鍵は使うたびに新しくなるので、そのつど保存し直す
"""
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

from common import load_json, save_json, log, now

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
REDIRECT = "https://tcg-chusen.com/tiktok-callback.html"
SCOPES = "user.info.basic,video.upload"
# アカウント：TIKTOK_ACCOUNT=gacha のときはガチャプラネット用（鍵の保存先を分ける）。ふだんはトレカ
ACCOUNT = "".join(os.environ.get("TIKTOK_ACCOUNT", "").split()) or "tcg"
META = "tiktok_meta.json" if ACCOUNT == "tcg" else f"tiktok_{ACCOUNT}_meta.json"


def _env(k):
    return "".join(os.environ.get(k, "").split())


def ready():
    return bool(_env("TIKTOK_CLIENT_KEY") and _env("TIKTOK_CLIENT_SECRET") and load_json(META, {}).get("refresh_enc"))


# ---- 鍵の保存（Client secret をもとに暗号化。リポジトリは非公開だが念のため）----
def _xor(data: bytes) -> bytes:
    salt = "tcg-tiktok|" if ACCOUNT == "tcg" else f"{ACCOUNT}-tiktok|"
    k = hashlib.sha256((salt + _env("TIKTOK_CLIENT_SECRET")).encode()).digest()
    stream = b"".join(hashlib.sha256(k + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return bytes(a ^ b for a, b in zip(data, stream))


def _save(tok):
    meta = load_json(META, {})
    meta["refresh_enc"] = base64.b64encode(_xor(tok["refresh_token"].encode())).decode()
    meta["open_id"] = tok.get("open_id") or meta.get("open_id")
    meta["refreshed_at"] = now().isoformat()
    save_json(META, meta)


def _refresh_token():
    enc = load_json(META, {}).get("refresh_enc")
    return _xor(base64.b64decode(enc)).decode() if enc else ""


def auth_url(state=None):
    state = state or ACCOUNT
    return (f"{AUTH_URL}?client_key={quote(_env('TIKTOK_CLIENT_KEY'))}&scope={quote(SCOPES, safe=',')}"
            f"&response_type=code&redirect_uri={quote(REDIRECT, safe='')}&state={state}")


def _token_req(data):
    r = requests.post(TOKEN_URL, data=dict(data, client_key=_env("TIKTOK_CLIENT_KEY"), client_secret=_env("TIKTOK_CLIENT_SECRET")),
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json() if r.content else {}
    if not r.ok or "access_token" not in j:
        raise RuntimeError(f"TikTokの鍵が使えない（{r.status_code} {j.get('error')} {j.get('error_description', '')[:120]}）")
    return j


def connect(code):
    """許可のコード → 鍵。保存して表示名を返す"""
    tok = _token_req({"code": code.strip(), "grant_type": "authorization_code", "redirect_uri": REDIRECT})
    _save(tok)
    r = requests.get("https://open.tiktokapis.com/v2/user/info/?fields=display_name",
                     headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=30)
    name = ((r.json().get("data") or {}).get("user") or {}).get("display_name") if r.ok else None
    log(f"TikTok: 連携できた（{name or 'アカウント名は取れず'}）")
    return name


def _access():
    tok = _token_req({"grant_type": "refresh_token", "refresh_token": _refresh_token()})
    _save(tok)  # リフレッシュトークンは使うたびに変わることがあるので保存し直す
    return tok["access_token"]


def upload_draft(path):
    """動画を TikTok の受信箱（下書き）に送る。publish_id を返す。連携していなければ None"""
    if not ready():
        log("TikTok: 未連携（TIKTOK_CLIENT_KEY・SECRET と連携が必要）なのでスキップ")
        return None
    acc = _access()
    size = Path(path).stat().st_size
    r = requests.post(INIT_URL, headers={"Authorization": f"Bearer {acc}", "Content-Type": "application/json; charset=UTF-8"},
                      data=json.dumps({"source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size,
                                                       "total_chunk_count": 1}}), timeout=30)
    j = r.json() if r.content else {}
    if not r.ok or (j.get("error") or {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: 下書きの準備に失敗 {r.status_code} {json.dumps(j.get('error'), ensure_ascii=False)[:200]}")
    data = j["data"]
    with open(path, "rb") as f:
        r2 = requests.put(data["upload_url"], data=f, timeout=600,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if not r2.ok:
        raise RuntimeError(f"TikTok: 動画の送信に失敗 {r2.status_code} {r2.text[:200]}")
    log(f"TikTok: 下書きに送った {Path(path).name}（アプリの受信箱に届きます）")
    return data.get("publish_id")


CONTENT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"


def upload_photos(urls, title="", description=""):
    """写真（最大35枚）を TikTok の受信箱（下書き）に送る。写真は TikTok が URL から取りに来るので、
    URL のドメイン（例 gachapla.com）を TikTok の開発者ページで「URLプロパティ」として確認しておく必要がある"""
    if not ready():
        log("TikTok: 未連携なのでスキップ")
        return None
    acc = _access()
    body = {"post_info": {"title": title[:90], "description": description[:4000]},
            "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": urls[:35]},
            "post_mode": "MEDIA_UPLOAD", "media_type": "PHOTO"}
    r = requests.post(CONTENT_INIT_URL, headers={"Authorization": f"Bearer {acc}", "Content-Type": "application/json; charset=UTF-8"},
                      data=json.dumps(body, ensure_ascii=False).encode(), timeout=30)
    j = r.json() if r.content else {}
    if not r.ok or (j.get("error") or {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: 写真の下書きに失敗 {r.status_code} {json.dumps(j.get('error'), ensure_ascii=False)[:300]}")
    log(f"TikTok: 写真{len(urls[:35])}枚を下書きに送った（アプリの受信箱に届きます）")
    return (j.get("data") or {}).get("publish_id")


def status(publish_id):
    acc = _access()
    r = requests.post(STATUS_URL, headers={"Authorization": f"Bearer {acc}", "Content-Type": "application/json; charset=UTF-8"},
                      data=json.dumps({"publish_id": publish_id}), timeout=30)
    return r.json()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "url":
        print("このアドレスを開いて「許可」を押してください：")
        print(auth_url())
    elif cmd == "code":
        print("連携できました：", connect(sys.argv[2]))
    elif cmd == "photos":  # python tiktok.py photos social-reel.json（ガチャのスライド）
        d = json.load(open(sys.argv[2], encoding="utf-8"))
        main = [i for i in d["items"] if i["id"] not in set(d.get("kawaii") or [])]
        kw = [i for i in d["items"] if i["id"] in set(d.get("kawaii") or [])]
        line = lambda it: f"・{it['name']}（{it['price']}円）"
        desc = "\n".join([f"{d['title']}（{d['sub']}）", "", *map(line, main), *( ["", f"ラストの{d['word']}が可愛すぎる♡", *map(line, kw)] if kw else []), "",
                          "どれを回したい？コメントで教えてね🪐", "発売日・近くの在庫店はプロフィールのリンクから", "",
                          "#ガチャガチャ #ガチャ #カプセルトイ #新作ガチャ #ガチャ活" + (f" #{d['word']}" if d.get("word") else "")])
        pid = upload_photos(d["slides"], d["title"], desc)
        print("publish_id:", pid)
        if pid:
            import time
            time.sleep(20)
            print(json.dumps(status(pid), ensure_ascii=False)[:500])
    elif cmd == "test":
        pid = upload_draft(sys.argv[2])
        print("publish_id:", pid)
        if pid:
            import time
            time.sleep(15)
            print(json.dumps(status(pid), ensure_ascii=False)[:500])
    else:
        print(__doc__)
