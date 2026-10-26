"""自作サイトの書き出し：state/lotteries.json → site/
  python src/sitegen.py            本番データで site/ を作る
  python src/sitegen.py --sample   サンプルデータで output/site_preview.html を作る（見た目確認用）

作るページ（すべて静的HTML。検索エンジン向けに一覧の文字も最初から埋め込む）
  /                                トップ（ポケカを表示）
  /pokeka/  /onepiece/  /fusionworld/     ゲーム別
  /pokeka/s-xxxxxxxx/              弾ごと（「〇〇 抽選」で検索されるページ）
  /pokeka/area/osaka/              都道府県ごとの店頭抽選（「ポケカ 抽選 大阪」）
  /sitemap.xml  /robots.txt
"""
import json
import os
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

from common import ROOT, load_json, save_json, load_settings, now, parse_dt, sha, normalize

TEMPLATE = Path(__file__).with_name("site_template.html")
ACTIVE = ("approved", "posted", "listed")
FIELDS = ("key", "game", "store", "product", "series", "end", "conditions", "tags", "url",
          "channel", "area", "found_at", "id_check", "member", "image", "img_url", "multi", "method")
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}
GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピカード", "dragonball": "フュージョンワールド"}
PREF = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi", "秋田県": "akita",
    "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki", "栃木県": "tochigi", "群馬県": "gunma",
    "埼玉県": "saitama", "千葉県": "chiba", "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata",
    "富山県": "toyama", "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie", "滋賀県": "shiga",
    "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo", "奈良県": "nara", "和歌山県": "wakayama",
    "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama", "広島県": "hiroshima", "山口県": "yamaguchi",
    "徳島県": "tokushima", "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi", "福岡県": "fukuoka",
    "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita", "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}
WEEK = "月火水木金土日"


def load_images() -> dict:
    """config/images.yaml：弾名 → 商品画像URL"""
    import yaml
    p = ROOT / "config" / "images.yaml"
    if not p.exists():
        return {}
    return {k: v for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).items() if v}


def series_path(game, series):
    return f"{GAME_SLUG[game]}/s-{sha(normalize(series))[:8]}/"


def _fmt(s):
    dt = parse_dt(s)
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}) {dt:%H:%M}" if dt else "締切 要確認"


def prerender(items) -> str:
    """JSが動く前（＝検索エンジンが最初に読む）一覧。JSが動くと本来の表示に置き換わる"""
    if not items:
        return '<div class="empty">現在受付中の抽選はありません。</div>'
    out = []
    for ch, title in (("online", "ネット抽選（当選後に発送）"), ("store", "店頭抽選（受け取りは店頭）")):
        rows = []
        for i in sorted([i for i in items if (i.get("channel") == "store") == (ch == "store")],
                        key=lambda x: x.get("end") or "9999")[:150]:
            where = f"［{i['area']}］" if ch == "store" and i.get("area") else ""
            dt = parse_dt(i.get("end"))
            when = f'<time datetime="{dt.isoformat()}">{_fmt(i.get("end"))}</time>' if dt else "締切 要確認"
            link = f' <a href="{escape(i["url"])}" rel="nofollow noopener">応募ページ</a>' if i.get("url") else ""
            rows.append(f"<li><b>{escape(where + i['store'])}</b> {escape(i.get('product') or '')} ／ 締切 {when}{link}</li>")
        if rows:
            out.append(f'<h2>{title}</h2><ul class="pre">{"".join(rows)}</ul>')
    return "".join(out)


def page(data: dict, meta: dict, standalone=True) -> str:
    base = meta.get("root", "/")
    canon = meta.get("canonical")
    site = meta.get("site", "")
    head = []
    if canon:
        head += [f'<link rel="canonical" href="{escape(canon)}">',
                 f'<meta property="og:url" content="{escape(canon)}">']
    og_img = f"{site}/og.png" if site else "/og.png"
    head += [f'<meta property="og:title" content="{escape(meta["title"])}">',
             f'<meta property="og:description" content="{escape(meta["desc"])}">',
             '<meta property="og:type" content="website">', '<meta property="og:site_name" content="トレカ抽選ナビ">',
             '<meta property="og:locale" content="ja_JP">',
             f'<meta property="og:image" content="{escape(og_img)}">', '<meta property="og:image:width" content="1200">',
             '<meta property="og:image:height" content="630">',
             '<meta name="twitter:card" content="summary_large_image">',
             f'<meta name="twitter:image" content="{escape(og_img)}">',
             '<meta name="theme-color" content="#c8102e">',
             '<link rel="icon" href="/favicon.svg" type="image/svg+xml">', '<link rel="icon" href="/favicon.png" sizes="48x48">',
             '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
             '<meta name="robots" content="index,follow,max-image-preview:large">']
    if meta.get("verify"):
        head.append(f'<meta name="google-site-verification" content="{escape(meta["verify"])}">')
    for ld in meta.get("ld") or []:
        head.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    body = TEMPLATE.read_text(encoding="utf-8")
    for k, v in {"__TITLE__": escape(meta["title"]), "__DESC__": escape(meta["desc"]),
                 "__HEADMETA__": "\n".join(head), "__ROOT__": escape(base), "__H1__": escape(meta["h1"]),
                 "__LEAD__": escape(meta["lead"]), "__SUMMARY__": escape(meta.get("summary", "")),
                 "__CRUMBS__": meta.get("crumbs", ""),
                 "__LINKS__": meta.get("links", ""), "__AFF__": meta.get("aff", ""), "__SUPPLY__": meta.get("supply", ""),
                 "__PRERENDER__": meta.get("prerender", "")}.items():
        body = body.replace(k, v)
    body = body.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    if not standalone:
        return body
    # テンプレートの <header> より前（title・meta・CSS）は <head> に入れる（検索エンジンは <head> の中を読む）
    cut = body.index("<header")
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}'
            ':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>'
            f'{body[:cut]}</head><body>{body[cut:]}</body></html>')


def _links(title, pairs):
    if not pairs:
        return ""
    return (f'<nav class="links" aria-label="{escape(title)}"><b>{escape(title)}</b>' +
            "".join(f'<a href="{escape(h)}">{escape(t)}</a>' for t, h in pairs) + "</nav>")


GAME_EN = {"pokemon": "POKEMON CARD", "onepiece": "ONE PIECE CARD", "dragonball": "FUSION WORLD"}


def _menu(items, games, g, here=""):
    """「抽選をさがす」メニュー（ページ下部＋ヘッダーのメニューボタンで開くシート）。
    タイトル（件数つきカード）／弾ごと（多い順・件数つき）／店頭抽選の地域"""
    gi = [i for i in items if i["game"] == g]
    slug = GAME_SLUG[g]
    cards = []
    for x in games:
        n = sum(1 for i in items if i["game"] == x)
        cur = ' aria-current="page"' if x == g else ""
        cards.append(f'<a class="m-game g-{x}" href="/{GAME_SLUG[x]}/"{cur}><small>{GAME_EN[x]}</small>'
                     f'<b>{escape(GAME_SHORT[x])}</b><span><em>{n}</em>件 受付中</span></a>')
    cnt = {}
    for i in gi:
        if i.get("series"):
            cnt[i["series"]] = cnt.get(i["series"], 0) + 1
    ser = sorted(cnt, key=lambda x: -cnt[x])

    def row(k, x):
        href = "/" + series_path(g, x)
        cur = ' aria-current="page"' if href == here else ""
        return (f'<li><a href="{escape(href)}"{cur}><i>{k:02d}</i><b>{escape(x)}</b>'
                f'<span>{cnt[x]}件</span></a></li>')
    rows = [row(k, x) for k, x in enumerate(ser, 1)]
    ser_html = ""
    if rows:
        ser_html = (f'<section class="m-sec"><h3>{escape(GAME_SHORT[g])}の弾ごと<small>受付中が多い順</small></h3>'
                    f'<ol class="m-ser">{"".join(rows[:8])}</ol>'
                    + (f'<details class="m-more"><summary>すべての弾を見る（{len(rows)}）</summary>'
                       f'<ol class="m-ser" start="9">{"".join(rows[8:])}</ol></details>' if len(rows) > 8 else "")
                    + '</section>')
    acnt = {}
    for i in gi:
        if i.get("channel") == "store" and i.get("area") in PREF:
            acnt[i["area"]] = acnt.get(i["area"], 0) + 1
    area_html = ""
    if acnt:
        chips = "".join(f'<a href="/{slug}/area/{PREF[a]}/">{escape(a)}<span>{acnt[a]}</span></a>'
                        for a in sorted(acnt, key=lambda a: list(PREF).index(a)))
        area_html = (f'<section class="m-sec"><h3>店頭抽選を地域でさがす<small>{len(acnt)}都道府県</small></h3>'
                     f'<div class="m-area">{chips}</div></section>')
    return (f'<nav class="menu" aria-label="抽選をさがす"><section class="m-sec"><h3>タイトルで選ぶ</h3>'
            f'<div class="m-games">{"".join(cards)}</div></section>{ser_html}{area_html}</nav>')


def _amz(q, tag):
    return f"https://www.amazon.co.jp/s?k={quote(q)}&tag={quote(tag)}"


def _rak(q, aff):
    """楽天の検索結果ページへのアフィリエイトリンク（楽天アフィリエイトの公式の形式）"""
    u = f"https://search.rakuten.co.jp/search/mall/{quote(q)}/"
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(u, safe='')}&m={quote(u, safe='')}" if aff else u


# サプライのアイコン（自作の簡単な図形）
_ICON = {
    "スリーブ": '<rect x="7" y="4" width="14" height="20" rx="2"/><rect x="10" y="7" width="8" height="12" rx="1" opacity=".45"/>',
    "ローダー": '<rect x="6" y="3" width="16" height="22" rx="2.5" stroke-width="2.4"/><rect x="10" y="7" width="8" height="12" rx="1" opacity=".45"/>',
    "デッキケース": '<path d="M5 9h18v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"/><path d="M5 9l3-5h12l3 5"/><path d="M12 14h4"/>',
    "ストレージ": '<rect x="3" y="10" width="22" height="14" rx="2"/><path d="M3 10l2-5h18l2 5"/><path d="M10 15h8"/>',
}


def _icon(k):
    return (f'<svg viewBox="0 0 28 28" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">{_ICON[k]}</svg>')


_REL = 'target="_blank" rel="nofollow sponsored noopener"'


def _product_ad(x, name, rr, tag, aff):
    """弾ページの広告：商品写真＋楽天／Amazonのボタン＋一緒に使うサプライ"""
    if not (tag or aff or rr.get("url")):
        return ""
    rak = rr.get("url") or _rak(f"{name} {x}", aff)
    amz = _amz(f"{name} {x}", tag) if tag else ""
    img = (f'<img src="{escape(rr["image"])}" alt="{escape(x)}" loading="lazy">' if rr.get("image")
           else f'<span class="ph">{_icon("ストレージ")}</span>')
    btns = (f'<a class="b-rak" href="{escape(rak)}" {_REL}>楽天市場で見る</a>' +
            (f'<a class="b-amz" href="{escape(amz)}" {_REL}>Amazonで見る</a>' if amz else ""))
    sup = "".join(f'<a href="{escape(_amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff))}" {_REL}>{_icon(k)}<span>{k}</span></a>'
                  for k in ("スリーブ", "ローダー", "デッキケース"))
    return (f'<aside class="ad"><div class="ad-top"><span class="ad-pr">PR</span><span>抽選に外れても、通販で探せます</span></div>'
            f'<div class="ad-main"><a class="ad-img" href="{escape(rak)}" {_REL}>{img}</a>'
            f'<div class="ad-info"><small>{escape(name)}</small><b>{escape(x)}</b><div class="ad-btns">{btns}</div></div></div>'
            f'<div class="ad-sup"><p>一緒にそろえたいサプライ</p><div>{sup}</div></div></aside>')


def _flow_ad(prods, title):
    """商品写真が横に流れる広告。prods: [(ゲーム略称, 弾名, 画像URL, 楽天リンク, 件数)]（画像のあるものだけ）"""
    prods = [p for p in prods if p[2] and p[3]][:14]
    if len(prods) < 3:
        return ""
    cards = "".join(
        f'<a class="fi" href="{escape(u)}" {_REL}><span class="fi-img"><img src="{escape(img)}" alt="{escape(x)}" loading="lazy"></span>'
        f'<small>{escape(g)}・抽選{n}件</small><b>{escape(x)}</b><em>楽天で見る</em></a>'
        for g, x, img, u, n in prods)
    sec = max(24, len(prods) * 5)  # 1枚あたり約5秒で流れる
    return (f'<aside class="ad ad-flow"><div class="ad-top"><span class="ad-pr">PR</span><span>{escape(title)}</span></div>'
            f'<div class="flow-wrap"><div class="flow-track" style="--sec:{sec}s">{cards}'
            f'<span class="flow-dup" aria-hidden="true">{cards}</span></div></div></aside>')


def _supply_ad(short, name, tag, aff, prices=None, game=None):
    """ゲームページの広告：サプライ4ジャンルのタイル。楽天の最安値があれば「¥199〜」を表示（押すと楽天の安い順）"""
    if not (tag or aff):
        return ""
    prices = prices or {}
    tiles, dates = [], []
    for k in ("スリーブ", "ローダー", "デッキケース", "ストレージ"):
        p = prices.get(k) or prices.get(f"{game}|{k}") or {}
        if p.get("price") and p.get("url"):
            href, price = p["url"], f'<small>楽天</small><strong>¥{p["price"]:,}〜</strong>'
            dates.append(p.get("fetched_at") or "")
        else:
            href = _amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff)
            price = ""
        tiles.append(f'<a href="{escape(href)}" {_REL}>{_icon(k)}<span>{k}</span>{price}</a>')
    amz = ("".join(f'<a href="{escape(_amz(f"{name} {k}", tag))}" {_REL}>{k}</a>'
                   for k in ("スリーブ", "ローダー", "デッキケース", "ストレージ")) if tag else "")
    note = ""
    if dates:
        d = parse_dt(max(dates))
        note = f'<p class="ad-note">価格は楽天市場の{d.month}/{d.day}時点の最安値（税込）</p>' if d else ""
    return (f'<aside class="ad"><div class="ad-top"><span class="ad-pr">PR</span><span>{escape(short)}のサプライをさがす</span></div>'
            f'<div class="ad-sup ad-tiles"><div>{"".join(tiles)}</div></div>{note}'
            + (f'<div class="ad-amz"><b>Amazonで見る</b>{amz}</div>' if amz else "") + '</aside>')


AMZ_SHORT = ("amzn.to", "amzn.asia", "link.amazon", "a.co")


def own_amazon_url(url, name, tag):
    """Amazonのリンクを自分のタグ付きに作り直す（他人のタグ・短縮リンクは使わない）。Amazon以外はそのまま"""
    import re
    from urllib.parse import urlparse
    if not url or not tag:
        return url
    host = urlparse(url).netloc.lower()
    if "amazon." in host:
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        return f"https://www.amazon.co.jp/dp/{m.group(1)}/?tag={quote(tag)}" if m else _amz(name, tag)
    if host in AMZ_SHORT:  # 短縮リンクの中身（商品）は分からないので、商品名の検索にする
        return _amz(name, tag)
    return url


def amazon_invites(items, tag):
    """ネット抽選の一番上に固定する「Amazon 招待リクエスト」の券の中身。ゲームごとに [{name, url}]
    商品ページ（/dp/）のあるものを先に、短縮リンクしかないものは同じ商品が無いときだけ（検索リンクで）入れる"""
    import re
    norm = lambda s: re.sub(r"[\s・「」『』()（）\-]", "", (s or "").lower())
    rows = []
    for i in items:
        if "amazon" not in ((i.get("store") or "") + (i.get("url") or "")).lower() or i.get("channel") == "store":
            continue
        p = i.get("product") or ""
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", i.get("url") or "")
        name = i.get("series") or p
        sub = re.search(r"[（(]([^）)]{2,30})[）)]", p)
        if sub and "招待" not in sub.group(1) and "BOX" not in sub.group(1):
            name = f"{name}（{sub.group(1)}）"
        rows.append((0 if m else 1, i["game"], m.group(1) if m else None, name, p, i.get("url")))
    out = {}
    for has_short, g, asin, name, p, url in sorted(rows, key=lambda r: r[0]):
        lst = out.setdefault(g, [])
        seen = " ".join(norm(x["name"]) + " " + norm(x["p"]) for x in lst)
        if (asin and any(x["asin"] == asin for x in lst)) or any(x["name"] == name for x in lst):
            continue
        if not asin and norm(name) and norm(name) in seen:
            continue  # 短縮リンクの商品が、商品ページのある行と同じなら入れない
        lst.append({"asin": asin, "name": name, "p": p, "url": own_amazon_url(url, p or name, tag)})
    return {g: [{"name": x["name"], "url": x["url"]} for x in v] for g, v in out.items()}


def active_series(settings=None):
    """{game: [弾名（受付中が多い順）]}"""
    s = settings or load_settings()
    cnt = {}
    for i in load_json("lotteries.json", {}).values():
        if i.get("status") not in ACTIVE or not i.get("series"):
            continue
        e = parse_dt(i.get("end"))
        if e and e < now():
            continue
        cnt.setdefault(i["game"], {}).setdefault(i["series"], 0)
        cnt[i["game"]][i["series"]] += 1
    return {g: sorted(c, key=lambda x: -c[x]) for g, c in cnt.items() if g in s["game_names"]}


def build(settings=None, out_dir=None, sample=None):
    s = settings or load_settings()
    site = (os.environ.get("SITE_URL") or s.get("site_public_url") or "").rstrip("/")
    tag = os.environ.get("AMAZON_TAG") or s.get("amazon_tag")
    raff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or s.get("rakuten_affiliate_id") or "").strip()
    out = Path(out_dir or ROOT / "site")
    games = [g for g in s["game_names"]]

    prices = load_json("rakuten_prices.json", {}) if sample is None else {}  # サプライの楽天最安値
    if sample is not None:
        items = sample
    else:
        images = load_images()
        from rakuten import item_link
        rk = {k: dict(v, url=item_link(v.get("url"), raff)) for k, v in load_json("rakuten.json", {}).items()}  # 楽天の商品画像＋自分のIDのリンク
        items = []
        for i in load_json("lotteries.json", {}).values():
            if i.get("status") not in ACTIVE:
                continue
            e = parse_dt(i.get("end"))
            if e and e < now():
                continue
            row = {k: i.get(k) for k in FIELDS}
            row["image"] = row.get("image") or images.get(i.get("series") or "")
            row["url"] = own_amazon_url(row.get("url"), row.get("product") or row.get("series") or "", tag)
            r = rk.get(f"{i.get('game')}|{i.get('series')}") or {}
            if not row["image"] and r.get("image"):
                row["image"], row["img_url"] = r["image"], r.get("url")
            items.append(row)

    # 中身が変わっていなければ「最終更新」も据え置き（無駄な再公開をしない）
    meta_state = load_json("site_meta.json", {})
    digest = sha(json.dumps(sorted(items, key=lambda x: x.get("key") or ""), ensure_ascii=False, sort_keys=True))
    changed = meta_state.get("digest") != digest
    updated = now().isoformat() if changed or not meta_state.get("updated") else meta_state["updated"]

    common_data = {"sample": False, "updated": updated,
                   "games": [{"id": g, "name": GAME_SHORT[g]} for g in games],
                   "gameUrls": {g: f"/{GAME_SLUG[g]}/" for g in games}, "items": items,
                   "gameNames": {g: s["game_names"][g] for g in games}, "amazonTag": tag or "", "amazonInvites": amazon_invites(items, tag) if tag else {}}
    urls = []
    upd = parse_dt(updated) or now()
    md = f"{upd.month}/{upd.day}"
    verify = s.get("google_site_verification") or os.environ.get("GOOGLE_SITE_VERIFICATION") or ""
    game_counts = {g: sum(1 for i in items if i["game"] == g) for g in games}

    def summary(sub, what):
        """ページごとの要約文（件数・一番近い締切・店頭が多い都道府県）。検索結果にも使われる独自の文章"""
        if not sub:
            return f"現在受付中の{what}はありません。新しい抽選が見つかり次第、自動で追加されます。"
        on = sum(1 for i in sub if i.get("channel") != "store")
        txt = f"現在受付中の{what}は{len(sub)}件" + (f"（ネット抽選{on}件・店頭抽選{len(sub) - on}件）。" if 0 < on < len(sub) else "。")
        soon = sorted([i for i in sub if parse_dt(i.get("end"))], key=lambda i: i["end"])
        if soon:
            i = soon[0]
            txt += f"締切が一番近いのは{i['store']}の「{i.get('series') or i.get('product')}」（{_fmt(i['end'])}締切）。"
        cnt = {}
        for i in sub:
            if i.get("channel") == "store" and i.get("area"):
                cnt[i["area"]] = cnt.get(i["area"], 0) + 1
        top3 = sorted(cnt, key=lambda a: -cnt[a])[:3]
        if top3:
            txt += "店頭抽選が多い地域は" + "・".join(f"{a}（{cnt[a]}件）" for a in top3) + "です。"
        return txt

    def crumbs(trail):
        """パンくず（画面）と構造化データ。trail: [(名前, パス)]"""
        html = '<nav class="crumbs" aria-label="パンくず">' + " › ".join(
            (f'<a href="/{escape(p)}">{escape(n)}</a>' if k < len(trail) - 1 else f"<span>{escape(n)}</span>")
            for k, (n, p) in enumerate(trail)) + "</nav>"
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": k + 1, "name": n, "item": f"{site}/{p}"} for k, (n, p) in enumerate(trail)]}
        return html, ld

    def item_list(sub, title):
        rows = sorted([i for i in sub if parse_dt(i.get("end"))], key=lambda i: i["end"])[:20]
        return {"@context": "https://schema.org", "@type": "ItemList", "name": title, "numberOfItems": len(sub),
                "itemListElement": [{"@type": "ListItem", "position": k + 1,
                                     "name": f"{i['store']} {i.get('series') or i.get('product')}（{_fmt(i['end'])}締切）",
                                     **({"url": i["url"]} if i.get("url") else {})} for k, i in enumerate(rows)]}

    def write(path, lock, meta, subset, trail=None):
        p = out / path / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        meta["canonical"] = f"{site}/{path}" if site else None
        meta["site"], meta["verify"] = site, verify
        meta["prerender"] = prerender(subset)
        ld = [item_list(subset, meta["h1"])]
        if trail:
            meta["crumbs"], bl = crumbs(trail)
            ld.insert(0, bl)
        if not path:
            ld.insert(0, {"@context": "https://schema.org", "@type": "WebSite", "name": "トレカ抽選ナビ", "url": f"{site}/",
                          "inLanguage": "ja", "description": meta["desc"]})
        meta["ld"] = ld
        # ページを軽くする：そのページのゲームの抽選だけを埋め込む（トップは最初のゲームだけ。ほかのゲームはタブで移動）
        g0 = lock.get("game") or games[0]
        data = {**common_data, "lock": lock, "items": [i for i in items if i["game"] == g0], "gameCounts": game_counts,
                "amazonInvites": {g0: (common_data.get("amazonInvites") or {}).get(g0, [])}}
        p.write_text(page(data, meta), encoding="utf-8")
        last = max([i.get("found_at") or "" for i in subset] + [""]) or updated
        urls.append((f"{site}/{path}", (last or updated)[:10]))

    def prods_of(game):
        cnt = {}
        for i in items:
            if i["game"] == game and i.get("series"):
                cnt[i["series"]] = cnt.get(i["series"], 0) + 1
        rk_ = rk if sample is None else {}
        return [(GAME_SHORT[game], x, (rk_.get(f"{game}|{x}") or {}).get("image"), (rk_.get(f"{game}|{x}") or {}).get("url"), n)
                for x, n in sorted(cnt.items(), key=lambda kv: -kv[1])]

    for g in games:
        gi = [i for i in items if i["game"] == g]
        name, short, slug = s["game_names"][g], GAME_SHORT[g], GAME_SLUG[g]
        series = sorted({i["series"] for i in gi if i.get("series")},
                        key=lambda x: -sum(1 for i in gi if i.get("series") == x))
        areas = sorted({i["area"] for i in gi if i.get("channel") == "store" and i.get("area") in PREF},
                       key=lambda a: list(PREF).index(a))
        online = sum(1 for i in gi if i.get("channel") != "store")
        today = sum(1 for i in gi if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == now().date())
        meta = {"title": f"{short}抽選情報まとめ【{md}更新】受付中{len(gi)}件" + (f"・本日締切{today}件" if today else "") + "｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{name}（{short}）の抽選販売・予約抽選を締切が近い順にまとめ。ネット抽選{online}件・"
                        f"店頭抽選{len(gi) - online}件を掲載、都道府県別・弾別・本人確認や会員の有無で絞り込めます。30分ごとに自動更新。",
                "summary": summary(gi, f"{short}の抽選"),
                "h1": f"{short}の抽選・予約情報まとめ",
                "lead": f"いま受付中の{name}の抽選を、ネット・店頭（都道府県別）に分けて締切が近い順に並べています。"
                        "30分ごとに自動で更新しています。",
                "links": _menu(items, games, g), "root": "/",
                "supply": _supply_ad(short, name, tag, raff, prices, g)}
        write(f"{slug}/", {"game": g}, dict(meta), gi, [("トップ", ""), (f"{short}の抽選", f"{slug}/")])
        if g == games[0]:
            top = dict(meta, title=f"トレカ抽選ナビ｜ポケカ・ワンピカードの抽選情報まとめ【{md}更新】締切が近い順",
                       desc=f"【{md}更新】ポケカ（ポケモンカード）・ワンピカード・フュージョンワールドの抽選販売をネットと店頭（都道府県別）に分けて"
                            f"締切が近い順に掲載。受付中{sum(game_counts.values())}件。本人確認・会員の有無でも絞り込めます。",
                       summary=summary(items, "トレカの抽選"),
                       h1="トレカの抽選・予約情報まとめ",
                       lead="ポケカ・ワンピカード・ドラゴンボール フュージョンワールドの抽選を、ネットと店頭（都道府県別）で"
                            "締切が近い順にまとめています。本人確認・会員カードの有無でも絞り込めます。")
            top["supply"] = _supply_ad(short, name, tag, raff, prices, g)
            write("", {}, top, items)

        for x in series:
            si = [i for i in gi if i.get("series") == x]
            rr = (rk if sample is None else {}).get(f"{g}|{x}") or {}
            aff = _product_ad(x, name, rr, tag, raff)
            alias = (s.get("rakuten_aliases") or {}).get(x)
            write(series_path(g, x), {"game": g, "series": x}, {
                "title": f"{x}の抽選・予約情報【{md}更新】受付中{len(si)}件・締切順｜{short}｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{name}「{x}」" + (f"（{alias}）" if alias and alias != x else "") +
                        f"の抽選販売・予約抽選{len(si)}件を締切順にまとめ。ネット・店頭（都道府県別）、本人確認・会員カードの有無もひと目で分かります。",
                "summary": summary(si, f"「{x}」の抽選"),
                "h1": f"「{x}」の抽選・予約情報",
                "lead": f"{name}「{x}」の受付中の抽選は{len(si)}件です。新しい抽選が見つかり次第、自動で追加されます。",
                "aff": aff, "links": _menu(items, games, g, "/" + series_path(g, x)),
                "root": "/"}, si, [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (x, series_path(g, x))])

        for a in areas:
            ai = [i for i in gi if i.get("channel") == "store" and i.get("area") == a]
            write(f"{slug}/area/{PREF[a]}/", {"game": g, "channel": "store", "area": a}, {
                "title": f"{a}の{short}店頭抽選まとめ【{md}更新】{len(ai)}件・締切順｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{a}の店舗で受付中の{name}（{short}）の店頭抽選・抽選券配布{len(ai)}件を締切順にまとめ。"
                        "Web応募で店頭受取の抽選も含みます。",
                "summary": summary(ai, f"{a}の{short}店頭抽選"),
                "h1": f"{a}の{short}店頭抽選",
                "lead": f"{a}で受付中の{name}の店頭抽選は{len(ai)}件です。整理券・抽選券の配布時間や条件は店舗の告知で必ずご確認ください。",
                "links": _menu(items, games, g), "root": "/"}, ai,
                [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (f"{a}の店頭抽選", f"{slug}/area/{PREF[a]}/")])

    # 共通の画像（OGP・アイコン）と IndexNow の鍵ファイル
    import shutil
    for f in (ROOT / "src" / "static").glob("*"):
        shutil.copy(f, out / f.name)
    if s.get("indexnow_key"):
        (out / f"{s['indexnow_key']}.txt").write_text(s["indexnow_key"], encoding="utf-8")

    # X手動投稿用の下書きページ（検索に載せない・サイトマップにも入れない）
    from xdraft import build_x_draft
    build_x_draft(out, items, site, updated)

    if site:
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u, lm in urls)
            + "</urlset>\n", encoding="utf-8")
        (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /x-draft.html\nSitemap: {site}/sitemap.xml\n", encoding="utf-8")

    if sample is None:
        save_json("site_meta.json", {"digest": digest, "updated": updated})
    (out / ".changed").unlink(missing_ok=True)
    if changed:
        (out / ".changed").write_text(updated, encoding="utf-8")  # ワークフローはこれがある時だけ公開
    return out


def sample_items():
    P, O, D = "pokemon", "onepiece", "dragonball"
    rows = [
        (P, "ポケモンセンターオンライン", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 5.2, ["本人確認"], "ポケモンセンターオンライン会員・本人確認済みの方", "online", None, 30, True, "account"),
        (P, "ヨドバシ.com", "拡張パック「サンプル弾A」1BOX", "サンプル弾A", 30, ["購入履歴"], "ゴールドポイントカード・プラス会員、過去1年の購入履歴あり", "online", None, 3, False, "account"),
        (P, "セブンネットショッピング", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 52, [], "7iD会員", "online", None, 10, None, "account"),
        (P, "楽天ブックス", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 76, [], "楽天会員", "online", None, 2, False, "account"),
        (P, "Amazon（招待リクエスト）", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 120, [], "Amazonアカウントでリクエスト", "online", None, 60, False, "account"),
        (P, "ジョーシン", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 18, ["アプリ"], "ジョーシンアプリから応募", "online", None, 6, False, "account"),
        (P, "TSUTAYAオンライン", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 9, [], "応募条件なし", "online", None, 40, False, "none"),
        (P, "イオン なんば店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 26, ["整理券", "レシート"], "店頭で抽選券を配布（10:00〜）", "store", "大阪府", 4, False, "none"),
        (P, "カードショップ サンプル梅田店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 7.5, ["SNS応募"], "店舗Xアカウントをフォローしてリプライで応募", "store", "大阪府", 1, None, "none"),
        (P, "トイザらス 堺店", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 44, ["アプリ"], "トイザらスアプリ会員証を提示", "store", "大阪府", 12, False, "card"),
        (P, "ゲームショップ サンプル京都店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 33, ["本人確認"], "身分証の提示が必要", "store", "京都府", 8, True, "card"),
        (P, "イオンモール 幕張新都心", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 21, ["整理券"], "整理券配布後に抽選", "store", "千葉県", 20, False, "none"),
        (P, "カードショップ サンプル秋葉原店", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 3.1, ["SNS応募"], "Xのポストへのリプライで応募", "store", "東京都", 2, None, None),
        (O, "プレミアムバンダイ", "ブースターパック「サンプル航海」BOX", "サンプル航海", 14, [], "バンダイナムコID", "online", None, 5, False, "account"),
        (O, "あみあみ", "ブースターパック「サンプル航海」BOX", "サンプル航海", 48, [], "あみあみ会員", "online", None, 30, False, "account"),
        (O, "カードショップ サンプル心斎橋店", "ブースターパック「サンプル航海」BOX", "サンプル航海", 22, ["SNS応募"], "Xで応募", "store", "大阪府", 3, False, "none"),
        (O, "ゲームショップ サンプル渋谷店", "ブースターパック「サンプル航海」BOX", "サンプル航海", 40, ["整理券"], "店頭で抽選券配布", "store", "東京都", 11, True, "card"),
        (D, "プレミアムバンダイ", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 36, [], "バンダイナムコID", "online", None, 7, False, "account"),
        (D, "駿河屋", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 90, [], "駿河屋会員", "online", None, 26, None, "account"),
        (D, "カードショップ サンプル天神店", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 28, ["整理券"], "店頭で抽選券配布", "store", "福岡県", 5, False, "none"),
    ]
    return [{"key": f"s{n}", "game": g, "store": st, "product": pr, "series": se, "end_h": h, "tags": tags,
             "conditions": cond, "url": "https://example.com/", "channel": ch, "area": area, "found_h": found,
             "id_check": idc, "member": mem}
            for n, (g, st, pr, se, h, tags, cond, ch, area, found, idc, mem) in enumerate(rows)]


if __name__ == "__main__":
    if "--sample" in sys.argv:
        items = sample_items()
        data = {"sample": True, "updated": now().isoformat(),
                "games": [{"id": g, "name": GAME_SHORT[g]} for g in GAME_SHORT], "items": items}
        meta = {"title": "トレカ抽選ナビ", "desc": "試作", "h1": "トレカの抽選・予約情報まとめ",
                "lead": "ポケカ・ワンピカード・フュージョンワールドの抽選を、ネットと店頭（都道府県別）で締切が近い順にまとめています。",
                "links": _links("弾ごと", [("サンプル弾A", "#"), ("サンプル弾B", "#")]), "root": "#"}
        out = ROOT / "output"
        out.mkdir(exist_ok=True)
        (out / "site_preview.html").write_text(page(data, meta, standalone=False), encoding="utf-8")
        print(out / "site_preview.html")
    else:
        print(build())
