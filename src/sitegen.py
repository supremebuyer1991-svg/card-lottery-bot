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
    rows = []
    for i in sorted(items, key=lambda x: x.get("end") or "9999")[:200]:
        where = f"［{i['area']}］" if i.get("channel") == "store" and i.get("area") else ""
        link = f' <a href="{escape(i["url"])}" rel="noopener">応募ページ</a>' if i.get("url") else ""
        rows.append(f"<li><b>{escape(where + i['store'])}</b> {escape(i['product'])}"
                    f" ／ 締切 {_fmt(i.get('end'))}{link}</li>")
    return f'<ul class="pre">{"".join(rows)}</ul>'


def page(data: dict, meta: dict, standalone=True) -> str:
    base = meta.get("root", "/")
    canon = meta.get("canonical")
    head = []
    if canon:
        head += [f'<link rel="canonical" href="{escape(canon)}">',
                 f'<meta property="og:url" content="{escape(canon)}">']
    head += [f'<meta property="og:title" content="{escape(meta["title"])}">',
             f'<meta property="og:description" content="{escape(meta["desc"])}">',
             '<meta property="og:type" content="website">', '<meta name="twitter:card" content="summary">']
    body = TEMPLATE.read_text(encoding="utf-8")
    for k, v in {"__TITLE__": escape(meta["title"]), "__DESC__": escape(meta["desc"]),
                 "__HEADMETA__": "\n".join(head), "__ROOT__": escape(base), "__H1__": escape(meta["h1"]),
                 "__LEAD__": escape(meta["lead"]), "__LINKS__": meta.get("links", ""), "__AFF__": meta.get("aff", ""),
                 "__PRERENDER__": meta.get("prerender", "")}.items():
        body = body.replace(k, v)
    body = body.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    if not standalone:
        return body
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}'
            ':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>'
            f'</head><body>{body}</body></html>')


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


def _supply_ad(short, name, tag, aff):
    """ゲームページの広告：サプライを4つのタイルで"""
    if not (tag or aff):
        return ""
    tiles = "".join(f'<a href="{escape(_amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff))}" {_REL}>{_icon(k)}<span>{k}</span></a>'
                    for k in ("スリーブ", "ローダー", "デッキケース", "ストレージ"))
    more = (f'<a class="ad-more" href="{escape(_rak(f"{name} サプライ", aff))}" {_REL}>楽天市場でサプライをまとめて見る</a>' if aff else "")
    return (f'<aside class="ad"><div class="ad-top"><span class="ad-pr">PR</span><span>{escape(short)}のサプライをさがす</span></div>'
            f'<div class="ad-sup ad-tiles"><div>{tiles}</div></div>{more}</aside>')


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
                   "gameUrls": {g: f"/{GAME_SLUG[g]}/" for g in games}, "items": items}
    urls = []

    def write(path, lock, meta, subset):
        p = out / path / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        meta["canonical"] = f"{site}/{path}" if site else None
        meta["prerender"] = prerender(subset)
        p.write_text(page({**common_data, "lock": lock}, meta), encoding="utf-8")
        urls.append(f"{site}/{path}")

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
        meta = {"title": f"{short}抽選・予約情報まとめ【最新・締切順】｜トレカ抽選ナビ",
                "desc": f"{name}の抽選・予約情報を締切が近い順にまとめています。ネット抽選{online}件、"
                        f"店頭抽選{len(gi) - online}件を掲載。本人確認・会員の有無で絞り込めます。",
                "h1": f"{short}の抽選・予約情報まとめ",
                "lead": f"いま受付中の{name}の抽選を、ネット・店頭（都道府県別）に分けて締切が近い順に並べています。"
                        "30分ごとに自動で更新しています。",
                "links": _menu(items, games, g), "root": "/",
                "aff": _flow_ad(prods_of(g), f"いま抽選が多い{short}の弾を通販でチェック") + _supply_ad(short, name, tag, raff)}
        write(f"{slug}/", {"game": g}, dict(meta), gi)
        if g == games[0]:
            top = dict(meta, title="トレカ抽選ナビ｜ポケカ・ワンピカード・フュージョンワールドの抽選情報まとめ",
                       h1="トレカの抽選・予約情報まとめ",
                       lead="ポケカ・ワンピカード・ドラゴンボール フュージョンワールドの抽選を、ネットと店頭（都道府県別）で"
                            "締切が近い順にまとめています。本人確認・会員カードの有無でも絞り込めます。")
            top["aff"] = _flow_ad(sorted(sum((prods_of(x) for x in games), []), key=lambda p: -p[4]),
                                  "いま抽選が多い弾を通販でチェック") + _supply_ad(short, name, tag, raff)
            write("", {}, top, items)

        for x in series:
            si = [i for i in gi if i.get("series") == x]
            rr = (rk if sample is None else {}).get(f"{g}|{x}") or {}
            aff = _product_ad(x, name, rr, tag, raff)
            write(series_path(g, x), {"game": g, "series": x}, {
                "title": f"{x} 抽選・予約情報まとめ【{len(si)}件受付中・締切順】｜トレカ抽選ナビ",
                "desc": f"{name}「{x}」の抽選・予約情報を店舗別・締切順にまとめています。ネット・店頭（都道府県別）、"
                        "本人確認・会員カードの有無もひと目で分かります。",
                "h1": f"「{x}」の抽選・予約情報",
                "lead": f"{name}「{x}」の受付中の抽選は{len(si)}件です。新しい抽選が見つかり次第、自動で追加されます。",
                "aff": aff, "links": _menu(items, games, g, "/" + series_path(g, x)),
                "root": "/"}, si)

        for a in areas:
            ai = [i for i in gi if i.get("channel") == "store" and i.get("area") == a]
            write(f"{slug}/area/{PREF[a]}/", {"game": g, "channel": "store", "area": a}, {
                "title": f"{a}の{short}店頭抽選まとめ【{len(ai)}件・締切順】｜トレカ抽選ナビ",
                "desc": f"{a}の店舗で受付中の{name}の店頭抽選・抽選券配布の情報を締切順にまとめています。",
                "h1": f"{a}の{short}店頭抽選",
                "lead": f"{a}で受付中の{name}の店頭抽選は{len(ai)}件です。整理券・抽選券の配布時間や条件は店舗の告知で必ずご確認ください。",
                "links": _menu(items, games, g), "root": "/"}, ai)

    # X手動投稿用の下書きページ（検索に載せない・サイトマップにも入れない）
    from xdraft import build_x_draft
    build_x_draft(out, items, site, updated)

    if site:
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{updated[:10]}</lastmod></url>" for u in urls)
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
