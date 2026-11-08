"""ゲーム・ホビー入荷速報：定価以上で売れる商品（プレ値商品）

・買取店（game_kaitori が毎日読む9店）の新品の買取価格を、JANコードごとにまとめる（JANが無い店の商品は商品名で寄せる）
・定価は楽天ブックスの販売価格（JANで探す。楽天ブックスは基本的に定価で売っている）。1回 premium_teika_per_run 件ずつ調べ、7日ごとに調べ直す
・いちばん高い買取価格が定価の premium_min_ratio 倍以上の商品を「プレ値商品」として、/premium/ と /premium/<JAN>/ を作る
・毎日の最高買取価格を state/game/premium_hist.json に残す（チャート・1週間前比・1か月前比に使う。400日分）
"""
import re
from datetime import timedelta
from html import escape

from common import load_json, save_json, now, parse_dt, log

HIST = "premium_hist.json"
TEIKA = "premium_teika.json"


def groups(st=None):
    """{JAN: {"names": [...], "prices": {店: 価格}, "max": 価格, "store": 店}}"""
    import official_link as ol
    st = st if st is not None else load_json("kaitori_multi.json", {})
    g = {}
    loose = []
    for store, rec in st.items():
        if not isinstance(rec, dict):
            continue
        for name, jan, price in rec.get("items", []):
            jan = re.sub(r"\D", "", str(jan or ""))
            if len(jan) in (8, 13):
                x = g.setdefault(jan, {"names": [], "prices": {}})
                if name not in x["names"]:
                    x["names"].append(name)
                x["prices"][store] = max(price, x["prices"].get(store, 0))
            else:
                loose.append((store, name, price))
    for store, name, price in loose:   # JANの無い店の商品は、商品名がほぼ同じJANの商品に寄せる
        best = None
        for jan, x in g.items():
            sc = min(ol._score(name, x["names"][0]), ol._score(x["names"][0], name))
            if sc >= 0.85 and (best is None or sc > best[0]):
                best = (sc, jan)
        if best:
            x = g[best[1]]
            x["prices"][store] = max(price, x["prices"].get(store, 0))
    for x in g.values():
        x["store"], x["max"] = max(x["prices"].items(), key=lambda kv: kv[1])
    return g


def _lookup_teika(jan, settings, fetch=None):
    import game_affi
    fetch = fetch or (lambda p: game_affi.http_fetch(p, settings))
    items = fetch({"keyword": jan, "shopCode": "book", "hits": 5, "availability": 0, "imageFlag": 1})
    for it in items:
        p = it.get("itemPrice")
        if p:
            url = (it.get("itemUrl") or "").split("?")[0]
            return {"price": int(p), "itemUrl": url, "img": game_affi._image(it), "title": it.get("itemName") or ""}
    return None


BOOKS_GAME = ["https://openapi.rakuten.co.jp/services/api/BooksGame/Search/20170404",
              "https://openapi.rakuten.co.jp/booksms/api/BooksGame/Search/20170404",
              "https://app.rakuten.co.jp/services/api/BooksGame/Search/20170404"]
_books_ok = {}


def _books_info(jan, settings):
    """楽天ブックスのゲームの情報（発売日・メーカー・対応機種・説明）。新しいAPIの場所が分からないので、候補を順に試す"""
    import os
    import requests
    site = (os.environ.get("RAKUTEN_REFERER") or os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")
    p = {"applicationId": os.environ.get("RAKUTEN_APP_ID", "").strip(), "accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", "").strip(),
         "jan": jan, "format": "json", "formatVersion": 2}
    h = {"accessKey": p["accessKey"], "Referer": site + "/", "Origin": site, "User-Agent": "game-nyuka/1.0"}
    for url in ([_books_ok["url"]] if _books_ok.get("url") else BOOKS_GAME):
        try:
            r = requests.get(url, params=p, headers=h, timeout=15)
        except Exception as e:
            log(f"楽天ブックス（ゲーム）: {url.split('/')[2]} {e}")
            continue
        if r.status_code == 200:
            _books_ok["url"] = url
            items = r.json().get("Items") or []
            if items:
                i = items[0].get("Item", items[0])
                return {"sales_date": i.get("salesDate") or "", "maker": i.get("label") or i.get("makerCode") or "",
                        "hardware": i.get("hardware") or "", "caption": (i.get("itemCaption") or "")[:400], "title": i.get("title") or ""}
            return {}
        if not _books_ok.get("logged"):
            log(f"楽天ブックス（ゲーム）: {url} → {r.status_code} {r.text[:120]}")
    _books_ok["logged"] = True
    return None


def update(settings, fetch=None, sleep=None):
    import time
    sleep = sleep or time.sleep
    g = groups()
    if not g:
        return {}
    t = now()
    today = t.date().isoformat()
    hist = load_json(HIST, {})
    cut = (t.date() - timedelta(days=400)).isoformat()
    for jan, x in g.items():
        h = hist.setdefault(jan, {})
        h[today] = x["max"]
        for d in [d for d in h if d < cut]:
            h.pop(d)
    save_json(HIST, hist)
    teika = load_json(TEIKA, {})
    import os
    if fetch is None and not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
        return g
    left = int(settings.get("premium_teika_per_run", 8))
    order = sorted(g, key=lambda j: -g[j]["max"])   # 買取価格の高い商品から先に定価を調べる
    for jan in order:
        c = teika.get(jan)
        if c and parse_dt(c.get("at")) and (t - parse_dt(c["at"])).total_seconds() < 7 * 86400:
            continue
        if left <= 0:
            break
        left -= 1
        try:
            r = _lookup_teika(jan, settings, fetch)
            info = _books_info(jan, settings) if (r and fetch is None) else None
            teika[jan] = dict(r or {}, **(info or {}), at=t.isoformat())
        except Exception as e:
            log(f"プレ値：{jan} 定価の取得失敗 {e}")
            if "429" not in str(e):
                teika[jan] = {"at": t.isoformat()}
        sleep(1.2)
    if fetch is None:   # 定価が分かっていて、商品情報（発売日など）がまだのものを少しずつ埋める
        for jan in [j for j in order if (teika.get(j) or {}).get("price") and "sales_date" not in teika[j]][:int(settings.get("premium_info_per_run", 6))]:
            info = _books_info(jan, settings)
            if info is None:
                break
            teika[jan].update(info or {"sales_date": ""})
            sleep(1.2)
    save_json(TEIKA, teika)
    return g


def _ago(h, days, today):
    d0 = (today - timedelta(days=days)).isoformat()
    ks = [k for k in sorted(h) if k <= d0]
    return h[ks[-1]] if ks else None


def premium_list(settings=None):
    """プレ値商品の一覧（定価との差の大きい順）"""
    settings = settings or {}
    g = groups()
    teika = load_json(TEIKA, {})
    hist = load_json(HIST, {})
    today = now().date()
    out = []
    for jan, x in g.items():
        tk = teika.get(jan) or {}
        if not tk.get("price"):
            continue
        r = x["max"] / tk["price"]
        if r < float(settings.get("premium_min_ratio", 1.03)):
            continue
        h = hist.get(jan, {})
        name = re.sub(r"\s+", " ", (tk.get("title") or x["names"][0]))
        name = re.sub(r"【.*?】", "", name).strip()[:70]
        model = re.compile(r"[A-Z]{2,}-?[A-Z0-9]{3,}")
        if not model.search(name):   # 楽天の名前に型番が無ければ、型番のある買取店の名前を使う（同じ名前の別モデルを見分けるため）
            withm = [n for n in x["names"] if model.search(n)]
            if withm:
                name = re.sub(r"\s+", " ", withm[0]).strip()[:70]
        out.append({"jan": jan, "name": name, "names": x["names"], "teika": tk["price"], "max": x["max"], "store": x["store"],
                    "prices": sorted(x["prices"].items(), key=lambda kv: -kv[1]), "ratio": r, "itemUrl": tk.get("itemUrl", ""),
                    "img": tk.get("img", ""), "hist": h, "w1": _ago(h, 7, today), "m1": _ago(h, 30, today),
                    "sales_date": tk.get("sales_date", ""), "maker": tk.get("maker", ""), "hardware": tk.get("hardware", ""), "caption": tk.get("caption", "")})
    out.sort(key=lambda x: -x["ratio"])
    return out


def _chg(cur, old):
    if not old:
        return '<span class="na">記録なし</span>'
    d = cur - old
    cls = "up" if d > 0 else "dn" if d < 0 else "eq"
    return f'<span class="{cls}">{"+" if d > 0 else ""}{d:,}円（{"+" if d > 0 else ""}{round(d / old * 100, 1)}%）</span>'


def chart_svg(h, teika):
    """最高買取価格のチャート（直近90日・定価の線つき）"""
    pts = sorted(h.items())[-90:]
    if not pts:
        return ""
    W, H, P = 640, 220, 34
    vals = [v for _, v in pts] + [teika]
    lo, hi = min(vals) * 0.97, max(vals) * 1.03
    def X(i):
        return P + (W - 2 * P) * (i / max(1, len(pts) - 1))
    def Y(v):
        return H - P - (H - 2 * P) * ((v - lo) / max(1, hi - lo))
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    dots = "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3"><title>{d} {v:,}円</title></circle>' for i, (d, v) in enumerate(pts))
    ty = Y(teika)
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="最高買取価格の推移">'
            f'<line x1="{P}" x2="{W - P}" y1="{ty:.1f}" y2="{ty:.1f}" class="tk"/><text x="{W - P}" y="{ty - 6:.1f}" text-anchor="end" class="tkl">定価 {teika:,}円</text>'
            f'<polyline points="{line}" class="ln"/>{dots}'
            f'<text x="{P}" y="{H - 8}" class="ax">{pts[0][0][5:].replace("-", "/")}</text><text x="{W - P}" y="{H - 8}" text-anchor="end" class="ax">{pts[-1][0][5:].replace("-", "/")}</text></svg>')


CSS = (".pm-t{width:100%;border-collapse:collapse;font-size:14px}.pm-t td,.pm-t th{padding:8px 6px;border-bottom:1px solid var(--line,#262c3a);text-align:left}"
       ".pm-t td.n{text-align:right;font-family:var(--font-num)}.up{color:#3ddc84}.dn{color:#ff8a95}.eq,.na{color:#8a93a6}"
       ".chart{width:100%;height:auto;background:#0f121a;border:1px solid #262c3a;border-radius:10px;margin:8px 0}"
       ".chart .ln{fill:none;stroke:#ffd23f;stroke-width:2.5}.chart circle{fill:#ffd23f}.chart .tk{stroke:#5ee0ff;stroke-dasharray:5 5}"
       ".chart .tkl,.chart .ax{fill:#8a93a6;font-size:12px}.pm-big{font-size:28px;font-weight:900;font-family:var(--font-num)}"
       ".pm-row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}.pm-row img{border-radius:10px;background:#fff}"
       ".shopb{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.shopb .btn{padding:10px 14px;border-radius:6px;font-weight:900;text-decoration:none}"
       ".btn-rk{background:#bf0000;color:#fff}.btn-yh{background:#ff0033;color:#fff}.btn-mc{background:#fff;color:#ea352d;border:1px solid #ea352d}.btn-az{background:#ff9900;color:#0b0d12}")


def info_rows(x):
    """商品情報の表：商品名・メーカー・発売日・定価・型番・対応機種・JAN（分かるものだけ）"""
    model = ""
    for n in [x["name"]] + x.get("names", []):
        m = re.search(r"[A-Z]{2,}-?[A-Z0-9]{3,}[A-Z0-9-]*", n)
        if m:
            model = m.group(0)
            break
    rows = [("商品名", x["name"]), ("メーカー", x.get("maker")), ("発売日", x.get("sales_date")), ("定価（税込）", f'{x["teika"]:,}円（楽天ブックスの販売価格）'),
            ("型番", model), ("対応機種", x.get("hardware")), ("JANコード", x["jan"])]
    out = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows if v)
    if x.get("caption"):
        out += f'<tr><th>説明</th><td>{escape(x["caption"][:200])}…</td></tr>'
    return out


def write_pages(out, cats, site, brand, live_rows, settings, simple_page, aff_id=""):
    """/premium/ と /premium/<JAN>/ を書く。書いたパスの一覧を返す（サイトマップ用）"""
    from urllib.parse import quote
    import official_link as ol
    from game_affi import rakuten_link
    items = premium_list(settings)
    upd = now()
    md = f"{upd.month}/{upd.day}"
    paths = []
    note = ('<p class="note">買取価格は各買取店が公開している新品（未開封）の買取価格を毎日読み取ったものです（店の条件で変わることがあります）。'
            '定価は楽天ブックスの販売価格です。転売を勧めるものではありません。リンクの一部は広告（PR）です。</p>')

    def page(title, desc, body, path):
        html = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{escape(title)}</title><meta name="description" content="{escape(desc)}"><link rel="canonical" href="{site}/{path}">'
                f'<link rel="icon" href="/favicon.svg" type="image/svg+xml"><style></style></head><body><style>{CSS}</style>{body}</body></html>')
        d = out / path
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(simple_page(cats, html), encoding="utf-8")
        paths.append(path)

    rows = "".join(
        f'<tr><td><a href="/premium/{x["jan"]}/">{escape(x["name"])}</a></td><td class="n">{x["teika"]:,}円</td><td class="n">{x["max"]:,}円</td>'
        f'<td class="n up">+{round((x["ratio"] - 1) * 100)}%</td><td class="n">{_chg(x["max"], x["w1"])}</td></tr>' for x in items)
    page(f"定価以上で売れるゲーム・ホビー一覧【{md}更新】買取価格の相場｜{brand['name']}",
         f"定価より高く買い取られているゲーム機・周辺機器・ホビーの一覧。買取店の新品の最高買取価格・定価との差・1週間前比を毎日更新。",
         f'<h1>定価以上で売れるゲーム・ホビー</h1><p>買取店の新品の最高買取価格が定価を上回っている商品です（{md}更新・{len(items)}件）。定価で買える抽選・予約・再販が出たら、このサイトとXで知らせます。</p>'
         + (f'<table class="pm-t"><thead><tr><th>商品</th><th>定価</th><th>最高買取</th><th>定価比</th><th>1週間前比</th></tr></thead><tbody>{rows}</tbody></table>' if items else "<p>いま該当する商品はありません。</p>")
         + note, "premium/")
    for x in items:
        q = quote(re.sub(r"\s+", " ", x["name"])[:40])
        rel = [r for r in live_rows if min(ol._score(r.get("product") or "", x["name"]), ol._score(x["name"], r.get("product") or "")) >= 0.6][:6]
        rel_html = ("<h2>この商品の抽選・予約・再販</h2><ul>" + "".join(
            f'<li><a href="/{escape(r["lpath"])}">{escape(r.get("store") or "")} {escape(r.get("product") or "")}</a></li>' for r in rel) + "</ul>") if rel else \
            "<h2>この商品の抽選・予約・再販</h2><p>いま受付中のものはありません。始まったらこのサイトとXでお知らせします。</p>"
        shops = (f'<a class="btn btn-rk" href="{escape(rakuten_link(x["itemUrl"], aff_id))}" target="_blank" rel="nofollow sponsored noopener">楽天で見る（定価）</a>' if x["itemUrl"] else "") + \
            f'<a class="btn btn-yh" href="https://shopping.yahoo.co.jp/search?p={q}" target="_blank" rel="nofollow noopener">Yahoo!で見る</a>' + \
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale" target="_blank" rel="nofollow noopener">メルカリで探す</a>'
        top = "".join(f'<tr><td>{escape(s)}</td><td class="n">{p:,}円</td></tr>' for s, p in x["prices"][:5])
        img = f'<img src="{escape(x["img"])}?_ex=200x200" alt="{escape(x["name"])}" width="120" height="120" loading="lazy">' if x["img"] else ""
        page(f"{x['name']} 買取価格の相場・定価比【{md}更新】｜{brand['name']}",
             f"{x['name']}の新品の最高買取価格は{x['max']:,}円（定価{x['teika']:,}円の{round(x['ratio'] * 100)}%）。1週間前比・1か月前比・買取店ごとの価格・抽選や再販の情報。",
             f'<p><a href="/premium/">定価以上で売れるゲーム・ホビー</a></p><h1>{escape(x["name"])}</h1>'
             f'<div class="pm-row">{img}<div><div>最高買取（新品）</div><div class="pm-big">{x["max"]:,}円</div><div>{escape(x["store"])}・定価 {x["teika"]:,}円（<span class="up">+{round((x["ratio"] - 1) * 100)}%</span>）</div></div></div>'
             f'<table class="pm-t"><tr><th>1週間前比</th><td class="n">{_chg(x["max"], x["w1"])}</td></tr><tr><th>1か月前比</th><td class="n">{_chg(x["max"], x["m1"])}</td></tr></table>'
             f'<h2>商品情報</h2><table class="pm-t">{info_rows(x)}</table>'
             f'<h2>最高買取価格の推移</h2>{chart_svg(x["hist"], x["teika"])}'
             f'<h2>定価で買えるところ</h2><div class="shopb">{shops}</div>{rel_html}'
             f'<h2>買取店ごとの買取価格（新品・上位5店）</h2><table class="pm-t">{top}</table>{note}', f"premium/{x['jan']}/")
    log(f"プレ値商品：{len(items)}件のページ")
    return paths, items
