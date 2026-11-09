"""日本の買取店のページを、Cloudflare の中継（worker/jp-fetch）経由で読む。
GitHub のサーバー（海外）からだと断られるお店があるため。鍵は Cloudflare のアカウントIDから作る（中継の公開時と同じ作り方）"""
import hashlib
import os
from urllib.parse import quote

BASE = "https://jp-fetch.supreme-buyer-1991.workers.dev/"


def key():
    seed = "".join((os.environ.get("JPFETCH_SEED") or "").split()).strip('"')
    return hashlib.sha256((seed + "jp-fetch").encode()).hexdigest()[:24] if seed else ""


def url(target):
    return f"{BASE}?k={key()}&u={quote(target, safe='')}"


def get(target, timeout=(6, 20)):
    """「URL##a=1&b=2」と書いたら POST で送る（検索フォームで動くお店：モバイル一番など）"""
    import requests
    if "##" in target:
        target, body = target.split("##", 1)
        r = requests.post(url(target), data=body.encode(), timeout=timeout,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    else:
        r = requests.get(url(target), timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text
