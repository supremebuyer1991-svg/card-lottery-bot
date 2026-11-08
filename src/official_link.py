"""応募先をニュース記事から公式ページに差し替える（ゲーム・ホビー側）

ニュース（Googleニュース・ゲーム/ホビーのニュースサイト）から拾った抽選は、応募先が記事のURLになりがち。
記事を開いて、中にある公式の応募・商品ページ（プレバンの商品ページなど）へのリンクを探し、
候補のページを開いてタイトルが商品名と合うものを応募先にする。見つからなければ、お店の公式トップにする。
元の記事は source_url に残す（出典）。同じ公式ページになった抽選は1つにまとめる。
1回に調べる数は official_link_per_run まで。調べた結果は state/game/official_links.json に残す（同じ記事は二度調べない）。
"""
import re
import unicodedata
from urllib.parse import urlparse, urljoin

from common import load_json, save_json, now, parse_dt, log

CACHE = "official_links.json"
# 公式（応募・商品ページ）とみなすURL
OFFICIAL = re.compile(
    r"https?://(?:[\w-]+\.)?(?:p-bandai\.jp/item/|p-bandai\.jp/chara/|pokemoncenter-online\.com/|store-jp\.nintendo\.com/|"
    r"1kuji\.com/|gundam-base\.net/|takaratomymall\.jp/|chiikawamarket\.jp/|limited\.yodobashi\.com/|yodobashi\.com/product/|"
    r"biccamera\.com/|joshinweb\.jp/|edion\.com/|geo-online\.co\.jp/|store\.sony\.jp/|direct\.playstation\.com/|"
    r"tamashiiweb\.com/item/|bandai-hobby\.net/item/|amazon\.co\.jp/dp/|books\.rakuten\.co\.jp/rb/|my-nintendo-store|"
    r"nintendo\.co\.jp/|playstation\.com/ja-jp/|sony\.jp/|takaratomy\.co\.jp/|beyblade\.takaratomy|"
    r"bandai\.co\.jp/|bandaispirits\.co\.jp/|lottery|chusen)", re.I)
# 記事の中のリンクのうち、応募先の候補として強いもの（商品そのもののページ）
ITEM_PAGE = re.compile(r"p-bandai\.jp/item/item-\d+|pokemoncenter-online\.com/\d+|store-jp\.nintendo\.com/item/|"
                       r"1kuji\.com/products/|takaratomymall\.jp/shop/g/|chiikawamarket\.jp/products/|tamashiiweb\.com/item/\d+|"
                       r"bandai-hobby\.net/item/\d+|amazon\.co\.jp/dp/|books\.rakuten\.co\.jp/rb/", re.I)
# お店ごとの公式トップ（記事に公式リンクが無かったときの応募先）
STORE_TOP = [
    (r"プレバン|プレミアムバンダイ|p-bandai|BANDAI SPIRITS|バンダイスピリッツ", "https://p-bandai.jp/"),
    (r"魂ウェブ", "https://p-bandai.jp/tamashiiweb/"),
    (r"ガンダムベース|GUNDAM BASE", "https://www.gundam-base.net/"),
    (r"ポケモンセンター|ポケセン", "https://www.pokemoncenter-online.com/"),
    (r"一番くじ", "https://1kuji.com/"),
    (r"タカラトミーモール", "https://takaratomymall.jp/"),
    (r"ちいかわ", "https://chiikawamarket.jp/"),
    (r"マイニンテンドー|Nintendo Store|任天堂", "https://store-jp.nintendo.com/"),
    (r"ソニーストア", "https://store.sony.jp/"),
    (r"ソニー・インタラクティブ|SIE|PlayStation", "https://www.playstation.com/ja-jp/"),
    (r"ヨドバシ", "https://limited.yodobashi.com/"),
    (r"ビックカメラ", "https://www.biccamera.com/"),
]


def is_official(url):
    return bool(url and OFFICIAL.search(url))


def store_top(store):
    for pat, top in STORE_TOP:
        if re.search(pat, store or "", re.I):
            return top
    return ""


def _tokens(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[（(][^）)]*[）)]|【[^】]*】|＜[^＞]*＞|<[^>]*>", " ", s)
    return {t for t in re.split(r"[\s・:：/／\-～〜!！?？「」『』、,]+", s) if len(t) >= 2}


def _score(product, title):
    a, b = _tokens(product), _tokens(title)
    if not a:
        return 0
    hit = sum(1 for t in a if any(t in x or x in t for x in b) or t in (title or "").lower())
    return hit / len(a)


def find_official(article_url, product, fetch, max_open=3):
    """記事を開いて、公式の商品・応募ページを探す。見つからなければ ""。fetch(url)→HTML"""
    from bs4 import BeautifulSoup
    url = article_url
    try:
        import gnews
        if gnews.is_gnews(url):
            url = gnews.decode(url) or ""
        if not url:
            return "", ""
        html = fetch(url)
    except Exception as e:
        log(f"公式リンク探し：記事が読めない {article_url[:60]}: {e}")
        return "", url
    soup = BeautifulSoup(html, "html.parser")
    cands = []
    for a in soup.find_all("a", href=True):
        h = urljoin(url, a["href"]).split("#")[0]
        if ITEM_PAGE.search(h) and h not in [c[0] for c in cands]:
            cands.append((h, a.get_text(" ", strip=True)))
    if not cands:
        return "", url
    if len(cands) == 1:
        return cands[0][0], url
    best, best_sc = "", 0.0
    for h, label in cands[:max_open]:   # 候補が複数（記事の横の「関連記事」など）→ ページを開いてタイトルで照合
        sc = _score(product, label)
        if sc < 0.6:
            try:
                t = re.search(r"<title[^>]*>(.*?)</title>", fetch(h), re.S)
                sc = max(sc, _score(product, t.group(1) if t else ""))
            except Exception:
                pass
        if sc > best_sc:
            best, best_sc = h, sc
    return (best if best_sc >= 0.5 else ""), url


def resolve(settings, lots, fetch):
    """lots の中のニュース由来の応募先を公式に差し替える（lots を書き換える）。差し替えた数を返す"""
    cache = load_json(CACHE, {})
    left = int(settings.get("official_link_per_run", 8))
    t = now()
    changed = 0
    for key, it in lots.items():
        if it.get("status") not in ("new", "approved", "listed", "posted"):
            continue
        u = it.get("url") or ""
        if not u or is_official(u) or it.get("official_checked"):   # もう差し替え済み
            continue
        en = parse_dt(it.get("end"))
        if en and en < t:
            continue
        if u in cache:
            off = cache[u].get("official") or ""
        else:
            if left <= 0:
                continue
            left -= 1
            off, real = find_official(u, it.get("product") or "", fetch)
            cache[u] = {"official": off, "article": real, "at": t.isoformat()}
        art = cache[u].get("article") or u
        new = off or store_top(it.get("store")) or ""
        if new:
            it["source_url"] = art
            it["official_checked"] = True
            it["url"] = new
            changed += 1
            log(f"応募先を公式に：{(it.get('product') or '')[:30]} → {new}")
    # 同じ公式の商品ページになったものは1つにまとめる（締切が分かっている方・早く見つけた方を残す）
    seen = {}
    for key, it in sorted(lots.items(), key=lambda kv: (not kv[1].get("end"), kv[1].get("found_at") or "")):
        u = it.get("url") or ""
        if it.get("status") in ("approved", "listed", "posted") and ITEM_PAGE.search(u):
            if u in seen:
                it["status"] = "duplicate"
                it["dup_of"] = seen[u]
                log(f"同じ公式ページなのでまとめる：{(it.get('product') or '')[:30]}")
            else:
                seen[u] = key
    # 公式の商品ページが分かった抽選と、商品名がほぼ同じ抽選（応募先がお店のトップ・ニュースのまま）もまとめる
    items = [(k, i) for k, i in lots.items() if i.get("status") in ("approved", "listed", "posted")]
    for k, i in items:
        if ITEM_PAGE.search(i.get("url") or "") or i.get("kind") == "release":
            continue
        for k2, j in items:
            if k2 != k and j.get("status") != "duplicate" and ITEM_PAGE.search(j.get("url") or "") \
                    and j.get("kind") == i.get("kind") and min(_score(i.get("product"), j.get("product")), _score(j.get("product"), i.get("product"))) >= 0.6:
                i["status"], i["dup_of"] = "duplicate", k2
                log(f"商品名が同じなのでまとめる：{(i.get('product') or '')[:30]}")
                break
    save_json(CACHE, cache)
    return changed
