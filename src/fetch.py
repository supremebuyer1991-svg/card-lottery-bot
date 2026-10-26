"""ページ取得（アクセスは控えめに：1ソース1リクエスト、UA明示）"""
import json
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


EXCLUDE_LINK = ("方法", "詳細", "みる", "見る", "確認")


def _is_apply(label: str, link_text: str) -> bool:
    """「抽選に応募する！」のような応募ボタンだけを対象にする（「応募方法をみる」は除外）"""
    return link_text in label and not any(x in label for x in EXCLUDE_LINK)


def product_of(box, base_url: str, host: str) -> str:
    """そのカードの商品名を探す。カードの中 → 直前の商品見出し（商品ページへのリンクや画像）の順"""
    base_path = requests.compat.urlparse(base_url).path.rstrip("/")

    def is_product_link(t):
        if t.name != "a" or not t.get("href"):
            return False
        u = requests.compat.urlparse(requests.compat.urljoin(base_url, t["href"]))
        p = u.path.rstrip("/")
        return u.netloc == host and p.startswith(base_path + "/") and p.count("/") == base_path.count("/") + 1

    def name_of(a):
        label = a.get_text(" ", strip=True)
        img = a.find("img")
        alt = img.get("alt", "").strip() if img else ""
        slug = requests.compat.urlparse(a["href"]).path.rstrip("/").split("/")[-1]
        return " ".join(x for x in (label, alt) if x) or slug

    inside = box.find(is_product_link)
    if inside:
        return name_of(inside)
    prev = box.find_previous(is_product_link)
    if prev:
        return name_of(prev)
    img = box.find_previous("img", alt=True)
    return img.get("alt", "").strip() if img else ""


def cards(html: str, base_url: str, link_text: str = "応募") -> list:
    """一覧型サイト用：応募ボタン1つごとに、そのボタンを含む「カード」のテキストを切り出す
    戻り値: [(キー=応募URL, 正規化テキストのハッシュ, テキスト)]"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    host = requests.compat.urlparse(base_url).netloc

    def apply_links(node):
        out = set()
        for x in node.find_all("a", href=True):
            href = requests.compat.urljoin(base_url, x["href"])
            if _is_apply(x.get_text(" ", strip=True), link_text) and requests.compat.urlparse(href).netloc != host:
                out.add(href)
        return out

    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if not _is_apply(a.get_text(" ", strip=True), link_text):
            continue
        href = requests.compat.urljoin(base_url, a["href"])
        if requests.compat.urlparse(href).netloc == host or href in seen:
            continue  # 外部の応募先だけ（サイト内リンクは除外）
        seen.add(href)
        box = a
        # 応募ボタンを1つだけ含む、いちばん外側の要素まで広げる＝そのカード
        while box.parent is not None and box.parent.name not in ("body", "html", "[document]"):
            if len(apply_links(box.parent)) > 1:
                break
            box = box.parent
        text = " / ".join(t for t in box.get_text("\n", strip=True).splitlines() if t)
        prod = product_of(box, base_url, host)
        text = (f"商品: {prod}\n" if prod else "") + f"{text}\n応募URL: {href}"
        out.append((href, sha256(COUNTDOWN.sub("", text).encode()).hexdigest()[:16], text))
    return out


def cardchusen_items(html: str, base_url: str) -> list:
    """cardchusen.com 専用：各抽選カードに埋め込まれた整理済みデータをそのまま読む（AI不要）
    戻り値: [(キー, ハッシュ, 抽選データ)]"""
    from sitegen import PREF
    romaji = {v: k for k, v in PREF.items()}
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.select("article.board-card[data-entry-end]"):
        cta = art.select_one("a.board-card__cta[href]")
        store_el = art.select_one(".board-card__store")
        if not cta or not store_el:
            continue
        url = requests.compat.urljoin(base_url, cta["href"])
        media = art.select_one(".board-card__media")
        label = (media.get("aria-label", "") if media else "").replace("のパック情報を見る", "").strip()
        official = (store_el.get("title") or "").strip()
        series = label if label and len(label) <= 24 else None
        conds = [c.get_text(strip=True) for c in art.select(".board-cond__txt")]
        areas = [romaji[a] for a in (art.get("data-area") or "").split() if a in romaji]
        kind = art.get("data-lottery-type") or "online"
        channel = "store" if kind == "store" or (kind == "other" and len(areas) == 1) else "online"
        method = art.select_one(".board-card__method")
        cond_txt = "・".join(conds) if conds else None
        if len(areas) > 1:
            cond_txt = ((cond_txt + " ／ ") if cond_txt else "") + "対象地域：" + "・".join(areas)
        item = {
            "store": store_el.get_text(strip=True),
            "product": official or label or series,
            "series": series,
            "end": art["data-entry-end"],
            "url": url,
            "x_post": url if "x.com/" in url and "/status/" in url else None,
            "channel": channel,
            "area": areas[0] if len(areas) == 1 else None,
            "method": method.get_text(strip=True) if method else None,
            "conditions": cond_txt,
            "tags": conds,
            "id_check": "本人確認" in conds,
            "member": ("card" if channel == "store" else "account") if "会員" in conds else "none",
            "confidence": 0.95,
        }
        if not item["product"]:
            continue
        key = art.get("id") or url
        h = sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        out.append((key, h, item))
    return out
