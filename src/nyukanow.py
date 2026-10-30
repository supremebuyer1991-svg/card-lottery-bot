"""入荷Now（nyuka-now.com）の「〇〇の抽選予約・在庫・再販情報まとめ」記事を、AIを使わずに読む

記事はお店ごとに見出し（受付中／近日開始／終了のラベル付き）があり、その下に更新日ごとの表
（対象商品・抽選形式・開始日・終了日・当選発表・応募条件・詳細ページ）が並んでいる。
・受付中／近日開始のお店だけ、締切が過ぎていない表を読む（先着販売などの抽選でないものは読まない）
・入荷Nowの文章（応募条件の文）はそのまま載せない。価格・購入期間・本人確認・会員など事実だけを取り出す
  （条件の文はあとで応募ページから自分の言葉でまとめる：pagecheck.fill_details）
・リンクはアフィリエイトを外して、お店のページのURLにする
"""
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
UNWRAP = ("pc", "vcurl", "goods_url", "a8ejpredirect", "url")
OPEN = re.compile(r"受付中|近日開始|開始予定|予告")


def unwrap(href):
    """アフィリエイトのリンク（楽天・バリューコマース・A8・もしも・駿河屋）から、お店のページのURLを取り出す"""
    if not href:
        return None
    p = urlsplit(href)
    host = p.netloc.lower()
    if re.search(r"afl\.rakuten|valuecommerce|a8\.net|moshimo|af_jump|affiliate\.", host + p.path):
        q = parse_qs(p.query)
        for k in UNWRAP:
            if q.get(k) and q[k][0].startswith("http"):
                return unwrap(q[k][0])
        return None  # 中身の分からないアフィリエイト（trafficgate など）は使わない
    if "trafficgate" in host:
        return None
    if "amazon." in host:
        href = re.sub(r"([?&])tag=[^&]*&?", r"\1", href).rstrip("?&")  # 入荷Nowのタグは外す（サイト側で自分のタグを付ける）
    return href


def _dt(s, base):
    """「10月29日(木)12:00」「11/4(水)頃」→ datetime（年は更新日から。更新日より半年以上前の月なら翌年）"""
    m = re.search(r"(\d{1,2})\s*[月/]\s*(\d{1,2})\s*日?", s or "")
    if not m:
        return None
    t = re.search(r"(\d{1,2})[:：時](\d{2})?", s[m.end():])
    hh, mm = (int(t.group(1)), int(t.group(2) or 0)) if t else (23, 59)
    y = base.year
    try:
        d = date(y, int(m.group(1)), int(m.group(2)))
        if d < base - timedelta(days=180):
            d = date(y + 1, d.month, d.day)
        return datetime(d.year, d.month, d.day, min(hh, 23), mm if hh < 24 else 59, tzinfo=JST)
    except ValueError:
        return None


def _facts(cond):
    """応募条件の文から事実だけ（文はそのまま使わない）"""
    c = cond or ""
    tags, f = [], {}
    if re.search(r"本人確認|身分証|顔写真|マイナンバー|運転免許", c):
        tags.append("本人確認")
        f["id_check"] = True
    if re.search(r"アプリ", c):
        tags.append("アプリ")
    if re.search(r"会員|アカウント|プレイヤーズクラブ|ID", c):
        tags.append("会員")
        f["member"] = "card" if re.search(r"会員(カード|証)|ポイントカード", c) else "account"
    if re.search(r"購入(履歴|実績|歴)|利用(履歴|実績)|売買|買取", c):
        tags.append("購入履歴")
    if re.search(r"レシート", c):
        tags.append("レシート")
    m = re.search(r"(購入|受取|受け取り|引換|引き換え)期間\s*[:：]?\s*([0-9０-９/／月日()（）〜～\-\s:：時土日月火水木金]{5,40})", c)
    if m:
        f["buy"] = re.sub(r"\s+", "", m.group(2)).strip("、，,")
    prices = re.findall(r"([0-9,]{4,7})\s*円", c)
    if prices:
        f["price"] = "・".join(dict.fromkeys(p + "円" for p in prices))
    f["tags"] = tags
    return f


def _cells(table):
    out = {}
    for tr in table.select("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            out[th.get_text(strip=True)] = td
    return out


def items(html, page_url, now=None):
    """記事から受付中・近日開始の抽選を読む。戻り値: [(キー, ハッシュ, 抽選データ)]"""
    import json
    from hashlib import sha256
    now = now or datetime.now(JST)
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.find("h1") or soup.find("title"))
    title = title.get_text(" ", strip=True) if title else ""
    game = "onepiece" if re.search(r"ワンピース|ONE ?PIECE", title, re.I) else "dragonball" if re.search(r"フュージョンワールド|ドラゴンボール", title) else "pokemon"
    m = re.search(r"(?:ポケモンカード|ワンピースカード|ONE PIECEカード|ワンピカード)\s*(.+?)の抽選", title)
    title_series = m.group(1).strip() if m else None
    out = []
    for h3 in soup.find_all("h3"):
        lab = h3.find("span")
        status = lab.get_text(strip=True) if lab else ""
        if not OPEN.search(status):
            continue
        store = h3.get_text(" ", strip=True).replace(status, "").strip()
        shop_only = bool(re.search(r"[（(]店舗[）)]", store))
        store = re.sub(r"\s*[（(]店舗[）)]", "", store).strip()  # 「フルコンプ（店舗）」→「フルコンプ」（店頭抽選として扱う）
        box = h3.find_parent("dt")
        box = box.find_next_sibling("dd") if box else h3.parent
        if not box:
            continue
        base = now.date()
        for el in box.find_all(["h4", "table"]):
            if el.name == "h4":
                d = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", el.get_text())
                if d:
                    base = date(int(d.group(1)), int(d.group(2)), int(d.group(3)))
                continue
            c = _cells(el)
            kind = c["抽選形式"].get_text(" ", strip=True) if "抽選形式" in c else ""
            if "抽選" not in kind:
                continue  # 先着販売・在庫情報などは抽選ではない
            end = _dt(c["終了日"].get_text(" ", strip=True), base) if "終了日" in c else None
            if end and end < now:
                continue
            start = _dt(c["開始日"].get_text(" ", strip=True), base) if "開始日" in c else None
            if not start and not end:
                continue  # 「12月頃に開始予定」のような予告だけの表は載せない
            prods = [li.get_text(" ", strip=True) for li in c["対象商品"].find_all("li")] if "対象商品" in c else []
            if not prods and "対象商品" in c:
                prods = [c["対象商品"].get_text(" ", strip=True)]
            prods = [re.sub(r"^(ポケモンカード|ワンピースカード|ONE PIECEカードゲーム)\s*", "", p) for p in prods if p]
            sers = []  # 商品ごとの弾名
            for p_ in prods:  # 弾名はサイトで使っている名前にそろえる（「30th CELEBRATION BOX」→「30th CELEBRATION」）
                try:
                    from sitegen import guess_series
                    g_ = guess_series(game, p_)
                except Exception:
                    g_ = None
                sers.append(g_ or p_)
            link = None
            for f_ in ("応募ページ", "詳細ページ"):
                a = c[f_].find("a", href=True) if f_ in c else None
                if a and not link:
                    link = unwrap(a["href"])
            ann = c["当選発表"].get_text(" ", strip=True) if "当選発表" in c else None
            facts = _facts(c["応募条件"].get_text(" ", strip=True) if "応募条件" in c else "")
            in_store = bool(re.search(r"店頭|店舗", kind)) and not re.search(r"発送|配送|通販", kind)
            if shop_only:
                in_store = True
            base_item = {
                "store": store,
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "announce": ann if ann and ann not in ("-", "未定", "なし") else None,
                "buy": facts.get("buy"),
                "method": kind or None,
                "url": link,
                "x_post": link if link and re.search(r"(x|twitter)\.com/[^/]+/status/", link) else None,
                "game": game,
                "channel": "store" if in_store else "online",
                "id_check": facts.get("id_check"),
                "member": facts.get("member"),
                "tags": facts["tags"],
                "confidence": 0.9 if link and end else 0.6,
            }
            # 商品ごとに1件（ほかの情報元も商品ごとなので、同じ抽選としてまとめやすい）
            for p_, s_ in (zip(prods, sers) if prods else [(title_series, title_series)]):
                if not p_:
                    continue
                item = dict(base_item, product=p_, series=s_)
                key = f"{page_url}#{store}#{s_}#{item['end'] or item['start'] or base}"
                h = sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
                out.append((key, h, item))
    return out
