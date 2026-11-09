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
            return {"price": int(p), "itemUrl": url, "img": game_affi._image(it), "title": it.get("itemName") or "",
                    "caption": (it.get("itemCaption") or "")[:1500]}
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
        r = None
        for attempt in range(3):   # 楽天は1秒に1回まで。混んでいたら少し待ってやり直す
            try:
                r = requests.get(url, params=p, headers=h, timeout=15)
            except Exception as e:
                log(f"楽天ブックス（ゲーム）: {url.split('/')[2]} {e}")
                r = None
                break
            if r.status_code != 429:
                break
            import time
            time.sleep(1.5)
        if r is None:
            continue
        if r.status_code == 429:
            return None
        if r.status_code == 200:
            _books_ok["url"] = url
            items = r.json().get("Items") or []
            if items:
                i = items[0].get("Item", items[0])
                return {"list_price": int(i.get("listPrice") or 0) or None,
                        "sales_date": i.get("salesDate") or "", "maker": i.get("label") or i.get("makerCode") or "",
                        "hardware": i.get("hardware") or "", "caption": (i.get("itemCaption") or "")[:1500], "title": i.get("title") or ""}
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
    # 定価を調べる順：プレ値になりやすい種類（限定・コラボ・たまごっち・GO Plus+ など）を先に、その中は買取価格の高い順
    hot = re.compile(settings.get("premium_hot_words") or r"たまごっち|Tamagotchi|GO ?Plus|amiibo|限定|リミテッド|エディション|Edition|コラボ|セット|パック|Pro|ゼルダ|ポケモン|Xbox|Ally", re.I)
    order = sorted(g, key=lambda j: (not any(hot.search(n) for n in g[j]["names"]), -g[j]["max"]))
    for jan in order:
        c = teika.get(jan)
        if c and parse_dt(c.get("at")) and (t - parse_dt(c["at"])).total_seconds() < 7 * 86400:
            continue
        if left <= 0:
            break
        from common import job_elapsed
        if job_elapsed() > float(settings.get("kaitori_until_sec", 230)) + 20:   # 1回の実行を5分以内に収める
            log("プレ値：時間の上限なので、定価の確認は次の回に回します")
            break
        left -= 1
        try:
            r = _lookup_teika(jan, settings, fetch)
            if r and fetch is None:
                sleep(1.2)
            info = _books_info(jan, settings) if (r and fetch is None) else None
            teika[jan] = dict(r or {}, **(info or {}), at=t.isoformat())
        except Exception as e:
            log(f"プレ値：{jan} 定価の取得失敗 {e}")
            if "429" not in str(e):
                teika[jan] = {"at": t.isoformat()}
        sleep(1.2)
    if fetch is None:   # 定価が分かっていて、商品情報（発売日など）がまだのものを少しずつ埋める
        from common import job_elapsed
        for jan in [j for j in order if (teika.get(j) or {}).get("price") and "sales_date" not in teika[j]][:int(settings.get("premium_info_per_run", 6))]:
            if job_elapsed() > float(settings.get("kaitori_until_sec", 230)) + 20:
                break
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


def watch_map():
    """見張り（worker/game-watch）がJANで見つけた楽天・Amazonの商品ページ {JAN: {rkUrl, asin, azUrl, img, ...}}（読めなければ前回の分）"""
    import hashlib
    import os
    import requests
    cache = load_json("watch_map.json", {})
    key = os.environ.get("X_API_KEY", "").strip()
    if not key:
        return cache
    try:
        admin = hashlib.sha256((key + "game-watch").encode()).hexdigest()[:24]
        r = requests.get(f"https://game-watch.supreme-buyer-1991.workers.dev/map?k={admin}", timeout=15)
        if r.status_code == 200 and isinstance(r.json(), dict):
            cache = r.json()
            save_json("watch_map.json", cache)
    except Exception as e:
        log(f"見張りの商品ページの読み込み失敗 {e}")
    return cache


def _clean(n):
    n = re.sub(r"\s+", " ", n or "")
    return re.sub(r"【.*?】|^BANDAI \(バンダイ\) ", "", n).strip()[:70]


def catalog(settings=None, wmap=None):
    """買取価格が分かる商品すべて（定価・定価比は分かるものだけ）。プレ値の大きい順、定価が分からないものは後ろ"""
    settings = settings or {}
    g = groups()
    teika = load_json(TEIKA, {})
    hist = load_json(HIST, {})
    wmap = wmap if wmap is not None else load_json("watch_map.json", {})
    today = now().date()
    model = re.compile(r"[A-Z]{2,}-?[A-Z0-9]{3,}")
    out = []
    for jan, x in g.items():
        tk = dict(teika.get(jan) or {})
        wm = wmap.get(jan) or {}
        if tk.get("list_price"):
            tk["price"] = tk["list_price"]   # 楽天ブックスの「定価」があればそれ（販売価格より正確）
        if not tk.get("price") and wm.get("rkPrice"):
            tk["price"] = int(wm["rkPrice"])   # 見張り（Cloudflare）がJANで見た楽天ブックスの値段（GitHubの時間を使わずに定価がそろう）
        price = tk.get("price")
        r = x["max"] / price if price else None
        h = hist.get(jan, {})
        name = _clean(tk.get("title") or x["names"][0])
        if not model.search(name):   # 型番が無ければ、型番のある買取店の名前を使う（同じ名前の別モデルを見分けるため）
            withm = [n for n in x["names"] if model.search(n)]
            if withm:
                name = _clean(withm[0])
        out.append({"jan": jan, "name": name, "names": x["names"], "teika": price, "max": x["max"], "store": x["store"],
                    "prices": sorted(x["prices"].items(), key=lambda kv: -kv[1]), "ratio": r,
                    "itemUrl": tk.get("itemUrl") or wm.get("rkUrl", ""), "azUrl": wm.get("azUrl", ""),
                    "img": tk.get("img") or wm.get("img", ""), "hist": h, "w1": _ago(h, 7, today), "m1": _ago(h, 30, today),
                    "sales_date": tk.get("sales_date", ""), "maker": tk.get("maker", ""), "hardware": tk.get("hardware", ""), "caption": tk.get("caption", "")})
    out.sort(key=lambda x: (x["ratio"] is None, -(x["ratio"] or 0), -x["max"]))
    return out


def premium_list(settings=None, wmap=None):
    """プレ値商品（最高買取が定価の premium_min_ratio 倍以上）"""
    settings = settings or {}
    return [x for x in catalog(settings, wmap) if x["ratio"] and x["ratio"] >= float(settings.get("premium_min_ratio", 1.03))]


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
       ".pm-t td.n{text-align:right;font-family:var(--font-num);white-space:nowrap}.up{color:#3ddc84}.dn{color:#ff8a95}.eq,.na{color:#8a93a6}"
       ".chart{width:100%;height:auto;background:#0f121a;border:1px solid #262c3a;border-radius:10px;margin:8px 0}"
       ".chart .ln{fill:none;stroke:#ffd23f;stroke-width:2.5}.chart circle{fill:#ffd23f}.chart .tk{stroke:#5ee0ff;stroke-dasharray:5 5}"
       ".chart .tkl,.chart .ax{fill:#8a93a6;font-size:12px}.pm-big{font-size:28px;font-weight:900;font-family:var(--font-num)}"
       ".pm-row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}.pm-row img{border-radius:10px;background:#fff}"
       ".shopb{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.shopb .btn{padding:10px 14px;border-radius:6px;font-weight:900;text-decoration:none}"
       ".follow{background:#141823;border:1px solid #ffd23f;border-radius:12px;padding:14px 16px;margin:16px 0}.follow p{margin:4px 0}"
       ".mc-box{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:12px 0;padding:10px 12px;border:1px solid #ea352d;border-radius:10px}.mc-box .btn{padding:8px 12px;border-radius:6px;font-weight:900;text-decoration:none}"
       ".btn-x{display:inline-block;margin-top:8px;background:#e9edf5;color:#0b0d12;padding:10px 16px;border-radius:6px;font-weight:900;text-decoration:none}"
       ".pm-shops{white-space:nowrap}.pm-det{text-align:right;white-space:nowrap;width:1%}.pm-sh{display:inline-block;padding:6px 9px;margin-right:4px;border-radius:6px;font-weight:900;text-decoration:none;font-size:13px}"
       ".pm-sh.rk{background:#bf0000;color:#fff}.pm-sh.az{background:#ff9900;color:#0b0d12}"
       ".pm-go{display:inline-block;white-space:nowrap;padding:6px 10px;border-radius:6px;background:#ffd23f;color:#0b0d12;font-weight:900;text-decoration:none;font-size:13px}"
       ".btn-rk{background:#bf0000;color:#fff}.btn-yh{background:#ff0033;color:#fff}.btn-mc{background:#fff;color:#ea352d;border:1px solid #ea352d}.btn-az{background:#ff9900;color:#0b0d12}")


def info_rows(x):
    """商品情報の表：商品名・メーカー・発売日・定価・型番・対応機種・JAN（分かるものだけ）"""
    model = ""
    for n in [x["name"]] + x.get("names", []):
        m = re.search(r"[A-Z]{2,}-?[A-Z0-9]{3,}[A-Z0-9-]*", n)
        if m:
            model = m.group(0)
            break
    rows = [("商品名", x["name"]), ("メーカー", x.get("maker")), ("発売日", x.get("sales_date")), ("定価（税込）", f'{x["teika"]:,}円' if x.get("teika") else ""),
            ("型番", model), ("対応機種", x.get("hardware")), ("JANコード", x["jan"])]
    out = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows if v)
    return out


def features_html(x):
    """商品の詳細・特徴（楽天ブックスの商品説明から）"""
    c = re.sub(r"\s+", " ", x.get("caption") or "").strip()
    if not c:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=。)|■|◆|●|【", c) if len(p.strip()) >= 6][:8]
    return "<h2>商品の詳細・特徴</h2><ul>" + "".join(f"<li>{escape(p.strip('】 '))}</li>" for p in parts) + "</ul><p class=\"note\">商品説明は楽天ブックスの商品情報からの抜粋です。</p>"


def _av(av):
    """いま予約・販売しているお店の枠（sitegen_game.avail_html と同じ）"""
    if not av:
        return ""
    import sitegen_game
    return f"<style>{sitegen_game.AV_CSS}</style>" + sitegen_game.avail_html(av)


def mercari_box(name):
    """「この商品をメルカリで見る」（出品中・売れた価格）"""
    from urllib.parse import quote
    q = quote(re.sub(r"\s+", " ", name or "")[:40])
    return ('<div class="mc-box"><b>この商品をメルカリで見る</b>'
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale" target="_blank" rel="nofollow noopener">出品中を見る</a>'
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=sold_out" target="_blank" rel="nofollow noopener">売れた価格を見る</a></div>')


FOLLOW = ('<div class="follow"><p><b>🔔 このページでは、楽天・Amazonで定価で販売されていないかを定期的にチェックしています。</b></p>'
          '<p>販売が始まったら X（@a9994aaa）ですぐ通知するので、フォロー＆通知ONで待っててね！</p>'
          '<a class="btn btn-x" href="https://x.com/intent/follow?screen_name=a9994aaa" target="_blank" rel="noopener">Xでフォローする</a></div>')


def _ratio_html(x):
    if not x["ratio"]:
        return '<span class="na">定価確認中</span>'
    pc = round((x["ratio"] - 1) * 100)
    return f'<span class="{"up" if pc > 0 else "dn" if pc < 0 else "eq"}">{"+" if pc > 0 else ""}{pc}%</span>'


SEARCH_JS = r"""<script>
(function(){var q=(new URLSearchParams(location.search).get("q")||"").trim();var box=document.querySelector(".qsearch input");if(box)box.value=q;
var n=document.getElementById("qs-n"),r=document.getElementById("qs-r");if(!q){n.textContent="商品名（例：PS5 Pro、たまごっち）かJANコード（13けた）を入れてください。";return;}
function norm(s){return (s||"").normalize("NFKC").toLowerCase().replace(/\s+/g," ");}
fetch("/search.json").then(function(x){return x.json();}).then(function(d){
var ws=norm(q).split(" ").filter(Boolean),dig=q.replace(/\D/g,"");
var hit=d.filter(function(e){var t=norm(e[0]);if(dig.length>=8&&e[1]&&e[1].indexOf(dig)>=0)return true;return ws.every(function(w){return t.indexOf(w)>=0;});});
n.textContent="「"+q+"」の検索結果："+hit.length+"件";
r.innerHTML=hit.slice(0,100).map(function(e){return '<a class="qs-i" href="'+e[2]+'"><b>'+e[0].replace(/[<>&]/g,"")+'</b><span>'+(e[3]?"定価 "+e[3].toLocaleString()+"円 ":"")+(e[4]?"最高買取 "+e[4].toLocaleString()+"円":"")+(e[1]?" ・JAN "+e[1]:"")+'</span></a>';}).join("")||"<p>見つかりませんでした。言葉を短くするか、別の言い方で探してみてください。</p>";});})();
</script><style>.qs-i{display:block;padding:12px 14px;margin:8px 0;border:1px solid #262c3a;border-radius:10px;background:#141823;color:#e9edf5;text-decoration:none}.qs-i b{display:block}.qs-i span{font-size:13px;color:#8a93a6}</style>"""


def write_pages(out, cats, site, brand, live_rows, settings, simple_page, aff_id=""):
    """/premium/（定価以上で売れる）・/souba/（買取相場の一覧）・/premium/<JAN>/（商品ごと）を書く。書いたパスの一覧を返す"""
    from urllib.parse import quote
    import official_link as ol
    from game_affi import rakuten_link
    allx = catalog(settings)
    items = [x for x in allx if x["ratio"] and x["ratio"] >= float(settings.get("premium_min_ratio", 1.03))]
    upd = now()
    md = f"{upd.month}/{upd.day}"
    paths = []
    note = ('<p class="note">買取価格は各買取店が公開している新品（未開封）の買取価格を毎日読み取ったものです（店の条件で変わることがあります）。'
            '定価は楽天ブックスの定価・販売価格です。転売を勧めるものではありません。リンクの一部は広告（PR）です。</p>')

    def page(title, desc, body, path):
        html = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{escape(title)}</title><meta name="description" content="{escape(desc)}"><link rel="canonical" href="{site}/{path}">'
                f'<link rel="icon" href="/favicon.svg" type="image/svg+xml"><style></style></head><body><style>{CSS}</style>{body}</body></html>')
        d = out / path
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(simple_page(cats, html), encoding="utf-8")
        paths.append(path)

    def table(xs):
        rows = "".join(
            f'<tr><td><a href="/premium/{x["jan"]}/">{escape(x["name"])}</a></td><td class="n">{(str(format(x["teika"], ",")) + "円") if x["teika"] else "—"}</td>'
            f'<td class="n">{x["max"]:,}円</td><td class="n">{_ratio_html(x)}</td><td class="n">{_chg(x["max"], x["w1"])}</td></tr>' for x in xs)
        return f'<table class="pm-t"><thead><tr><th>商品</th><th>定価</th><th>最高買取</th><th>定価比</th><th>1週間前比</th></tr></thead><tbody>{rows}</tbody></table>'

    page(f"定価以上で売れるゲーム・ホビー一覧【{md}更新】買取価格の相場｜{brand['name']}",
         "定価より高く買い取られているゲーム機・周辺機器・ホビーの一覧。買取店の新品の最高買取価格・定価との差・1週間前比を毎日更新。",
         f'<h1>定価以上で売れるゲーム・ホビー</h1><p>買取店の新品の最高買取価格が定価を上回っている商品です（{md}更新・{len(items)}件）。'
         f'楽天・Amazonで定価で売り出されたら、Xですぐお知らせします。<a href="/souba/">すべての商品の買取相場（{len(allx)}件）</a></p>'
         + (table(items) if items else "<p>いま該当する商品はありません。</p>") + note, "premium/")
    page(f"ゲーム・ホビー買取相場一覧【{md}更新】{len(allx)}商品の最高買取価格｜{brand['name']}",
         "ゲーム機・周辺機器・たまごっち・ホビーの新品の最高買取価格（買取店9店）と定価比・1週間前比の一覧。毎日更新。",
         f'<h1>ゲーム・ホビー買取相場一覧</h1><p>買取店9店の新品の買取価格から、商品ごとのいちばん高い価格を毎日まとめています（{md}更新・{len(allx)}件）。'
         f'<a href="/premium/">定価以上で売れる商品だけを見る</a></p>' + table(allx) + note, "souba/")
    for x in allx:
        q = quote(re.sub(r"\s+", " ", x["name"])[:40])
        rel = [r for r in live_rows if min(ol._score(r.get("product") or "", x["name"]), ol._score(x["name"], r.get("product") or "")) >= 0.6][:6]
        rel_html = ("<h2>この商品の抽選・予約・再販</h2><ul>" + "".join(
            f'<li><a href="/{escape(r["lpath"])}">{escape(r.get("store") or "")} {escape(r.get("product") or "")}</a></li>' for r in rel) + "</ul>") if rel else \
            "<h2>この商品の抽選・予約・再販</h2><p>いま受付中のものはありません。楽天・Amazonで販売が始まったらXでお知らせします。</p>"
        shops = (f'<a class="btn btn-rk" href="{escape(rakuten_link(x["itemUrl"], aff_id))}" target="_blank" rel="nofollow sponsored noopener">楽天で見る</a>' if x["itemUrl"] else "") + \
            (f'<a class="btn btn-az" href="{escape(x["azUrl"])}" target="_blank" rel="nofollow sponsored noopener">Amazonで見る</a>' if x.get("azUrl") else "") + \
            f'<a class="btn btn-yh" href="https://shopping.yahoo.co.jp/search?p={q}" target="_blank" rel="nofollow noopener">Yahoo!で見る</a>' + \
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale" target="_blank" rel="nofollow noopener">メルカリで探す</a>'
        top = "".join(f'<tr><td>{escape(s_)}</td><td class="n">{p_:,}円</td></tr>' for s_, p_ in x["prices"][:5])
        img = f'<img src="{escape(x["img"])}" alt="{escape(x["name"])}" width="120" height="120" loading="lazy">' if x["img"] else ""
        tk = f'定価 {x["teika"]:,}円（{_ratio_html(x)}）' if x["teika"] else "定価：確認中"
        desc = f"{x['name']}の新品の最高買取価格は{x['max']:,}円" + (f"（定価{x['teika']:,}円の{round(x['ratio'] * 100)}%）" if x["teika"] else "") + "。1週間前比・1か月前比・買取店ごとの価格・抽選や再販の情報。"
        page(f"{x['name']} 買取価格の相場・定価比【{md}更新】｜{brand['name']}", desc,
             f'<p><a href="/souba/">ゲーム・ホビー買取相場一覧</a> ／ <a href="/premium/">定価以上で売れる</a></p><h1>{escape(x["name"])}</h1>'
             f'<div class="pm-row">{img}<div><div>最高買取（新品）</div><div class="pm-big">{x["max"]:,}円</div><div>{escape(x["store"])}・{tk}</div></div></div>'
             f'<table class="pm-t"><tr><th>1週間前比</th><td class="n">{_chg(x["max"], x["w1"])}</td></tr><tr><th>1か月前比</th><td class="n">{_chg(x["max"], x["m1"])}</td></tr></table>{mercari_box(x["name"])}'
             f'{FOLLOW}<h2>買えるところ</h2><div class="shopb">{shops}</div>'
             f'<h2>商品情報</h2><table class="pm-t">{info_rows(x)}</table>{features_html(x)}'
             f'<h2>最高買取価格の推移</h2>{chart_svg(x["hist"], x["teika"] or x["max"])}{rel_html}'
             f'<h2>買取店ごとの買取価格（新品・上位5店）</h2><table class="pm-t">{top}</table>{note}', f"premium/{x['jan']}/")
    # サイトに載っている抽選・予約・発売日の商品で、買取相場の一覧に無いもの → 商品ページを作る（発売前は相場「予測不能」）
    import hashlib
    from dedupe import norm_product
    import gamecats
    cats_by = gamecats.by_id(False)
    groups_ = {}
    for r in live_rows:
        nm = (r.get("product") or "").strip()
        if not nm or any(min(ol._score(nm, x["name"]), ol._score(x["name"], nm)) >= 0.75 for x in allx):
            continue
        groups_.setdefault(norm_product(nm), []).append(r)
    made = 0
    for key, rs in groups_.items():
        r0 = max(rs, key=lambda r: (bool((r.get("rk") or {}).get("u")), bool(r.get("az")), len(r.get("product") or "")))
        nm = re.sub(r"\s+", " ", r0.get("product") or "")[:70]
        slug = item_slug(r0.get("product") or key)
        rel = rs[:8]
        rel_html = "<h2>この商品の抽選・予約・発売の情報</h2><ul>" + "".join(
            f'<li><a href="/{escape(r["lpath"])}">{escape(r.get("store") or "")} {escape(r.get("product") or "")}</a></li>' for r in rel) + "</ul>"
        rel_date = next((r.get("end") for r in rs if r.get("kind") == "release" and r.get("end")), "")
        rd = parse_dt(rel_date) if rel_date else None
        before = bool(rd and rd > upd)
        souba = "予測不能（発売前）" if before else "買取価格の情報はまだありません"
        price = next((r.get("price") for r in rs if r.get("price")), "")
        q = quote(nm[:40])
        rk = (r0.get("rk") or {})
        shops = (f'<a class="btn btn-rk" href="{escape(rk["u"])}" target="_blank" rel="nofollow sponsored noopener">楽天で見る</a>' if rk.get("u") else "") + \
            (f'<a class="btn btn-az" href="{escape(r0["az"])}" target="_blank" rel="nofollow sponsored noopener">Amazonで見る</a>' if r0.get("az") else "") + \
            f'<a class="btn btn-yh" href="https://shopping.yahoo.co.jp/search?p={q}" target="_blank" rel="nofollow noopener">Yahoo!で見る</a>' + \
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale" target="_blank" rel="nofollow noopener">メルカリで探す</a>'
        img = f'<img src="{escape(rk["img"])}" alt="{escape(nm)}" width="120" height="120" loading="lazy">' if rk.get("img") else ""
        cat = (cats_by.get(r0.get("game")) or {}).get("short", "")
        info = [("商品名", nm), ("カテゴリ", cat), ("発売日", f"{rd.year}年{rd.month}月{rd.day}日" if rd else ""), ("定価（税込）", price),
                ("JANコード", r0.get("jan") or "")]
        info_h = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in info if v)
        page(f"{nm} 抽選・予約・再販と相場・定価【{md}更新】｜{brand['name']}",
             f"{nm}の抽選・予約・再販の受付状況、定価、相場（{souba}）、楽天・Amazonの販売ページ。販売開始はXで通知。",
             f'<p><a href="/souba/">ゲーム・ホビー買取相場一覧</a></p><h1>{escape(nm)}</h1>'
             f'<div class="pm-row">{img}<div><div>市場相場</div><div class="pm-big" style="font-size:20px">{escape(souba)}</div>'
             f'<div>{("定価 " + escape(str(price))) if price else ""}</div></div></div>{_av(next((r.get("avail") for r in rs if r.get("avail")), None))}{mercari_box(nm)}'
             f'{FOLLOW}<h2>買えるところ</h2><div class="shopb">{shops}</div>{rel_html}<h2>商品情報</h2><table class="pm-t">{info_h}</table>{note}', f"item/{slug}/")
        made += 1
    # 商品名・JANコードで検索：/search.json（商品ページ・抽選の一覧）と /search/
    import json as _json
    idx = [[x["name"], x["jan"], f"/premium/{x['jan']}/", x["teika"] or 0, x["max"]] for x in allx]
    idx += [[re.sub(r"\s+", " ", rs_[0].get("product") or "")[:70], rs_[0].get("jan") or "", f"/item/{item_slug(rs_[0].get('product') or k_)}/", 0, 0]
            for k_, rs_ in groups_.items()]
    idx += [[f'{r.get("store") or ""} {r.get("product") or ""}'.strip()[:80], r.get("jan") or "", "/" + r["lpath"], 0, 0] for r in live_rows if r.get("lpath")]
    (out / "search.json").write_text(_json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    page(f"商品名・JANコードで検索｜{brand['name']}", "ゲーム機・ホビーの商品を商品名やJANコードで検索。定価・買取相場・抽選や発売の情報のページに移動できます。",
         '<h1>商品名・JANコードで検索</h1><p id="qs-n" class="note"></p><div id="qs-r"></div>' + SEARCH_JS, "search/")
    log(f"相場ページ：{len(allx)}件（うち定価以上で売れる {len(items)}件）、抽選・発売の商品ページ：{made}件")
    return paths, items


_PM_CACHE = {}


def premium_match(name, settings=None):
    """商品名が「定価以上で売れる商品」に当たるなら、その商品（dict）を返す。当たらなければ None"""
    import official_link as ol
    if "list" not in _PM_CACHE:
        try:
            _PM_CACHE["list"] = premium_list(settings or {})
        except Exception:
            _PM_CACHE["list"] = []
    for x in _PM_CACHE["list"]:
        for n in [x["name"]] + x.get("names", [])[:3]:
            if min(ol._score(name or "", n), ol._score(n, name or "")) >= 0.75:
                return x
    return None


def worth_posting(it, settings=None):
    """Xに出す価値があるか（11/9 ユーザーの指示）：定価以上で売れる商品か、品薄の商品（抽選・招待販売になっているもの）だけ"""
    if it.get("kind") in ("lottery", "invite", "fukubukuro"):
        return True
    return premium_match(it.get("product") or "", settings) is not None


# ---- カテゴリごとの商品一覧（左メニューの数・カテゴリページの商品一覧に使う）----
# 商品名からカテゴリを決める順番（細かいものを先に。たまごっち・GO Plus+ が「ポケモン」に入らないように等）
CAT_ORDER = ["digital_toys", "pc_parts", "handheld_pc", "xbox", "switch2", "switch1", "ps5", "game_limited", "gunpla", "beyblade", "pokecen",
             "chiikawa", "lego", "tomica", "bearbrick", "figure", "ichibankuji", "fukubukuro"]


def watch_map_cached():
    return load_json("watch_map.json", {})


def cat_of(names):
    """商品名（複数）からカテゴリid（当たらなければ None）"""
    import gamecats
    hs = gamecats.hints()
    text = " ".join(names or [])
    for cid in CAT_ORDER + [c for c in hs if c not in CAT_ORDER]:
        h = hs.get(cid)
        if h and h.search(text):
            return cid
    return None


def item_slug(name):
    """抽選・発売の商品ページ（/item/<slug>/）の名前"""
    import hashlib
    from dedupe import norm_product
    return "p" + hashlib.sha1(norm_product(name).encode()).hexdigest()[:10]


def product_index(settings, live_rows):
    """{カテゴリid: [{"name","teika","max","store","url","img","ratio"}]}：買取相場の商品（/premium/<JAN>/）と、
    抽選・発売の商品（/item/<slug>/。買取相場に無いもの）。カテゴリの中は「定価以上で売れる」順→最高買取の高い順"""
    import official_link as ol
    import game_affi
    from game_affi import rakuten_link
    aff = game_affi.affiliate_id(settings or {})
    out = {}
    allx = catalog(settings, watch_map_cached())
    for x in allx:
        cid = cat_of(x["names"] + [x["name"]])
        if not cid:
            continue
        out.setdefault(cid, []).append({"name": x["name"], "teika": x["teika"], "max": x["max"], "store": x["store"], "ratio": x["ratio"],
                                        "url": f"/premium/{x['jan']}/", "img": x.get("img", ""),
                                        "rk": rakuten_link(x["itemUrl"], aff) if x.get("itemUrl") else "", "az": x.get("azUrl", "")})
    seen = set()
    from dedupe import norm_product
    for r in live_rows:
        nm = (r.get("product") or "").strip()
        k = norm_product(nm)
        if not nm or k in seen or r.get("game") is None:
            continue
        if any(min(ol._score(nm, x["name"]), ol._score(x["name"], nm)) >= 0.75 for x in allx):
            continue
        seen.add(k)
        m = re.search(r"([\d,]{4,})", str(r.get("price") or ""))
        out.setdefault(r["game"], []).append({"name": re.sub(r"\s+", " ", nm)[:70], "teika": int(m.group(1).replace(",", "")) if m else None,
                                              "max": None, "store": "", "ratio": None, "url": f"/item/{item_slug(nm)}/",
                                              "img": ((r.get("rk") or {}).get("img") or ""),
                                              "rk": (r.get("rk") or {}).get("u", ""), "az": r.get("az", "")})
    for cid in out:
        out[cid].sort(key=lambda p: (not (p["ratio"] and p["ratio"] >= 1.03), -(p["max"] or 0)))
    return out


def _shop_mini(p):
    """一覧の行の「楽天」「Amazon」の小さいボタン（その商品のページ。アフィリエイト）"""
    out = ""
    if p.get("rk"):
        out += f'<a class="pm-sh rk" href="{escape(p["rk"])}" target="_blank" rel="nofollow sponsored noopener">楽天</a>'
    if p.get("az"):
        out += f'<a class="pm-sh az" href="{escape(p["az"])}" target="_blank" rel="nofollow sponsored noopener">Amazon</a>'
    return out


def cat_products_html(prods, short):
    """カテゴリページの商品一覧の表（商品・定価・最高買取・詳細を見る）"""
    if not prods:
        return f'<section class="sec"><h2>{escape(short)}の商品一覧</h2><p>商品はまだありません。</p></section>'
    rows = "".join(
        f'<tr><td>{escape(p["name"])}</td><td class="n">{(format(p["teika"], ",") + "円") if p["teika"] else "—"}</td>'
        f'<td class="n">{(format(p["max"], ",") + "円" + ("<br><small>" + escape(p["store"]) + "</small>" if p["store"] else "")) if p["max"] else "—"}'
        f'{(" <span class=\"up\">+" + str(round((p["ratio"] - 1) * 100)) + "%</span>") if p["ratio"] and p["ratio"] >= 1.03 else ""}</td>'
        f'<td class="pm-shops">{_shop_mini(p)}</td><td class="pm-det"><a class="pm-go" href="{escape(p["url"])}">詳細を見る</a></td></tr>' for p in prods)
    return (f'<section class="sec pm-list"><h2>{escape(short)}の商品一覧（{len(prods)}件）</h2>'
            '<p class="note">最高買取は買取店の新品の買取価格でいちばん高いもの。定価で売り出されたらXで通知します。</p>'
            f'<div style="overflow-x:auto"><table class="pm-t"><thead><tr><th>商品</th><th>定価</th><th>最高買取</th><th>買えるところ</th><th></th></tr></thead><tbody>{rows}</tbody></table></div></section>')
