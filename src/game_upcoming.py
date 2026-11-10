"""ゲーム・ホビー入荷速報：発売予定のゲーム（楽天ブックス）から商品ページを作る（11/9 ユーザーの指示）

・1日1回、楽天ブックスのゲームの検索（BooksGame）で、機種ごとに「発売日の新しい順」と「限定版」を取ってくる
  （1回の呼び出しは30件まで。機種×ページで十数回＝20秒くらい）
・発売日がまだ来ていない（または発売から30日以内の）商品を state/game/upcoming.json に残す
・サイトには /new/<JAN>/（商品ページ：発売日・定価・機種・メーカー・予約のリンク・商品説明・よくある質問）と /new/（一覧）
  買取店の相場ページ（/premium/<JAN>/）がある商品は作らない（そちらへつなぐ）
"""
import os
import re
import time
from datetime import timedelta
from html import escape

from common import load_json, save_json, now, parse_dt, log, job_elapsed

STATE = "upcoming.json"
HARD = ["Nintendo Switch 2", "PS5", "Nintendo Switch", "Xbox Series X", "Xbox Series X|S", "Xbox"]
# 検索に出す商品（本体・周辺機器・限定版・セットなど＝品薄・プレ値になりやすいもの）。普通のソフトはページを作るが検索には出さない（11/9 SEO監査）
def is_hot(title):
    """本体・周辺機器・限定版などか（「【楽天ブックス限定特典】」「(早期購入特典…)」などの特典の書き方は見ない）"""
    t = re.sub(r"【[^】]*】|[（(][^）)]*[）)]?", " ", title or "")
    return bool(HOT.search(t))


HOT = re.compile(r"本体|コントローラ|限定|特装|コレクターズ|同梱|エディション|Edition|EDITION|セット|amiibo|ケース|充電|microSD|周辺|BOX|ボックス|プレミアム|アクセサリ|ヘッドセット|スタンド|ドック|カメラ|ポーチ")


def _sales_date(s):
    """「2026年12月10日」「2026年12月上旬」「2026年12月」など → その月日の date（分からなければ None）"""
    from datetime import date
    m = re.search(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日|(上旬|中旬|下旬))?", s or "")
    if not m:
        return None
    d = int(m.group(3)) if m.group(3) else {"上旬": 5, "中旬": 15, "下旬": 25}.get(m.group(4) or "", 28)
    try:
        return date(int(m.group(1)), int(m.group(2)), d)
    except ValueError:
        return None


def _call(params, settings):
    import requests
    import game_premium as gp
    site = (os.environ.get("RAKUTEN_REFERER") or os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")
    p = dict(params, applicationId=os.environ.get("RAKUTEN_APP_ID", "").strip(), accessKey=os.environ.get("RAKUTEN_ACCESS_KEY", "").strip(),
             format="json", formatVersion=2, hits=30, booksGenreId="006")
    h = {"accessKey": p["accessKey"], "Referer": site + "/", "Origin": site, "User-Agent": "game-nyuka/1.0"}
    for url in ([gp._books_ok["url"]] if gp._books_ok.get("url") else gp.BOOKS_GAME):
        try:
            r = requests.get(url, params=p, headers=h, timeout=15)
        except Exception:
            continue
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(url, params=p, headers=h, timeout=15)
        if r.status_code == 200:
            gp._books_ok["url"] = url
            return [i.get("Item", i) for i in (r.json().get("Items") or [])]
    return []


def update(settings, call=None, sleep=time.sleep):
    """1日1回、発売予定のゲームを取り直す"""
    st = load_json(STATE, {})
    t = now()
    if st.get("at") and parse_dt(st["at"]) and (t - parse_dt(st["at"])).total_seconds() < 20 * 3600:
        return st
    if call is None:
        if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
            return st
        call = lambda p: _call(p, settings)  # noqa: E731
    items = dict(st.get("items") or {})
    today = t.date()
    n = 0
    per = {}
    for hw in settings.get("upcoming_hardware") or HARD:
        for params in ([{"hardware": hw, "sort": "-releaseDate", "page": pg} for pg in (1, 2, 3)] + [{"hardware": hw, "sort": "-releaseDate", "limitedFlag": 1}]):
            if job_elapsed() > float(settings.get("kaitori_until_sec", 230)) + 30:
                break
            try:
                rows = call(params)
            except Exception as e:
                log(f"発売予定：{hw} 失敗 {e}")
                rows = []
            n += 1
            per[hw] = per.get(hw, 0) + len(rows)
            for i in rows:
                jan = str(i.get("jan") or "")
                d = _sales_date(i.get("salesDate"))
                if not (jan.isdigit() and len(jan) == 13 and d and d >= today - timedelta(days=30)):
                    continue
                items[jan] = {"title": i.get("title") or "", "hardware": i.get("hardware") or hw, "maker": i.get("label") or "",
                              "sales_date": i.get("salesDate") or "", "date": d.isoformat(), "price": int(i.get("listPrice") or i.get("itemPrice") or 0),
                              "url": (i.get("itemUrl") or "").split("?")[0], "img": re.sub(r"\?_ex=\d+x\d+$", "", i.get("largeImageUrl") or ""),
                              "caption": (i.get("itemCaption") or "")[:1500], "limited": bool(str(i.get("limitedFlag") or "0") == "1" or is_hot(i.get("title"))),
                              "avail": str(i.get("availability") or "")}
            sleep(1.1)
    # 発売から30日すぎたものは消す
    items = {k: v for k, v in items.items() if v.get("date", "") >= (today - timedelta(days=30)).isoformat()}
    st = {"at": t.isoformat(), "items": items}
    save_json(STATE, st)
    log(f"発売予定：楽天ブックスを{n}回見て {len(items)}件（機種ごとの返事 {per}）")
    return st


AVAIL = {"1": "在庫あり", "2": "通常3〜7日程度で発送", "3": "通常3〜9日程度で発送", "4": "メーカー取り寄せ", "5": "予約受付中", "6": "メーカーに在庫確認"}


def write_pages(out, cats, site, brand, settings, page, aff_id, have_jans):
    """/new/<JAN>/ と /new/ を書く。page(title, desc, body, path) は game_premium.write_pages の中の関数と同じもの"""
    from urllib.parse import quote
    import game_premium as gp
    from game_affi import rakuten_link
    items = (load_json(STATE, {}) or {}).get("items") or {}
    upd = now()
    md = f"{upd.month}/{upd.day}"
    tag = (settings.get("amazon_tag") or "gamenyuka-22")
    rows = sorted(items.items(), key=lambda kv: (kv[1].get("date", ""), kv[1].get("title", "")))
    made = []
    for jan, x in rows:
        if jan in have_jans:
            continue
        nm = re.sub(r"\s+", " ", x["title"]).strip()
        if not nm:
            continue
        q = quote(nm[:40])
        rk = rakuten_link(x["url"], aff_id) if x.get("url") else ""
        az = f"https://www.amazon.co.jp/s?k={jan}&tag={tag}"
        before = x.get("date", "") > upd.date().isoformat()
        st_ = AVAIL.get(x.get("avail"), "")
        shops = (f'<a class="btn btn-rk" href="{escape(rk)}" target="_blank" rel="nofollow sponsored noopener">楽天で{"予約" if before else "見る"}</a>' if rk else "") + \
            f'<a class="btn btn-az" href="{escape(az)}" target="_blank" rel="nofollow sponsored noopener">Amazonで{"予約" if before else "見る"}</a>' + \
            f'<a class="btn btn-yh" href="https://shopping.yahoo.co.jp/search?p={jan}" target="_blank" rel="nofollow noopener">Yahoo!で見る</a>' + \
            f'<a class="btn btn-mc" href="https://jp.mercari.com/search?keyword={q}&amp;status=on_sale&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">メルカリで探す</a>'
        img = f'<img src="{escape(x["img"])}" alt="{escape(nm)}" width="120" height="120" loading="lazy">' if x.get("img") else ""
        price = f'{x["price"]:,}円' if x.get("price") else "確認中"
        hot = is_hot(nm)
        kind = "限定版・セット・周辺機器" if hot else ""
        intro = (f"{nm}は{x.get('maker') or 'メーカー'}から{x.get('sales_date') or '近日'}に発売{'予定' if before else 'された'}の"
                 f"{x.get('hardware') or 'ゲーム'}向けの商品です（JANコード {jan}）。定価（楽天ブックスの販売価格）は{price}"
                 + (f"、楽天ブックスでは「{st_}」です。" if st_ else "です。")
                 + ("限定版・セット商品は発売前後に品切れになりやすいので、予約は早めがおすすめです。" if kind else ""))
        info = [("商品名", nm), ("機種", x.get("hardware")), ("メーカー", x.get("maker")), ("発売日", x.get("sales_date")), ("定価（税込）", price),
                ("楽天ブックスの状況", st_), ("種類", kind), ("JANコード", jan)]
        info_h = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in info if v)
        feat = gp.features_html({"caption": x.get("caption")})
        faq = [(f"{nm}の発売日はいつ？", f"{x.get('sales_date') or '未定'}です（楽天ブックスの情報）。"),
               (f"{nm}の定価（値段）は？", f"{price}（税込）です。"),
               (f"{nm}はどこで予約できる？", "楽天ブックス・Amazonなどで予約できます。このページの「定価で買えるところ」から確認できます。品切れのときは、再販・販売開始を X（@a9994aaa）でお知らせします。"),
               (f"{nm}のJANコードは？", f"JANコードは {jan} です。")]
        faq_h = "<h2>よくある質問</h2>" + "".join(f'<details class="faq"><summary>{escape(a)}</summary><p>{escape(b)}</p></details>' for a, b in faq)
        same = [(j, y) for j, y in rows if j != jan and j not in have_jans and y.get("hardware") == x.get("hardware")][:8]
        same_h = (f"<h2>{escape(x.get('hardware') or '')}のほかの発売予定</h2><ul>" + "".join(
            f'<li><a href="/new/{j}/">{escape(y["title"])}</a>（{escape(y.get("sales_date") or "")}）</li>' for j, y in same) + "</ul>") if same else ""
        prod = {"@context": "https://schema.org", "@type": "Product", "name": nm, "gtin13": jan, "description": intro, "url": f"{site}/new/{jan}/"}
        if x.get("img"):
            prod["image"] = x["img"]
        if x.get("maker"):
            prod["brand"] = {"@type": "Brand", "name": x["maker"]}
        ld = gp._jsonld(prod) + gp._jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": a, "acceptedAnswer": {"@type": "Answer", "text": b}} for a, b in faq]})
        page(f"{nm} 予約・在庫・発売日・定価【{md}更新】｜{brand['name']}",
             f"{nm}（{x.get('hardware') or ''}）の発売日{x.get('sales_date') or ''}・定価{price}・予約できるお店（楽天・Amazon）・在庫と再販の情報。販売開始はXで通知。",
             f'{ld}<p><a href="/new/">発売予定のゲーム一覧</a> ／ <a href="/souba/">買取相場一覧</a></p><h1>{escape(nm)}</h1>{gp.buy_box(az, rk, nm)}<p class="pm-intro">{escape(intro)}</p>'
             f'<div class="pm-row">{img}<div><div>発売日</div><div class="pm-big" style="font-size:22px">{escape(x.get("sales_date") or "未定")}</div>'
             f'<div>定価 {escape(price)}{("・" + escape(st_)) if st_ else ""}</div><div>買取相場：{"予測不能（発売前）" if before else "買取価格の情報はまだありません"}</div></div></div>'
             f'{gp.mercari_box(nm)}{gp.FOLLOW}<h2>定価で買えるところ<small class="hot">（販売してたら激熱🔥）</small></h2><div class="shopb">{shops}</div>'
             f'<h2>商品情報</h2><table class="pm-t">{info_h}</table>{feat}{gp._aitext("new:" + jan)}{faq_h}{same_h}'
             '<p class="note">発売日・定価は楽天ブックスの商品情報です（変わることがあります）。リンクの一部は広告（PR）です。</p>', f"new/{jan}/",
             img=x.get("img") or "", noindex=not hot)
        made.append(jan)
    # 一覧：機種ごと・発売日の順
    blocks = ""
    for hw in settings.get("upcoming_hardware") or HARD:
        xs = [(j, y) for j, y in rows if y.get("hardware", "").startswith(hw) and j in made]
        if not xs:
            continue
        blocks += f"<h2>{escape(hw)}（{len(xs)}件）</h2>" + gp.plist_html([{
            "name": y["title"], "url": f"/new/{j}/", "img": y.get("img", ""), "teika": y.get("price") or 0, "max": 0, "store": "",
            "ratio": 0, "w1h": "", "rk": rakuten_link(y["url"], aff_id) if y.get("url") else "",
            "az": f"https://www.amazon.co.jp/s?k={j}&tag={tag}"} for j, y in xs])
    page(f"発売予定のゲーム・限定版一覧【{md}更新】予約・発売日・定価｜{brand['name']}",
         "Nintendo Switch 2・PS5・Switch・Xboxの発売予定のゲーム・限定版・周辺機器の一覧。発売日・定価・予約できるお店を毎日更新。",
         f'<h1>発売予定のゲーム・限定版</h1><p>楽天ブックスの情報から、これから発売されるゲーム・限定版・周辺機器をまとめています（{md}更新・{len(made)}件）。'
         '品切れの商品の販売開始・再販はXでお知らせします。</p>' + (blocks or "<p>いま載せられる商品はありません。</p>"), "new/")
    log(f"発売予定の商品ページ：{len(made)}件")
    return made
