"""まとめブログのページから、そのお店の「公式の応募ページ（またはお店の告知ポスト）」のリンクを探す

まとめブログはお店ごとに見出しや段落があり、その近くに公式の応募ページやお店のXのポストへのリンクを貼っている。
・お店の名前が出てくる段落（または見出し）を探し、そこから先の数段落の中で最初の「外のリンク」を使う
・ブログ自身・広告（Amazon・楽天など）・共有ボタンのリンクは使わない
・見つからなければ None（そのときは応募ボタンを出さない）
"""
import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

SKIP_HOSTS = ("amazon.", "amzn.", "rakuten.", "shopping.yahoo", "yahoo.co.jp", "a8.net", "moshimo", "valuecommerce",
              "linksynergy", "afl.rakuten", "accesstrade", "facebook.com", "line.me", "b.hatena", "getpocket",
              "pinterest", "google.com/search", "youtube.com", "instagram.com/explore", "t.co")
STORE_ALIAS = {"ふるいち": "古本市場", "ツタヤ": "tsutaya", "電機": "デンキ", "ヨドバシカメラ": "ヨドバシ", "トイザらス": "トイザラス"}
BLOCKS = ("h1", "h2", "h3", "h4", "h5", "p", "li", "td", "th", "dt", "dd", "blockquote", "figcaption")


def _norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    for a, b in STORE_ALIAS.items():
        s = s.replace(a.lower(), b.lower())
    return re.sub(r"[\s・\-_/｜|]", "", s)


def _names(store):
    """探すお店の名前（長い順）：そのまま・カッコを外したもの・「通販」「店」を外したもの"""
    s = unicodedata.normalize("NFKC", store or "")
    out = [s, re.sub(r"[（(][^）)]*[）)]", "", s)]
    out += [re.sub(r"(通販|オンラインショップ|オンライン|公式)$", "", x.strip()) for x in list(out)]
    out += [m for x in list(out) for m in re.findall(r"[（(]([^）)]+)[）)]", x)]  # 「ふるいち（古本市場）」の中身も
    ns = []
    for x in out:
        n = _norm(x)
        if len(n) >= 3 and n not in ns:
            ns.append(n)
    return sorted(ns, key=len, reverse=True)


def _ok(href, blog_host, blogs):
    if not re.match(r"https?://", href or ""):
        return False
    u = urlparse(href)
    host = u.netloc.lower().removeprefix("www.")
    if not host or host == blog_host or host.endswith("." + blog_host):
        return False
    if any(host == b or host.endswith("." + b) for b in blogs):
        return False
    full = host + u.path
    if any(x in full for x in SKIP_HOSTS):
        return False
    if re.fullmatch(r"/?((about|company|access|shop|shops|store|stores|recruit|info|top|index\.html?)/?)?", u.path.lower()) and not u.query:
        return False  # トップページ・会社案内などは応募ページではない
    if host in ("x.com", "twitter.com") and "/status/" not in u.path:
        return False  # 共有ボタン・プロフィールは使わない（お店の告知ポストだけ）
    return True


_CACHE = {}


def _blocks(html):
    """ページを段落ごとに分ける（同じページは1回だけ）"""
    k = hash(html)
    if k in _CACHE:
        return _CACHE[k]
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    blocks = []
    for el in soup.find_all(BLOCKS):
        if el.find(BLOCKS):  # 中に段落を持つもの（外側の li など）は中身のほうで見る
            if el.name not in ("li", "td"):
                continue
        links = [a.get("href") for a in el.find_all("a", href=True)]
        blocks.append((el.name, _norm(el.get_text(" ")), links))
    _CACHE[k] = blocks
    return blocks


def find_link(html, page_url, store, blogs=()):
    blog_host = urlparse(page_url).netloc.lower().removeprefix("www.")
    blocks = _blocks(html)
    for name in _names(store):
        for i, (tag, text, _) in enumerate(blocks):
            if name not in text:
                continue
            heading = tag.startswith("h")
            for j in range(i, min(len(blocks), i + (15 if heading else 6))):
                tag2, _, links = blocks[j]
                if j > i and tag2.startswith("h") and (not heading or tag2 <= tag):
                    break  # 次のお店の見出しまで
                good = [h for h in links if _ok(h, blog_host, blogs)]
                if good:
                    # 公式ページ（Xのポスト以外）があればそちらを優先
                    return next((h for h in good if not re.search(r"//(www\.|mobile\.)?(x|twitter)\.com/", h)), good[0])
    return None
