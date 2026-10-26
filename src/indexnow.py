"""IndexNow：サイトの更新を Bing などの検索エンジンにすぐ知らせる（Googleはサイトマップで拾う）
ワークフローでサイトを公開した直後に実行する。python src/indexnow.py
"""
import os
import re

import requests

from common import ROOT, load_settings, log


def main():
    s = load_settings()
    key = s.get("indexnow_key")
    site = (os.environ.get("SITE_URL") or s.get("site_public_url") or "").rstrip("/")
    sm = ROOT / "site" / "sitemap.xml"
    if not key or not site or not sm.exists():
        return
    urls = re.findall(r"<loc>(.*?)</loc>", sm.read_text(encoding="utf-8"))[:10000]
    host = re.sub(r"^https?://", "", site).split("/")[0]
    r = requests.post("https://api.indexnow.org/indexnow", timeout=30, json={
        "host": host, "key": key, "keyLocation": f"{site}/{key}.txt", "urlList": urls})
    log(f"IndexNow: {len(urls)}件を送信 → {r.status_code}")


if __name__ == "__main__":
    main()
