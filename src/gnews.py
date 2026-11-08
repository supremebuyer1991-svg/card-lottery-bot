"""Googleニュースの記事リンク（news.google.com/rss/articles/…）を、元の記事のURLに直す。
Googleニュースのリンクのままだと記事の本文が読めず、応募先（プレバンの商品ページなど）も拾えないため。
失敗したら None（呼び出し側はRSSのタイトル・要約だけで続ける）"""
import json
import re
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def is_gnews(url):
    return bool(re.match(r"https?://news\.google\.com/(rss/)?articles/", url or ""))


def decode(url, session=None):
    import requests
    s = session or requests
    m = re.search(r"/articles/([^?/#]+)", url or "")
    if not m:
        return None
    gid = m.group(1)
    try:
        html = s.get(f"https://news.google.com/rss/articles/{gid}", headers={"User-Agent": UA}, timeout=(6, 12)).text
        sg = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not (sg and ts):
            return None
        req = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                         f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sg.group(1)}"]']
        r = s.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                   headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                   data=f"f.req={quote(json.dumps([[req]]))}", timeout=(6, 12))
        body = r.text.split("\n\n", 1)[1]
        parsed = json.loads(body)[:-2]
        real = json.loads(parsed[0][2])[1]
        return real if isinstance(real, str) and real.startswith("http") else None
    except Exception:
        return None
