"""ゲーム・ホビー入荷速報：定価以上で売れる商品（プレ値商品）

・買取店（game_kaitori が毎日読む9店）の新品の買取価格を、JANコードごとにまとめる（JANが無い店の商品は商品名で寄せる）
・定価は楽天ブックスの販売価格（JANで探す。楽天ブックスは基本的に定価で売っている）。1回 premium_teika_per_run 件ずつ調べ、7日ごとに調べ直す
・いちばん高い買取価格が定価の premium_min_ratio 倍以上の商品を「プレ値商品」として、/premium/ と /premium/<JAN>/ を作る
・毎日の最高買取価格を state/game/premium_hist.json に残す（チャート・1週間前比・1か月前比に使う。400日分）
"""
import re
from datetime import timedelta
from html import escape

from common import ROOT, load_json, save_json, now, parse_dt, log
from common import parse_dt as _pd

HIST = "premium_hist.json"
TEIKA = "premium_teika.json"


# ゲーム・ホビー以外（カメラ・スマホ・家電・お酒など）は載せない（買取店の一覧に混ざってくるため・11/9）
# 買取価格のそばに出す注意書き（11/11 ユーザーの指示：表示の金額から変わっている場合があると書いておく）
CHANGE_NOTE = "買取価格は表示の金額から変わっている場合があります。売る前に必ず買取店のサイトでご確認ください。"
NOT_HOBBY = re.compile(r"カメラ|レンズ|PowerShot|EOS|Nikon|LUMIX|instax|チェキ|写ルンです|iPhone|iPad|Galaxy|Pixel|Xperia|AQUOS|arrows|MacBook|AirPods|"
                       r"Apple Watch|Dyson|ダイソン|ドライヤー|炊飯|掃除機|冷蔵庫|洗濯|電子レンジ|ウイスキー|ワイン|イヤホン|ヘッドホン|スマートウォッチ|Kindle|ルーター|Wi-Fi|"
                       r"SIGMA|TAMRON|FUJIFILM|Canon|CANON|SONY α|GoPro|DJI|Fitbit|Garmin|ロボット掃除機|美容|ReFa|シェーバー|"
                       # トレカはトレカ抽選ナビの担当（このサイトには載せない）
                       r"カードゲーム|BOOSTER|ブースター|フュージョンワールド|ダイバーズ|バトスピ|ポケモンカード|ポケカ|遊戯王|デュエル・?マスターズ|デュエマ|拡張パック|ブースターパック|トレカ|ヴァイスシュヴァルツ|ユニオンアリーナ|"
                       r"\bOP-\d|\bEB-\d|\bPRB-\d|\bSV\d|\bM\d[a-z]?\b.*BOX")


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
            if NOT_HOBBY.search(name or ""):
                continue
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
            sc = max(ol.same_item_score(name, n) for n in x["names"])   # 11/10：どの店の名前とも比べる（数字が違う名前は0）
            if sc >= 0.85 and (best is None or sc > best[0]):
                best = (sc, jan)
        if best:
            x = g[best[1]]
            x["prices"][store] = max(price, x["prices"].get(store, 0))
    for x in g.values():
        ps = sorted(x["prices"].items(), key=lambda kv: -kv[1])
        # 1店だけ飛び抜けて高い（2番目の店の1.5倍より上）ときは、その店の読み間違い・別の商品とみて使わない（11/10：PS5が10万8千円になっていた）
        if len(ps) >= 2 and ps[0][1] > ps[1][1] * 1.5:
            x["outlier"] = ps[0]
            x["prices"].pop(ps[0][0])
            ps = ps[1:]
        x["store"], x["max"] = ps[0]
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


def overrides():
    """config/game/premium_overrides.yaml：楽天ブックスで分からない商品の定価・分かりにくい商品名を手で直す {JAN: {...}}"""
    import yaml
    p = ROOT / "config" / "game" / "premium_overrides.yaml"
    try:
        y = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {str(k): v for k, v in y.items() if isinstance(v, dict)}


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
    ov_all = overrides()
    try:
        import game_facts as _gf
    except Exception:
        _gf = None
    for jan, x in g.items():
        tk = dict(teika.get(jan) or {})
        wm = wmap.get(jan) or {}
        ov = ov_all.get(jan) or {}
        # 定価の決め方（11/14：楽天ブックスの「販売価格」は割引後のことがあり、定価として出すとプレ値が大きく見えていた。
        # タカラトミー公式では UX-10 は税込5,700円なのに、サイトは楽天ブックスの4,579円を「定価」にしていた）
        #   1. 手で調べた定価（premium_overrides.yaml）
        #   2. メーカー公式ページの希望小売価格（game_facts が取ったもの）
        #   3. 楽天ブックスの「定価」（listPrice）
        #   4. 楽天ブックスの販売価格・見張りが見た楽天ブックスの値段 →「楽天ブックスの販売価格」と書く
        tnote = ""
        msrp = _gf.msrp_of(_gf.get(jan)) if _gf else None
        if ov.get("teika"):
            tk["price"], tnote = int(ov["teika"]), ov.get("teika_note", "")
        elif msrp:
            tk["price"], tnote = msrp, "メーカー希望小売価格（公式）"
        elif tk.get("list_price"):
            tk["price"] = tk["list_price"]
        elif tk.get("price"):
            tnote = "楽天ブックスの販売価格"
        elif wm.get("rkPrice"):
            tk["price"], tnote = int(wm["rkPrice"]), "楽天ブックスの販売価格"
        price = tk.get("price")
        r = x["max"] / price if price else None
        h = hist.get(jan, {})
        name = _clean(tk.get("title") or x["names"][0])
        if ov.get("name"):
            name = ov["name"]
        elif not model.search(name):   # 型番が無ければ、型番のある買取店の名前を使う（同じ名前の別モデルを見分けるため）
            withm = [n for n in x["names"] if model.search(n)]
            if withm:
                name = _clean(withm[0])
        if NOT_HOBBY.search(" ".join([name, tk.get("title") or "", (tk.get("caption") or "")[:200]] + x["names"])):   # 楽天の商品名・説明で分かるトレカ・家電も外す
            continue
        out.append({"jan": jan, "name": name, "names": x["names"], "teika": price, "max": x["max"], "store": x["store"],
                    "prices": sorted(x["prices"].items(), key=lambda kv: -kv[1]), "ratio": r,
                    "itemUrl": tk.get("itemUrl") or wm.get("rkUrl", ""), "azUrl": wm.get("azUrl", ""),
                    "img": tk.get("img") or wm.get("img", ""), "hist": h, "w1": _ago(h, 7, today), "m1": _ago(h, 30, today),
                    "teika_note": tnote,
                    "sales_date": tk.get("sales_date", "") or ov.get("sales_date", ""), "maker": tk.get("maker", ""), "hardware": tk.get("hardware", ""), "caption": tk.get("caption", "")})
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


def _notice_p(text):
    """カテゴリの注意書き（お酒の「20歳になってから」など）。無ければ空"""
    return ('<p class="cat-notice" style="margin:8px 0;padding:8px 12px;border:1px solid #e0b4b4;background:#fff5f5;'
            f'color:#7a1f1f;border-radius:8px;font-size:13px">🔞 {escape(text)}</p>') if text else ""


def chart_svg(h, teika, label="定価"):
    """最高買取価格のチャート（直近90日・定価の線つき）"""
    pts = sorted(h.items())[-90:]
    if not pts:
        return ""
    W, H, P = 640, 220, 34
    vals = [v for _, v in pts] + ([teika] if teika else [])
    lo, hi = min(vals) * 0.97, max(vals) * 1.03
    def X(i):
        return P + (W - 2 * P) * (i / max(1, len(pts) - 1))
    def Y(v):
        return H - P - (H - 2 * P) * ((v - lo) / max(1, hi - lo))
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    dots = "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3"><title>{d} {v:,}円</title></circle>' for i, (d, v) in enumerate(pts))
    ty = Y(teika) if teika else 0
    tk_line = (f'<line x1="{P}" x2="{W - P}" y1="{ty:.1f}" y2="{ty:.1f}" class="tk"/><text x="{W - P}" y="{ty - 6:.1f}" text-anchor="end" class="tkl">{label} {teika:,}円</text>'
               if teika else "")   # 定価が分からないときは線を引かない（11/11：最高買取を「定価」と表示していた）
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="最高買取価格の推移">'
            f'{tk_line}'
            f'<polyline points="{line}" class="ln"/>{dots}'
            f'<text x="{P}" y="{H - 8}" class="ax">{pts[0][0][5:].replace("-", "/")}</text><text x="{W - P}" y="{H - 8}" text-anchor="end" class="ax">{pts[-1][0][5:].replace("-", "/")}</text></svg>')


CSS = (".pm-facts ul{padding-left:1.2em;line-height:1.85;color:#cfd5e1}.pm-facts .note{font-size:12px}.sellb{display:inline-block;margin-top:6px;font-size:13px;color:#8a93a6!important}.pm-ai p{line-height:1.85;color:#cfd5e1}.pm-intro{line-height:1.8;margin:8px 0 14px;color:#cfd5e1}.faq{border:1px solid #262c3a;border-radius:10px;padding:10px 14px;margin:8px 0;background:#141823}.faq summary{font-weight:900;cursor:pointer}.faq p{margin:8px 0 0;line-height:1.7}"
       ".pm-t{width:100%;border-collapse:collapse;font-size:14px}.pm-t td,.pm-t th{padding:8px 6px;border-bottom:1px solid var(--line,#262c3a);text-align:left}"
       ".pm-t td.n{text-align:right;font-family:var(--font-num);white-space:nowrap}.up{color:#3ddc84}.dn{color:#ff8a95}.eq,.na{color:#8a93a6}"
       ".chart{width:100%;height:auto;background:#0f121a;border:1px solid #262c3a;border-radius:10px;margin:8px 0}"
       ".chart .ln{fill:none;stroke:#ffd23f;stroke-width:2.5}.chart circle{fill:#ffd23f}.chart .tk{stroke:#5ee0ff;stroke-dasharray:5 5}"
       ".chart .tkl,.chart .ax{fill:#8a93a6;font-size:12px}.pm-big{font-size:28px;font-weight:900;font-family:var(--font-num)}"
       ".pm-row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}.pm-row img{border-radius:10px;background:#fff}"
       ".shopb{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.shopb .btn{padding:10px 14px;border-radius:6px;font-weight:900;text-decoration:none}"
       "h2 .hot{font-size:.7em;color:#ff6b3d;font-weight:900;margin-left:6px}.follow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#141823;border:1px solid #ffd23f;border-radius:12px;padding:12px 14px;margin:16px 0}.follow p{margin:0;flex:1 1 200px}.follow .btn{white-space:nowrap;flex:1 1 140px;text-align:center}"
       ".mc-box{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0;padding:10px 12px;border:1px solid #ea352d;border-radius:10px}.mc-box b{grid-column:1/-1}.mc-box .btn{display:block;text-align:center;padding:11px 6px;border-radius:8px;font-weight:900;text-decoration:none;white-space:nowrap}"
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
    rows = [("商品名", x["name"]), ("メーカー", x.get("maker")), ("発売日", x.get("sales_date")), (f"{tword(x)}（税込）", f'{x["teika"]:,}円' if x.get("teika") else ""),
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


SNAME = {"buy": "在庫あり（販売中）", "pre": "予約受付中", "invite": "招待受付中", "none": "売り切れ・販売なし"}


def stock_html(jan, wm_all, name):
    """楽天ブックス・Amazon（Amazon.co.jp が売っているもの）の今の状態と、販売・在庫の履歴（見張りの記録）→ (今の状態の節, 履歴の節)"""
    from datetime import timezone as _tz
    jst = _tz(timedelta(hours=9))

    def parse_dt(v):   # 見張りの日時は世界時（Z）なので日本時間に直す
        d = _pd(v)
        return d.astimezone(jst) if d else None
    wm = wm_all.get(jan) or {}
    st2, hist = wm_all.get("_st2") or {}, wm_all.get("_hist") or {}
    ids = {"rk": ["j" + jan], "az": [i for i in (wm.get("asin"), "j" + jan) if i]}
    shop = {"rk": "楽天ブックス", "az": "Amazon"}
    now_rows, h_rows = [], []
    for w in ("az", "rk"):
        cur = next((st2.get(w, {}).get(i) for i in ids[w] if st2.get(w, {}).get(i)), None)
        if cur:
            d = parse_dt(cur.get("at"))
            now_rows.append((shop[w], SNAME.get(cur.get("s"), cur.get("s")), cur.get("p") or 0, d))
        for i in ids[w]:
            for h in (hist.get(w, {}).get(i) or []):
                h_rows.append((parse_dt(h.get("t")), shop[w], SNAME.get(h.get("s"), h.get("s")), h.get("p") or 0))
            if hist.get(w, {}).get(i):
                break
    if not now_rows:
        return "", ""
    last = max((r[3] for r in now_rows if r[3]), default=None)
    any_buy = any("売り切れ" not in r[1] for r in now_rows)
    lead = (f"{name}の楽天ブックス・Amazonでの販売状況です（{last.month}/{last.day} {last:%H:%M}時点）。" if last else "") + \
        ("いま定価付近で買える可能性があります。売り切れる前に確認してください。" if any_buy else
         "いまはどちらも売り切れ・販売なしです。販売が始まったら X（@a9994aaa）ですぐお知らせします。")
    cur_h = (f'<h2>{escape(name)}の最新の販売状況</h2><p class="pm-intro">{escape(lead)}</p><table class="pm-t"><tr><th>お店</th><th>状態</th><th>価格</th></tr>'
             + "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>{(format(c, ',') + '円') if c else '—'}</td></tr>" for a, b, c, _ in now_rows) + "</table>")
    h_rows = sorted([r for r in h_rows if r[0]], key=lambda r: r[0], reverse=True)[:12]
    hist_h = ("<h2>楽天・Amazonの販売・在庫の履歴</h2><table class=\"pm-t\"><tr><th>日時</th><th>お店</th><th>状態</th><th>価格</th></tr>"
              + "".join(f"<tr><td>{d.month}/{d.day} {d:%H:%M}</td><td>{escape(a)}</td><td>{escape(b)}</td><td>{(format(c, ',') + '円') if c else '—'}</td></tr>" for d, a, b, c in h_rows)
              + "</table><p class=\"note\">楽天ブックスとAmazon（Amazon.co.jpが販売するもの）を数十分〜1時間ごとに見て、状態が変わったときだけ記録しています（11/9から記録）。</p>") if h_rows else ""
    return cur_h, hist_h


BUY_CSS = (".buyb{margin:10px 0 16px;padding:14px;border:2px solid #ffd23f;border-radius:14px;background:#17140a}"
           ".buyb .xin{display:none;margin:0 0 10px;font-weight:900;line-height:1.6;color:#ffd23f}.buyb.on .xin{display:block}"
           ".buyb .bb{display:grid;grid-template-columns:1fr 1fr;gap:8px}.buyb .bb a{display:flex;align-items:center;justify-content:center;padding:14px 8px;"
           "border-radius:10px;font-weight:900;font-size:16px;text-decoration:none;text-align:center}.buyb .bb .az{background:#ff9900;color:#0b0d12}"
           ".buyb .bb .rk{background:#bf0000;color:#fff}.buyb .bb a.hl{outline:3px solid #fff;outline-offset:2px}.buyb small{display:block;margin-top:8px;color:#a3abbd;font-size:12px;line-height:1.6}")
BUY_JS = ("<script>(function(){var w=(new URLSearchParams(location.search).get('x')||'');var b=document.querySelector('.buyb');if(!b||!/^(az|rk)$/.test(w))return;"
          "b.classList.add('on');var n=w==='az'?'Amazon':'楽天';b.querySelector('.xin').textContent='🚨 Xの販売速報から来た方へ：'+n+'で販売・予約が再開しました。'"
          "+'人気商品はすぐ売り切れるので、下の「'+n+'で見る」から早めに確認してください（すでに売り切れの場合もあります）。';"
          "var a=b.querySelector('.bb .'+w);if(a){a.classList.add('hl');a.parentNode.insertBefore(a,a.parentNode.firstChild);}"
          "try{b.scrollIntoView({block:'start'});window.scrollBy(0,-12);}catch(e){}})();</script>")   # 速報から来た人はメニューを飛ばして購入ボタンへ


def buy_box(az, rk, name):
    """ページの上の方の購入ボタン（Amazon・楽天）。Xの販売速報（?x=az / ?x=rk）から来た人には、どのお店で再開したかの案内を出してそのボタンを目立たせる"""
    if not (az or rk):
        return ""
    btn = (f'<a class="az" href="{escape(az)}" target="_blank" rel="nofollow sponsored noopener">Amazonで見る</a>' if az else "") + \
          (f'<a class="rk" href="{escape(rk)}" target="_blank" rel="nofollow sponsored noopener">楽天で見る</a>' if rk else "")
    return (f'<style>{BUY_CSS}</style><div class="buyb"><p class="xin"></p><div class="bb">{btn}</div>'
            f'<small>{escape(name)}を定価で買えるお店のページです。在庫・価格はお店のページで確認してください。販売が始まったら X（@a9994aaa）で速報します。</small></div>{BUY_JS}')


def _sl(store, jan, name, cls=""):
    """買取店の名前 → その店のページへのリンク（広告ではない）"""
    try:
        import game_kaitori
        u = game_kaitori.store_link(store, jan, name)
    except Exception:
        u = ""
    return (f'<a{(" class=" + chr(34) + cls + chr(34)) if cls else ""} href="{escape(u)}" target="_blank" rel="nofollow noopener">{escape(store)}</a>' if u else escape(store))


def _sell_btn(x):
    """いちばん高く買い取る店へのボタン"""
    try:
        import game_kaitori
        u = game_kaitori.store_link(x["store"], x["jan"], x["name"])
    except Exception:
        u = ""
    return (f'<a class="sellb" href="{escape(u)}" target="_blank" rel="nofollow noopener">→ {escape(x["store"])}の買取ページを見る</a>' if u else "")


def has_material(x):
    """AIの解説を作ってよいだけの材料があるか（11/14 Fable：材料の無い商品の解説が一般論になっていた）：
    楽天ブックスの商品説明・メーカー公式などの商品の事実・買取店2店以上＋定価、のどれか"""
    if x.get("caption"):
        return True
    try:
        import game_facts
        if game_facts.get(x["jan"]):
            return True
    except Exception:
        pass
    return bool(x.get("teika") and len(x.get("prices") or []) >= 2)


def _aitext(key, x=None):
    if x is not None and not has_material(x):   # 材料の無い商品の解説（前に作ったもの）は出さない
        return ""
    try:
        import game_aitext
        return game_aitext.html_for(key)
    except Exception:
        return ""


def _jsonld(d):
    import json as _j
    return '<script type="application/ld+json">' + _j.dumps(d, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def tword(x, short=False):
    """「定価」と書いてよいか（11/14 Fable の監査：定価が分からず楽天ブックスの販売価格を使っている商品まで「定価」と書いていた）"""
    if x.get("teika_note") == "楽天ブックスの販売価格" or x.get("tn") == "楽天ブックスの販売価格":
        return "販売価格" if short else "楽天ブックスの販売価格"
    return "定価"


def _related(x, allx, cid, k=8):
    """同じカテゴリのほかの商品（11/14 Fable：全ページが同じ先頭8件で、381ページはリンクが1本以下・113ページは0本だった）。
    名前の共通の語が多い順 → 買取価格が近い順。同点はJANで開始位置をずらして、リンクがいろいろな商品に回るように"""
    import hashlib
    if not cid:
        return []
    def toks(n):
        return {w for w in re.split(r"[\s　/／()（）\[\]【】・,、\-]+", (n or "").lower()) if len(w) >= 2}
    me = toks(x["name"])
    cand = [y for y in allx if y["jan"] != x["jan"] and cat_of([y["name"]] + y.get("names", [])) == cid]
    if not cand:
        return []
    off = int(hashlib.md5(x["jan"].encode()).hexdigest(), 16) % len(cand)
    cand = cand[off:] + cand[:off]
    cand.sort(key=lambda y: (-len(me & toks(y["name"])), abs((y["max"] or 0) - (x["max"] or 0)) // 2000))
    return cand[:k]


def seo_parts(x, allx, site, cats_by, md):
    """商品ページを検索で見つけてもらうための追加の情報：まとめの文・買取店すべての価格・店での呼び方・よくある質問・同じカテゴリの商品・構造化データ
    → (まとめの文, 追加の節, 構造化データ)"""
    name, jan = x["name"], x["jan"]
    cid = cat_of([name] + x.get("names", []))
    cat = (cats_by.get(cid) or {}).get("short", "") if cid else ""
    prices = x.get("prices") or []
    n = len(prices)
    avg = round(sum(p for _, p in prices) / n) if n else 0
    lo = min((p for _, p in prices), default=0)
    teika = x.get("teika") or 0
    diff = x["max"] - teika if teika else 0
    _rb = x.get("teika_note") == "楽天ブックスの販売価格"
    tw = "楽天ブックスの販売価格" if _rb else "定価"   # 定価が分からないときは「定価」と書かない（11/14）
    tkn = ("・" + x["teika_note"]) if x.get("teika_note") and not _rb else ""
    # まとめの文（検索結果の説明にもなる、商品のことが一目で分かる文）
    s1 = (f"{name}（JANコード {jan}）は" + (f"{x['maker']}の" if x.get("maker") else "") + f"{cat}の商品です。") if (cat or x.get("maker")) else \
        f"{name}のJANコードは {jan} です。"   # メーカーもカテゴリも分からないとき「〜は商品です。」と出ていた（11/11）
    if x.get("sales_date"):
        s1 += f"発売日は{x['sales_date']}"
        s1 += f"、{tw}は{teika:,}円（税込{tkn}）です。" if teika else "です。"
    elif teika:
        s1 += f"{tw}は{teika:,}円（税込{tkn}）です。"
    s2 = f"{md}時点の新品の最高買取価格は{x['store']}の{x['max']:,}円"
    if teika:
        s2 += f"で、{tw}より{abs(diff):,}円{'高く' if diff >= 0 else '安く'}売れる（{tw}比 {'+' if diff >= 0 else ''}{round((x['ratio'] - 1) * 100)}%）状態です。"
    else:
        s2 += "です。"
    if n >= 2:
        s2 += f"買取店{n}店の平均は{avg:,}円、いちばん安い店は{lo:,}円で、店によって{x['max'] - lo:,}円の差があります。"
    intro = f'<p class="pm-intro">{escape(s1 + s2)}</p>'
    secs = ""
    # 買取店すべての価格（上位5店だけでなく）
    if n:
        rows = "".join(f'<tr><td>{i + 1}位 {_sl(s_, jan, name)}</td><td class="n">{p_:,}円</td>'
                       f'<td class="n">{(("+" if p_ - teika >= 0 else "") + format(p_ - teika, ",") + "円") if teika else "—"}</td></tr>' for i, (s_, p_) in enumerate(prices))
        secs += (f'<h2>{escape(name)}の買取価格 店舗比較（新品・{n}店）</h2><table class="pm-t"><tr><th>買取店</th><th>買取価格</th><th>{tw}との差</th></tr>{rows}</table>'
                 + (f'<p class="note">平均 {avg:,}円・最高 {x["max"]:,}円・最安 {lo:,}円（{md}時点）。{CHANGE_NOTE}</p>' if n >= 2 else f'<p class="note">{CHANGE_NOTE}</p>'))
    # 買取店での呼び方（別の名前・型番で探す人のため）
    alias = []
    for a in x.get("names", []):
        a = re.sub(r"\s+", " ", a).strip()
        if a and a != name and a not in alias and len(alias) < 8:
            alias.append(a)
    if alias:
        secs += "<h2>この商品の別の呼び方・表記</h2><ul>" + "".join(f"<li>{escape(a)}</li>" for a in alias) + "</ul>"
    # よくある質問（データから作る。構造化データにも入れる）
    faq = []
    faq.append((f"{name}の定価はいくら？", f"{tw}は{teika:,}円（税込{tkn}）です。" if teika else "定価は確認中です（楽天ブックス等で分かりしだい載せます）。"))
    faq.append((f"{name}の買取価格（相場）は？", f"{md}時点の新品の最高買取価格は{x['store']}の{x['max']:,}円です。" + (f"買取店{n}店の平均は{avg:,}円です。" if n >= 2 else "") + CHANGE_NOTE))
    if teika and not _rb:
        faq.append((f"{name}は定価以上で売れる？（プレ値？）",
                    f"はい、{md}時点で定価より{diff:,}円高い{x['max']:,}円で買い取られています。" if diff > 0 else
                    f"{md}時点では定価を下回る{x['max']:,}円の買取です（定価との差 {diff:,}円）。"))
    elif teika:
        faq.append((f"{name}は楽天ブックスの販売価格より高く売れる？",
                    f"{md}時点の最高買取{x['max']:,}円は、楽天ブックスの販売価格{teika:,}円より{abs(diff):,}円{'高い' if diff >= 0 else '低い'}です（定価は確認中です）。"))
    faq.append((f"{name}はどこで買える？在庫・再販は？",
                "楽天ブックス・Amazonで販売していないかを定期的にチェックしています。販売が始まったら X（@a9994aaa）ですぐ通知します。このページの「買えるところ」からも確認できます。"))
    faq.append((f"{name}のJANコードは？", f"JANコードは {jan} です。"))
    secs += "<h2>よくある質問</h2>" + "".join(f'<details class="faq"><summary>{escape(q)}</summary><p>{escape(a)}</p></details>' for q, a in faq)
    # 同じカテゴリの商品（中のリンクで関連の商品を見てもらう）
    same = _related(x, allx, cid)
    if same:
        secs += f"<h2>{escape(cat)}のほかの商品の買取相場</h2><ul>" + "".join(
            f'<li><a href="/premium/{y["jan"]}/">{escape(y["name"])}</a>（最高買取 {y["max"]:,}円' + (f'・{tword(y)} {y["teika"]:,}円' if y.get("teika") else "") + "）</li>" for y in same) + "</ul>"
    # 構造化データ（Google向け：商品・よくある質問・パンくず）
    # 「商品（Product）」の構造化データは入れない。Google は販売価格（offers）か
    # レビュー・評価が無い Product を「無効」として扱う（Search Console で20件エラー）。
    # このサイトは販売店ではなく、買取価格は販売価格ではないので、offers を作ると嘘になる。
    ld = _jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    ld += _jsonld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "ホーム", "item": f"{site}/"},
        ({"@type": "ListItem", "position": 2, "name": cat, "item": f"{site}/{(cats_by.get(cid) or {}).get('slug', '')}/"} if cid and (cats_by.get(cid) or {}).get("slug")
         else {"@type": "ListItem", "position": 2, "name": "ゲーム・ホビー買取相場一覧", "item": f"{site}/souba/"}),
        {"@type": "ListItem", "position": 3, "name": name, "item": f"{site}/premium/{jan}/"}]})
    return intro, secs, ld


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
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">出品中を見る</a>'
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=sold_out&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">売れた価格を見る</a></div>')


FOLLOW = ('<div class="follow"><p><b>🔔 定価販売を定期的にチェック中<br>販売されたらXで即通知！</b></p>'
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
    note = ('<p class="note">買取価格は各買取店が公開している新品（未開封）の買取価格を毎日読み取ったものです（店の条件で変わることがあります）。' + CHANGE_NOTE +
            '定価はメーカー公式の希望小売価格、分からなければ楽天ブックスの定価（定価が無い商品は楽天ブックスの販売価格で、そう書いています）です。転売を勧めるものではありません。リンクの一部は広告（PR）です。</p>')

    def page(title, desc, body, path, img="", noindex=False):
        """1ページ書く。img＝Xなどで共有したときのカードの画像（無ければサイトの共通画像）。noindex＝検索に出さない（情報が少ないページ）"""
        og = img or f"{site}/og.png"
        html = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{escape(title)}</title><meta name="description" content="{escape(desc)}"><link rel="canonical" href="{site}/{path}">'
                + ('<meta name="robots" content="noindex,follow">' if noindex else '<meta name="robots" content="index,follow,max-image-preview:large">')
                + f'<meta property="og:type" content="website"><meta property="og:site_name" content="{escape(brand["name"])}"><meta property="og:locale" content="ja_JP">'
                f'<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(desc)}"><meta property="og:url" content="{site}/{path}">'
                f'<meta property="og:image" content="{escape(og)}"><meta name="twitter:card" content="{"summary" if img else "summary_large_image"}">'
                f'<meta name="twitter:site" content="@a9994aaa"><meta name="twitter:image" content="{escape(og)}">'
                f'<link rel="icon" href="/favicon.svg" type="image/svg+xml"><style></style></head><body><style>{CSS}</style>{body}</body></html>')
        d = out / path
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(simple_page(cats, html), encoding="utf-8")
        if not noindex:   # 検索に出すページだけサイトマップへ。中身（日付以外）の指紋も渡す＝本当に変わった日だけ更新日を変える
            import hashlib
            fp = hashlib.sha1(re.sub(r"\d{1,2}/\d{1,2}(?:更新|時点|\([月火水木金土日]\))", "", body).encode()).hexdigest()[:16]
            paths.append((path, fp))

    def table(xs):
        return plist_html([{"name": x["name"], "jan": x["jan"], "url": f"/premium/{x['jan']}/", "img": x.get("img", ""), "teika": x["teika"], "max": x["max"], "tn": x.get("teika_note", ""),
                            "store": x["store"], "ratio": x["ratio"], "w1h": _chg(x["max"], x["w1"]) if x.get("w1") else "",
                            "rk": rakuten_link(x["itemUrl"], aff_id) if x.get("itemUrl") else "", "az": x.get("azUrl", "")} for x in xs])

    page(f"プレミア商品一覧｜定価以上で売れるゲーム・ホビー【{md}更新】買取相場と再販・入荷速報｜{brand['name']}",
         "定価より高く買い取られているゲーム機・周辺機器・ホビーの一覧。買取店の新品の最高買取価格・定価との差・1週間前比を毎日更新。",
         f'<h1>プレミア商品一覧（定価以上で売れるゲーム・ホビー）</h1><p>買取店の新品の最高買取価格が定価を上回っている商品です（{md}更新・{len(items)}件）。'
         f'定価はメーカー公式の希望小売価格・楽天ブックスの定価で、分からない商品は楽天ブックスの販売価格と比べています（カードに「販売価格」と表示）。'
         f'楽天・Amazonで定価で売り出されたら、Xですぐお知らせします。<a href="/souba/">すべての商品の買取相場（{len(allx)}件）</a></p>'
         + (table(items) if items else "<p>いま該当する商品はありません。</p>") + note, "")
    stores_all = {st_ for x in allx for st_, _ in (x.get("prices") or [])}
    # 買取相場：値動き中心（11/10 ユーザーの指示：プレミア商品一覧と中身が被らないように）
    #  値上がり・値下がりランキング（いちばん近い過去の記録＝最大7日前との差）＋ カテゴリごとの全商品（開いて見る）
    def _base(x):
        h = x.get("hist") or {}
        d0 = (upd.date() - timedelta(days=7)).isoformat()
        ks = [k for k in sorted(h) if k < upd.date().isoformat()]
        ks7 = [k for k in ks if k >= d0]
        k = ks7[0] if ks7 else None
        return (h[k], k) if k else (None, None)
    moves = []
    for x in allx:
        b, k = _base(x)
        if b and x["max"] != b:
            moves.append((x["max"] - b, (x["max"] - b) / b, k, x))
    ups = sorted([m for m in moves if m[0] > 0], key=lambda m: -m[1])[:20]
    downs = sorted([m for m in moves if m[0] < 0], key=lambda m: m[1])[:20]

    def mv_table(ms):
        rows = "".join(f'<tr><td><a href="/premium/{x["jan"]}/">{escape(x["name"])}</a></td><td class="n">{x["max"]:,}円</td>'
                       f'<td class="n" style="color:{"#3ddc84" if d > 0 else "#ff6b6b"}">{"+" if d > 0 else ""}{d:,}円（{"+" if d > 0 else ""}{round(r * 100)}%）</td>'
                       f'<td class="n">{int(k[5:7])}/{int(k[8:10])}比</td></tr>' for d, r, k, x in ms)
        return f'<table class="pm-t"><tr><th>商品</th><th>最高買取</th><th>変化</th><th>くらべた日</th></tr>{rows}</table>'
    since = min((m[2] for m in moves), default=None)
    mv_html = ("<h2>📈 値上がりした商品</h2>" + (mv_table(ups) if ups else "<p>値上がりした商品はありません。</p>")
               + "<h2>📉 値下がりした商品</h2>" + (mv_table(downs) if downs else "<p>値下がりした商品はありません。</p>")) if moves else \
        "<p>値動きのランキングは、買取価格の記録が2日分以上たまると出ます（毎日自動で記録しています）。</p>"
    import gamecats as _gc2
    _cn = _gc2.by_id(False)
    groups_ = {}
    for x in allx:
        groups_.setdefault(cat_of([x["name"]] + x.get("names", [])) or "_other", []).append(x)
    cat_html = "<h2>カテゴリごとの全商品</h2>" + "".join(
        f'<details class="faq"><summary>{escape((_cn.get(c) or {}).get("short") or "その他")}（{len(xs)}件）</summary>{table(sorted(xs, key=lambda x: -x["max"]))}</details>'
        for c, xs in sorted(groups_.items(), key=lambda kv: (kv[0] == "_other", -len(kv[1]))))
    page(f"ゲーム・ホビー買取相場【{md}更新】値上がり・値下がりランキングと{len(allx)}商品の最高買取価格｜{brand['name']}",
         f"ゲーム機・周辺機器・たまごっち・ホビーの買取相場の値動き。値上がり・値下がりした商品のランキングと、{len(allx)}商品の新品の最高買取価格（買取店{len(stores_all)}店）をカテゴリごとに毎日更新。",
         f'<h1>ゲーム・ホビー買取相場（値動き）</h1><p>買取店{len(stores_all)}店の新品の買取価格から、商品ごとのいちばん高い価格を毎日記録して、値動きをまとめています（{md}更新）。'
         f'定価より高く売れる商品は<a href="/">プレミア商品一覧</a>にまとめています。</p>' + mv_html + cat_html + note, "souba/")
    import gamecats as _gc
    _cats = _gc.by_id(False)
    _wm_all = load_json("watch_map.json", {}) or {}
    # 買取店の一覧から一時的に消えた商品も、60日はページを残す（すぐ404にすると Search Console で「見つかりません」になるため・11/9）
    snap = load_json("premium_snap.json", {}) or {}
    today_s = upd.date().isoformat()
    for x in allx:
        snap[x["jan"]] = dict({k: v for k, v in x.items() if k != "caption"}, caption=(x.get("caption") or "")[:600], seen=today_s)
    cut = (upd.date() - timedelta(days=60)).isoformat()
    cur_j = {x["jan"] for x in allx}
    revived = [dict(v, stale=v["seen"], prices=[tuple(p) for p in v.get("prices") or []]) for j, v in snap.items()
               if j not in cur_j and v.get("seen", "") >= cut and not NOT_HOBBY.search(" ".join([v.get("name", "")] + list(v.get("names") or [])))]
    for j in [j for j, v in snap.items() if v.get("seen", "") < cut]:
        snap.pop(j, None)
    save_json("premium_snap.json", snap)
    for x in allx + revived:
        q = quote(re.sub(r"\s+", " ", x["name"])[:40])
        intro, extra, ld = seo_parts(x, allx, site, _cats, md)
        try:   # メーカー公式などから取った商品の事実（出典つき。game_facts）
            import game_facts
            extra = game_facts.html_for(x["jan"], x["name"]) + extra
        except Exception:
            pass
        _ntc = (_cats.get(cat_of([x["name"]] + x.get("names", []))) or {}).get("notice")
        if _ntc:   # お酒の「20歳になってから」など、カテゴリの注意書き（11/11）
            intro = _notice_p(_ntc) + intro
        if x.get("stale"):
            sd = x["stale"]
            intro = (f'<p class="note">⚠ この商品は いま買取店の一覧に載っていません。下の買取価格は{int(sd[5:7])}/{int(sd[8:10])}時点のものです。</p>') + intro
        cur_h, hist_h = stock_html(x["jan"], _wm_all, x["name"])
        rel = [r for r in live_rows if ol.same_item_score(r.get("product") or "", x["name"]) >= 0.6][:6]
        rel_html = ("<h2>この商品の抽選・予約・再販</h2><ul>" + "".join(
            f'<li><a href="/{escape(r["lpath"])}">{escape(r.get("store") or "")} {escape(r.get("product") or "")}</a></li>' for r in rel) + "</ul>") if rel else \
            "<h2>この商品の抽選・予約・再販</h2><p>いま受付中のものはありません。楽天・Amazonで販売が始まったらXでお知らせします。</p>"
        import game_affi as _gaf
        from urllib.parse import quote as _qt
        _sq = _qt(re.sub(r"\s+", " ", x["name"])[:60])
        # 楽天・Amazonの商品ページが分からないときは「探す」（検索）のリンク（11/14 Fable：ボタンが無い商品ページが187あった。
        # 別の商品が出ることもあるので「探す」と書き、上の「販売中」のボタンには使わない）
        shops = (f'<a class="btn btn-rk" href="{escape(rakuten_link(x["itemUrl"], aff_id))}" target="_blank" rel="nofollow sponsored noopener">楽天で見る</a>' if x["itemUrl"] else
                 f'<a class="btn btn-rk" href="{escape(rakuten_link("https://search.rakuten.co.jp/search/mall/" + _sq + "/", aff_id))}" target="_blank" rel="nofollow sponsored noopener">楽天で探す</a>') + \
            (f'<a class="btn btn-az" href="{escape(x["azUrl"])}" target="_blank" rel="nofollow sponsored noopener">Amazonで見る</a>' if x.get("azUrl") else
             f'<a class="btn btn-az" href="https://www.amazon.co.jp/s?k={_sq}&amp;tag={escape(_gaf.amazon_tag(settings or {}))}" target="_blank" rel="nofollow sponsored noopener">Amazonで探す</a>') + \
            f'<a class="btn btn-yh" href="https://shopping.yahoo.co.jp/search?p={q}" target="_blank" rel="nofollow noopener">Yahoo!で見る</a>' + \
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">メルカリで探す</a>'
        top = "".join(f'<tr><td>{escape(s_)}</td><td class="n">{p_:,}円</td></tr>' for s_, p_ in x["prices"][:5])
        img = f'<img src="{escape(x["img"])}" alt="{escape(x["name"])}" width="120" height="120" loading="lazy">' if x["img"] else ""
        _rb = x.get("teika_note") == "楽天ブックスの販売価格"   # 定価が分からず、楽天ブックスの販売価格を使っているとき（11/14）
        tk = ((f'楽天ブックスの販売価格 {x["teika"]:,}円' if _rb else f'定価 {x["teika"]:,}円' + (f'<small>（{escape(x["teika_note"])}）</small>' if x.get("teika_note") else ""))
              + f'（{_ratio_html(x)}）') if x["teika"] else "定価：確認中"
        # JANコードで検索する人が多い（Search Console 11/11）ので、説明の頭と題名の最後に JAN を入れる。
        # 「買取」で検索する人のため、題名に最高買取価格も入れる。
        desc = f"JAN {x['jan']}｜{x['name']}の新品の最高買取価格は{x['max']:,}円（{x['store']}）" + (f"、{tword(x)}{x['teika']:,}円の{round(x['ratio'] * 100)}%" if x["teika"] else "") + "。買取店ごとの価格・1週間前比・抽選や再販の情報。"
        _cid = cat_of([x["name"]] + x.get("names", []))
        _cc = _cats.get(_cid) or {}
        _crumb = (f'<a href="/{escape(_cc["slug"])}/">{escape(_cc.get("short", ""))}</a> ／ ' if _cc.get("slug") else "")
        # 題名：定価が分からない商品は「定価・」を外す。見出しは「〜の買取価格・販売状況」（11/14 Fable）
        _when = (f"{int(x['stale'][5:7])}/{int(x['stale'][8:10])}時点" if x.get("stale") else f"{md}更新")   # 買取店から消えた商品は、最後に確かめた日（11/14 Fable）
        page(f"{x['name']} 買取価格 最高{x['max']:,}円【{_when}】{'定価・' if x['teika'] and not _rb else ''}再販情報｜JAN {x['jan']}", desc,
             f'{ld}<p>{_crumb}<a href="/souba/">ゲーム・ホビー買取相場一覧</a> ／ <a href="/">プレミア商品一覧</a></p><h1>{escape(x["name"])}の買取価格・販売状況</h1>{buy_box(x.get("azUrl") or "", rakuten_link(x["itemUrl"], aff_id) if x.get("itemUrl") else "", x["name"])}{intro}'
             f'<div class="pm-row">{img}<div><div>最高買取（新品）</div><div class="pm-big">{x["max"]:,}円</div><div>{_sl(x["store"], x["jan"], x["name"])}・{tk}</div><div class="note" style="font-size:12px">※{md}時点の金額です。{CHANGE_NOTE}</div>{_sell_btn(x)}</div></div>'
             f'<table class="pm-t"><tr><th>1週間前比</th><td class="n">{_chg(x["max"], x["w1"])}</td></tr><tr><th>1か月前比</th><td class="n">{_chg(x["max"], x["m1"])}</td></tr></table>{mercari_box(x["name"])}'
             f'{cur_h}{FOLLOW}<h2>{"定価で買えるところ" if x["teika"] and not _rb else "買えるところ"}<small class="hot">（販売してたら激熱🔥）</small></h2><div class="shopb">{shops}</div>{hist_h}'
             f'<h2>商品情報</h2><table class="pm-t">{info_rows(x)}</table>{features_html(x)}{_aitext(x["jan"], x)}'
             f'<h2>最高買取価格の推移</h2>{chart_svg(x["hist"], x["teika"], tword(x))}{rel_html}'
             f'{extra}{note}', f"premium/{x['jan']}/", img=x.get("img") or "",
             # どのジャンルにも入らず、定価も無く、買取店1店だけで、商品の事実も無いページは検索に出さない（11/14 Fable：
             # サイトのテーマと関係ない家電などが混ざっていて、中身も薄い）。ページは残す
             noindex=bool(x.get("stale") or (not _cid and not x["teika"] and len(x.get("prices") or []) <= 1 and not has_material(x))))
    # サイトに載っている抽選・予約・発売日の商品で、買取相場の一覧に無いもの → 商品ページを作る（発売前は相場「予測不能」）
    import hashlib
    from dedupe import norm_product
    import gamecats
    cats_by = gamecats.by_id(False)
    groups_ = {}
    for r in live_rows:
        nm = (r.get("product") or "").strip()
        if not nm or any(ol.same_item_score(nm, x["name"]) >= 0.75 for x in allx):
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
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">メルカリで探す</a>'
        img = f'<img src="{escape(rk["img"])}" alt="{escape(nm)}" width="120" height="120" loading="lazy">' if rk.get("img") else ""
        cat = (cats_by.get(r0.get("game")) or {}).get("short", "")
        info = [("商品名", nm), ("カテゴリ", cat), ("発売日", f"{rd.year}年{rd.month}月{rd.day}日" if rd else ""), ("定価（税込）", price),
                ("JANコード", r0.get("jan") or "")]
        info_h = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in info if v)
        thin = sum(bool(v) for v in (price, r0.get("jan"), rk.get("img"), rd)) < 3   # 定価・JAN・写真・発売日のうち3つ以上そろうまでは検索に出さない
        page(f"{nm} 抽選・予約・再販と相場・定価【{md}更新】｜{brand['name']}",
             f"{nm}の抽選・予約・再販の受付状況、定価、相場（{souba}）、楽天・Amazonの販売ページ。販売開始はXで通知。",
             f'<p><a href="/souba/">ゲーム・ホビー買取相場一覧</a></p><h1>{escape(nm)}</h1>' + _notice_p((cats_by.get(r0.get("game")) or {}).get("notice")) + f'{buy_box(r0.get("az") or "", rk.get("u") or "", nm)}'
             f'<div class="pm-row">{img}<div><div>市場相場</div><div class="pm-big" style="font-size:20px">{escape(souba)}</div>'
             f'<div>{("定価 " + escape(str(price))) if price else ""}</div></div></div>{_av(next((r.get("avail") for r in rs if r.get("avail")), None))}{mercari_box(nm)}'
             f'{FOLLOW}<h2>定価で買えるところ<small class="hot">（販売してたら激熱🔥）</small></h2><div class="shopb">{shops}</div>{rel_html}<h2>商品情報</h2><table class="pm-t">{info_h}</table>{note}', f"item/{slug}/", img=rk.get("img") or "", noindex=thin)
        made += 1
    # 発売予定のゲーム（楽天ブックス）：/new/<JAN>/ と /new/（11/9）
    up_made = []
    try:
        import game_upcoming
        up_made = game_upcoming.write_pages(out, cats, site, brand, settings, page, aff_id, {x["jan"] for x in allx})
    except Exception as e:
        log(f"発売予定の商品ページ: スキップ {e}")
    # 商品名・JANコードで検索：/search.json（商品ページ・抽選の一覧）と /search/
    import json as _json
    idx = [[x["name"], x["jan"], f"/premium/{x['jan']}/", x["teika"] or 0, x["max"]] for x in allx]
    idx += [[re.sub(r"\s+", " ", rs_[0].get("product") or "")[:70], rs_[0].get("jan") or "", f"/item/{item_slug(rs_[0].get('product') or k_)}/", 0, 0]
            for k_, rs_ in groups_.items()]
    idx += [[f'{r.get("store") or ""} {r.get("product") or ""}'.strip()[:80], r.get("jan") or "", "/" + r["lpath"], 0, 0] for r in live_rows if r.get("lpath")]
    _up = (load_json("upcoming.json", {}) or {}).get("items") or {}
    idx += [[_up[j]["title"], j, f"/new/{j}/", _up[j].get("price") or 0, 0] for j in up_made if j in _up]
    (out / "search.json").write_text(_json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    page(f"商品名・JANコードで検索｜{brand['name']}", "ゲーム機・ホビーの商品を商品名やJANコードで検索。定価・買取相場・抽選や発売の情報のページに移動できます。",
         '<h1>商品名・JANコードで検索</h1><p id="qs-n" class="note"></p><div id="qs-r"></div>' + SEARCH_JS, "search/", noindex=True)
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
            if ol.same_item_score(name or "", n) >= 0.75:
                return x
    return None


def price_match(name, settings=None):
    """商品名に当たる「買取価格が分かる商品」（定価以上かどうかに関係なく）。当たらなければ None"""
    import official_link as ol
    if "cat" not in _PM_CACHE:
        try:
            _PM_CACHE["cat"] = [x for x in catalog(settings or {}, watch_map_cached()) if x.get("teika")]
        except Exception:
            _PM_CACHE["cat"] = []
    best = None
    for x in _PM_CACHE["cat"]:
        for n in [x["name"]] + x.get("names", [])[:3]:
            sc = ol.same_item_score(name or "", n)
            if sc >= 0.75 and (best is None or sc > best[0]):
                best = (sc, x)
    return best[1] if best else None


def below_teika(name, settings=None):
    """買取価格が定価の8割（x_min_buy_ratio）より低いと分かっている商品か（11/13 ユーザーの指摘：買取がマイナスの商品の速報が多い）"""
    x = price_match(name, settings)
    r = float((settings or {}).get("x_min_buy_ratio", 0.8))   # 11/13 ユーザー：「定価－20％くらいまでならいい」
    return bool(x and x.get("teika") and x["max"] < x["teika"] * r)


def worth_posting(it, settings=None):
    """Xに出す価値があるか（11/9 ユーザーの指示）：定価以上で売れる商品か、品薄の商品（抽選・招待販売になっているもの）だけ。
    11/13：抽選・招待でも、買取価格が定価より低いと分かっている商品は出さない"""
    if it.get("kind") in ("lottery", "invite", "fukubukuro"):
        return not below_teika(it.get("product") or "", settings)
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
                                        "jan": x["jan"], "url": f"/premium/{x['jan']}/", "img": x.get("img", ""), "tn": x.get("teika_note", ""),
                                        "rk": rakuten_link(x["itemUrl"], aff) if x.get("itemUrl") else "", "az": x.get("azUrl", "")})
    seen = set()
    from dedupe import norm_product
    for r in live_rows:
        nm = (r.get("product") or "").strip()
        k = norm_product(nm)
        if not nm or k in seen or r.get("game") is None:
            continue
        if any(ol.same_item_score(nm, x["name"]) >= 0.75 for x in allx):
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


PL_CSS = (".pl{display:flex;flex-direction:column;gap:12px;margin:12px 0}"
          ".pc{display:grid;grid-template-columns:84px 1fr auto;gap:14px;align-items:center;background:#141823;border:1px solid #262c3a;border-radius:14px;padding:14px}"
          ".pc-img{display:block;width:84px;height:84px;border-radius:10px;background:#fff;overflow:hidden}.pc-img img{width:100%;height:100%;object-fit:contain}"
          ".pc-img.none{background:#1d2230}"
          ".pc-name{display:block;color:#e9edf5;font-weight:900;font-size:15px;line-height:1.45;text-decoration:none;margin-bottom:8px}.pc-name:hover{color:#ffd23f}"
          ".pc-nums{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:flex-end}.pc-nums small{display:block;font-size:11px;color:#8a93a6}"
          ".pc-nums b{font-family:var(--font-num);font-size:17px}.pc-nums em{font-style:normal;font-size:11px;color:#8a93a6;margin-left:4px}"
          ".pc-r{font-weight:900;font-size:14px;padding:3px 8px;border-radius:999px;background:#0f2a1a;color:#3ddc84}.pc-r.dn{background:#2a1316;color:#ff8a95}"
          ".pc-sub{margin-top:6px;font-size:12px;color:#8a93a6}"
          ".pc-acts{display:flex;gap:8px;align-items:stretch}.pc-shops{display:flex;flex-direction:column;gap:6px;min-width:128px}"
          ".pc-acts a{display:flex;align-items:center;justify-content:center;padding:10px 12px;border-radius:8px;font-weight:900;font-size:14px;text-decoration:none;white-space:nowrap}"
          ".pc-acts .rk{background:#bf0000;color:#fff}.pc-acts .az{background:#ff9900;color:#0b0d12}.pc-acts .mc{background:#ff4f50;color:#fff}"
          ".pc-acts .det{background:#ffd23f;color:#0b0d12;min-width:108px}"
          "@media (max-width:640px){.pc{grid-template-columns:72px 1fr;gap:12px;padding:14px 12px}.pc-img{width:72px;height:72px}"
          ".pc-acts{grid-column:1/-1;flex-direction:column;gap:6px}.pc-shops{flex-direction:row;min-width:0}.pc-shops a{flex:1;padding:12px 4px;font-size:13px}"
          ".pc-acts .det{padding:12px}.pc-name{font-size:15px}}")


def plist_html(prods):
    """商品のカード一覧（写真・商品名・定価・最高買取・定価比・楽天/Amazon/詳細を見る）。スマホでは1商品ずつ大きめのカードで、ボタンは下に横並び"""
    out = []
    for p in prods:
        img = (f'<a class="pc-img" href="{escape(p["url"])}" tabindex="-1" aria-hidden="true"><img src="{escape(p["img"])}" alt="{escape(p["name"])}" loading="lazy" width="84" height="84"></a>'
               if p.get("img") else f'<a class="pc-img none" href="{escape(p["url"])}" tabindex="-1" aria-hidden="true"></a>')
        nums = [f'<div><small>{tword(p, True)}</small><b>{format(p["teika"], ",")}円</b></div>' if p.get("teika") else '<div><small>定価</small><b>—</b></div>']
        if p.get("max"):
            nums.append(f'<div><small>最高買取（新品）</small><b>{format(p["max"], ",")}円</b>{("<em>" + _sl(p["store"], p.get("jan", ""), p["name"]) + "</em>") if p.get("store") else ""}</div>')
        if p.get("ratio"):
            pc = round((p["ratio"] - 1) * 100)
            nums.append(f'<span class="pc-r{" dn" if pc < 0 else ""}">{tword(p, True)}比 {"+" if pc >= 0 else ""}{pc}%</span>')
        sub = f'<div class="pc-sub">1週間前比 {p["w1h"]}</div>' if p.get("w1h") else ""
        from urllib.parse import quote
        acts = ""   # 上から Amazon・楽天・メルカリ（メルカリはいつも出す）、右端に「詳細を見る」
        if p.get("az"):
            acts += f'<a class="az" href="{escape(p["az"])}" target="_blank" rel="nofollow sponsored noopener">Amazon</a>'
        if p.get("rk"):
            acts += f'<a class="rk" href="{escape(p["rk"])}" target="_blank" rel="nofollow sponsored noopener">楽天</a>'
        mq = quote(re.sub(r"\s+", " ", p.get("name") or "")[:40])
        acts += f'<a class="mc" href="https://jp.mercari.com/search?keyword={mq}&amp;status=on_sale&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">メルカリ</a>'
        acts = f'<div class="pc-shops">{acts}</div><a class="det" href="{escape(p["url"])}">詳細を見る</a>'
        out.append(f'<div class="pc">{img}<div class="pc-body"><a class="pc-name" href="{escape(p["url"])}">{escape(p["name"])}</a>'
                   f'<div class="pc-nums">{"".join(nums)}</div>{sub}</div><div class="pc-acts">{acts}</div></div>')
    return f'<style>{PL_CSS}</style><div class="pl">{"".join(out)}</div>'


def _shop_mini(p):
    """一覧の行の「楽天」「Amazon」の小さいボタン（その商品のページ。アフィリエイト）"""
    out = ""
    if p.get("rk"):
        out += f'<a class="pm-sh rk" href="{escape(p["rk"])}" target="_blank" rel="nofollow sponsored noopener">楽天</a>'
    if p.get("az"):
        out += f'<a class="pm-sh az" href="{escape(p["az"])}" target="_blank" rel="nofollow sponsored noopener">Amazon</a>'
    return out


def cat_products_html(prods, short):
    """カテゴリページの商品一覧（カード）"""
    if not prods:
        return f'<section class="sec"><h2>{escape(short)}の商品一覧</h2><p>商品はまだありません。</p></section>'
    return (f'<section class="sec pm-list"><h2>{escape(short)}の商品一覧（{len(prods)}件）</h2>'
            '<p class="note">最高買取は買取店の新品の買取価格でいちばん高いもの。' + CHANGE_NOTE + '定価で売り出されたらXで通知します。</p>'
            f'{plist_html(prods)}</section>')