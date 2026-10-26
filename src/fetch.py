"""ページ取得（アクセスは控えめに：1ソース1リクエスト、UA明示）"""
import re
import time
from hashlib import sha256
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; CardLotteryBot/1.0; +info-collector)"


def get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ja"}, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    time.sleep(2)  # 連続アクセスしない
    return r.text


def html_to_text(html: str, base_url: str = "") -> str:
    """本文テキスト＋リンク一覧を返す（AIが抽選ページのURLを拾えるように）"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    links = []
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label and any(k in label for k in ("抽選", "予約", "応募", "販売", "発売", "こちら", "公式", "詳細")):
            href = requests.compat.urljoin(base_url, a["href"])
            links.append(f"- {label} -> {href}")
    if links:
        text += "\n\n[関連リンク]\n" + "\n".join(dict.fromkeys(links))
    return text


def parse_rss(xml: str) -> list:
    items = []
    root = ET.fromstring(xml)
    for it in root.iter("item"):
        items.append({
            "guid": (it.findtext("guid") or it.findtext("link") or "").strip(),
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "date": (it.findtext("pubDate") or "").strip(),
            "summary": BeautifulSoup(it.findtext("description") or "", "html.parser").get_text(" ", strip=True),
        })
    return items


def article_links(html: str, base_url: str, keywords: list, limit: int = 10) -> list:
    """一覧ページから、キーワードを含む記事リンクを拾う（同じサイト内のみ）"""
    soup = BeautifulSoup(html, "html.parser")
    host = requests.compat.urlparse(base_url).netloc
    out = []
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        href = requests.compat.urljoin(base_url, a["href"]).split("#")[0]
        if (requests.compat.urlparse(href).netloc == host and href.rstrip("/") != base_url.rstrip("/")
                and any(k in label for k in keywords) and href not in out):
            out.append(href)
    return out[:limit]


COUNTDOWN = re.compile(r"残り\s*\d+\s*(日|時間|分|秒)|あと\s*\d+\s*(日|時間|分)")


def cards(html: str, base_url: str, link_text: str = "応募") -> list:
    """一覧型サイト用：応募ボタン1つごとに、そのボタンを含む「カード」のテキストを切り出す
    戻り値: [(キー=応募URL, 正規化テキストのハッシュ, テキスト)]"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    host = requests.compat.urlparse(base_url).netloc
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if link_text not in a.get_text(" ", strip=True):
            continue
        href = requests.compat.urljoin(base_url, a["href"])
        if requests.compat.urlparse(href).netloc == host or href in seen:
            continue  # 外部の応募先だけ（サイト内リンクは除外）
        seen.add(href)
        box = a
        # 応募ボタンを1つだけ含む、いちばん外側の要素まで広げる＝そのカード
        while box.parent is not None and box.parent.name not in ("body", "html", "[document]"):
            n = len({requests.compat.urljoin(base_url, x["href"]) for x in box.parent.find_all("a", href=True)
                     if link_text in x.get_text(" ", strip=True)
                     and requests.compat.urlparse(requests.compat.urljoin(base_url, x["href"])).netloc != host})
            if n > 1:
                break
            box = box.parent
        text = " / ".join(t for t in box.get_text("\n", strip=True).splitlines() if t)
        text = f"{text}\n応募URL: {href}"
        out.append((href, sha256(COUNTDOWN.sub("", text).encode()).hexdigest()[:16], text))
    return out
