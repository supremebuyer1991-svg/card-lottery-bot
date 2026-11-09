"""probe-game.yml から呼ぶ：URLが読めるか（状態・文字数・タイトル・本文の頭・プレバン等のリンク数）を記録に出す"""
import os, re, sys
sys.path.insert(0, "src")
os.environ.setdefault("SITE", "game")
import requests
from fetch import get, html_to_text, parse_rss
import gnews

urls = os.environ.get("URLS", "").split()
if not urls:
    xml = get("https://news.google.com/rss/search?q=%E3%83%97%E3%83%AC%E3%83%90%E3%83%B3+%E6%8A%BD%E9%81%B8+when:7d&hl=ja&gl=JP&ceid=JP:ja")
    items = parse_rss(xml)[:4]
    for it in items:
        real = gnews.decode(it["link"])
        print("GNEWS", it["title"][:50], "->", real)
        if real:
            urls.append(real)
import jpfetch
for u in urls:
    try:
        body = None
        if "##" in u:   # 「URL##a=1&b=2」は POST で送る（検索フォームで動くお店用）
            u, body = u.split("##", 1)
        if os.environ.get("VIA") == "jp":
            u0 = u
            u = jpfetch.url(u)
        r = (requests.post(u, data=body.encode(), headers={"Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}, timeout=(6, 15)) if body is not None else requests.get(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept-Language": "ja"}, timeout=(6, 15)))
        r.encoding = r.apparent_encoding or r.encoding
        t = html_to_text(r.text, u) if "<rss" not in r.text[:500] else r.text
        title = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S)
        pb = sorted(set(re.findall(r"https?://p-bandai\.jp/item/[^\s\"'<>\]]+", r.text)))[:5]
        print(f"YEN {t.count('円')}")
        print(f"=== {u}\n  status={r.status_code} html={len(r.text)} text={len(t)} title={(title.group(1).strip()[:60] if title else '')}")
        print("  head:", re.sub(r"\s+", " ", t[:int(os.environ.get("HEAD", "400"))]))
        if pb:
            print("  p-bandai:", pb)
        if os.environ.get("LINKS", "").startswith("raw:"):   # HTMLの中身をそのまま探す（JavaScriptで動くメニューのURL探し）
            for m in list(re.finditer(os.environ["LINKS"][4:], r.text))[:60]:
                print("  raw:", re.sub(r"\s+", " ", r.text[max(0, m.start() - 80):m.end() + 120]))
        elif os.environ.get("LINKS"):
            from bs4 import BeautifulSoup
            seen = []
            for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
                h = requests.compat.urljoin(u, a["href"]); lab = a.get_text(" ", strip=True)[:40]
                if re.search(os.environ["LINKS"], h + " " + lab) and h not in seen:
                    seen.append(h); print("  link:", h, "|", lab)
                if len(seen) >= 40:
                    break
    except Exception as e:
        print(f"=== {u}\n  ERROR {e}")
