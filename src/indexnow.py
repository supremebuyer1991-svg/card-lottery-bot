"""IndexNow：サイトの更新を Bing などの検索エンジンにすぐ知らせる（Googleはサイトマップで拾う）
ワークフローでサイトを公開した直後に実行する。python src/indexnow.py
"""
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from common import ROOT, load_settings, log


def main():
    s = load_settings()
    key = s.get("indexnow_key")
    site = (s.get("site_public_url") or os.environ.get("SITE_URL") or "").rstrip("/")
    sms = sorted((ROOT / "site").glob("sitemap-*.xml")) or [ROOT / "site" / "sitemap.xml"]
    if not key or not site or not sms[0].exists():
        return
    # 11/7：今日中身が変わったページだけ送る（毎回全部送ると「送りすぎ」になる）
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    urls = [u for f in sms for u, lm in re.findall(r"<loc>(.*?)</loc><lastmod>(.*?)</lastmod>", f.read_text(encoding="utf-8")) if lm >= today][:10000]
    if not urls:
        log("IndexNow: 今日変わったページなし")
        return
    host = re.sub(r"^https?://", "", site).split("/")[0]
    r = requests.post("https://api.indexnow.org/indexnow", timeout=30, json={
        "host": host, "key": key, "keyLocation": f"{site}/{key}.txt", "urlList": urls})
    log(f"IndexNow: {len(urls)}件を送信 → {r.status_code}")


if __name__ == "__main__":
    main()
