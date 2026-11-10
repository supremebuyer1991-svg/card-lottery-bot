"""ゲーム・ホビー入荷速報（SITE=game）：カードの商品写真と「楽天で見る」「Amazonで見る」のリンク

・楽天：その商品そのものの楽天ブックスの商品ページ（売り切れでも「入荷お知らせ」を登録できる）。検索結果のページにはリンクしない
  楽天市場の商品検索API（トレカと同じ rakuten.ENDPOINT・同じ鍵）を shopCode=book（楽天ブックス）にしぼって、売り切れも含めて探す。
  商品名の大事な語（型番・モデル名）が全部入っている物だけを使う（周辺機器・中古・ソフトなどは使わない）
・結果は state/game/rakuten.json に1商品ずつ保存（見つからなかったものも保存）。同じ商品は24時間に1回まで・1回の実行で15回まで
・手で決める：config/game/manual.yaml の1件ごと、または config/game/models.yaml の series_shop（機種・モデルごと）に
  rakuten_url（楽天の商品ページのURL）・amazon_asin（AmazonのASIN）・jan（JANコード）を書く。手で書いたものが優先
・Amazon：ASIN を書いたものだけ（自動では探さない）。https://www.amazon.co.jp/dp/<ASIN>?tag=<タグ>
・値段は出さない（転売の値段を出さないため。楽天の値段も出さない）
・鍵（RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY）が無いとき（テスト・手元）は何もしない
"""
import os
import re
import time
import unicodedata
from urllib.parse import urlparse

from common import ROOT, load_json, save_json, now, parse_dt, log

CACHE = "rakuten.json"   # state/game/rakuten.json（SITE=game のとき STATE_DIR は state/game）
# 商品が無い（店頭のくじ・福袋の箱など）カテゴリは探さない
SKIP_GAMES = ("ichibankuji", "fukubukuro")
# 探すときに商品名から外す語（受付の言葉）
DROP = re.compile(r"抽選販売|抽選受付|抽選|予約受付|予約|再販売|再販|再入荷|入荷|販売|受付|第\s*\d+\s*回|先着|発売|"
                  r"招待リクエスト|招待制|招待|応募|本体のみ|新品|【[^】]*】|\[[^\]]*\]")
# 商品名に無くてもよい語（あれば少しよい）
QUIET = {"本体", "日本語専用", "国内専用", "日本語", "通常版", "単品", "パッケージ版"}   # 検索の語にも入れない
SOFT = QUIET | {"nintendo", "bandai", "spirits", "sony"}
# 写真・リンクに使わない物（周辺機器・中古・ソフトなど）
NG = re.compile(r"中古|訳あり|ジャンク|互換|対応|向け|保護|フィルム|ケース|カバー|スタンド|充電|ケーブル|アダプタ|ポーチ|スキン|シール|ステッカー|"
                r"グリップ|収納|バッグ|攻略|ガイドブック|設定資料|ムック|雑誌|カレンダー|DLC|ダウンロード版|オンラインコード|"
                r"(?<![語内])専用|[^\s　専]用(?=$|[\s　】\]）)])|ブルーレイ|Blu-?ray|DVD|CD", re.I)
# 商品名にあって、探している物に無ければ別の商品（PS5 と PS5 Pro、本体とセット など）
VARIANT = ("pro", "slim", "lite", "oled", "有機el", "デジタル", "digital", "ディスクドライブ", "コントローラー", "dualsense",
           "セット", "同梱", "ソフト", "カセット", "限定版", "特典", "パック")


def _n(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"playstation|プレイステーション|プレステ", "ps", s)   # 「PS5」と「PlayStation 5」を同じに
    return re.sub(r"[\s「」『』()（）・×【】\[\]/／&＆+＋\-－‐―〜~:：,，、。!！?？'\"]", "", s)


def keyword(name):
    """楽天で探すときの語（受付の言葉・「本体」などを外したもの）"""
    # 楽天は「半角1文字だけの語」（Switch 2 の「2」など）があると keyword is not valid で断る。
    # その語は検索語から外す（商品が合っているかの確認 match() では、元の名前の語のまま確かめる）
    words = [t for t in _split(name) if _n(t) not in QUIET and not re.fullmatch(r"[\x21-\x7e]", t)]
    return " ".join(words)


def _split(name):
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"[（(][^）)]*[）)]", " ", s)
    s = DROP.sub(" ", s)
    return [t for t in re.split(r"[\s　・,，、]+", s) if _n(t)]


def tokens(name):
    """探す語（大事な語＝必須、ほかは SOFT）。カッコの中は必須にしない"""
    req, soft = [], []
    for t in _split(name):
        (soft if _n(t) in SOFT else req).append(t)
    return req, soft


def match(item, name):
    """楽天の商品が、探している商品そのものか。合えば点数（大きいほどよい）、合わなければ None"""
    title = item.get("itemName") or ""
    if NG.search(title):
        return None
    req, soft = tokens(name)
    if not req:
        return None
    nt, q = _n(title), _n(" ".join(req))
    if any(_n(t) not in nt for t in req):
        return None
    for v in VARIANT:
        if v in nt and v not in _n(name):
            return None
    shop = (item.get("shopName") or "") + " " + (item.get("itemUrl") or "")
    sc = 10 if re.search(r"楽天ブックス|books\.rakuten\.co\.jp|item\.rakuten\.co\.jp/book/", shop) or item.get("shopCode") == "book" else 0
    sc += sum(1 for t in soft if _n(t) in nt)
    core = _n(re.sub(r"[（(][^）)]*[）)]", "", unicodedata.normalize("NFKC", title)))   # カッコ書き（作品名・型番）は数えない
    sc -= max(0, len(core) - len(q)) / 20  # 余計な語が少ないほうがよい（同じシリーズの別の商品より、名前がぴったりの物）
    return sc


def _image(item):
    """いちばん大きい写真（楽天の画像サーバーのサイズ指定 ?_ex= を外したもの）"""
    for key in ("mediumImageUrls", "smallImageUrls"):
        imgs = item.get(key) or []
        if imgs:
            u = imgs[0]["imageUrl"] if isinstance(imgs[0], dict) else imgs[0]
            return re.sub(r"\?_ex=\d+x\d+$", "", u or "")
    return ""


def thumb(url, px=300):
    """カードの写真用（楽天の画像サーバーなら px 四方に縮めて返す）"""
    if not url:
        return ""
    if re.search(r"(thumbnail\.image|image)\.rakuten\.co\.jp", url):
        return re.sub(r"\?_ex=\d+x\d+$", "", url) + f"?_ex={px}x{px}"
    return url


def _tcg_setting(key):
    """トレカ側の設定（config/settings.yaml）の値。楽天・Amazonのアフィリエイトの番号は人ごとに1つなので、
    ゲーム側に入っていなければトレカ側と同じものを使う"""
    try:
        import yaml
        return str((yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}).get(key) or "")
    except Exception:
        return ""


def affiliate_id(settings):
    return (os.environ.get("RAKUTEN_AFFILIATE_ID_GAME") or settings.get("rakuten_affiliate_id") or os.environ.get("RAKUTEN_AFFILIATE_ID")
            or _tcg_setting("rakuten_affiliate_id")).strip()


def amazon_tag(settings):
    return (os.environ.get("AMAZON_TAG_GAME") or settings.get("amazon_tag") or os.environ.get("AMAZON_TAG")
            or _tcg_setting("amazon_tag")).strip()


def rakuten_link(url, aff):
    from rakuten import item_link
    return item_link(url, aff) if url else ""


def amazon_link(asin, tag):
    asin = (asin or "").strip().upper()
    if not (tag and re.fullmatch(r"[A-Z0-9]{10}", asin)):
        return ""
    return f"https://www.amazon.co.jp/dp/{asin}?tag={tag}"


def item_page_ok(url):
    """商品そのもののページか（検索結果・一覧のページは使わない）"""
    u = urlparse(url or "")
    if u.scheme not in ("http", "https") or "search" in (u.netloc + u.path).lower():
        return False
    return bool(re.match(r"(books\.rakuten\.co\.jp/rb/\d+|item\.rakuten\.co\.jp/[^/]+/[^/]+)", u.netloc + u.path))


def _item_code(url):
    """楽天の商品ページのURL → 商品検索APIの itemCode（楽天ブックス：book:<番号>、楽天市場：<店>:<商品>）"""
    u = urlparse(url or "")
    m = re.match(r"/rb/(\d+)", u.path) if u.netloc == "books.rakuten.co.jp" else None
    if m:
        return f"book:{m.group(1)}"
    m = re.match(r"/([^/]+)/([^/]+)", u.path) if u.netloc == "item.rakuten.co.jp" else None
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def _models():
    import yaml
    p = ROOT / "config" / "game" / "models.yaml"
    y = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}
    return y.get("series_shop") or {}


def manual_of(i, models=None):
    """手で書いた rakuten_url / amazon_asin / jan（1件ごと＞機種・モデルごと）"""
    by = (models if models is not None else _models()).get(i.get("game")) or {}
    m = by.get(i.get("series") or "")
    if m is None and i.get("series") and by:
        from sitegen_game import canon_series   # 別名（PlayStation 5 Pro → PS5 Pro など）でも見つける
        m = by.get(canon_series(i["game"], i["series"]))
    m = m or {}
    return {k: str(i.get(k) or m.get(k) or "").strip() for k in ("rakuten_url", "amazon_asin", "jan", "yahoo_url")}


def query_of(i, man=None):
    """この1件で探すもの：(state のキー, 種類, 探す語)。探さないものは None"""
    man = man or manual_of(i)
    if man["rakuten_url"]:
        code = _item_code(man["rakuten_url"])
        return (f"url:{man['rakuten_url']}", "code", code) if code else None
    if i.get("game") in SKIP_GAMES:
        return None
    if re.fullmatch(r"\d{8}|\d{13}", man["jan"]):
        return (f"jan:{man['jan']}", "jan", man["jan"])
    name = i.get("product") or i.get("series") or ""
    req, _ = tokens(name)
    if not req:
        return None
    return ("q:" + _n(" ".join(req)), "name", name)


def http_fetch(params, settings):
    """楽天の商品検索API（トレカと同じ。新APIは Referer が必須＝楽天に登録したサイトのURLを送る）"""
    import requests
    from rakuten import ENDPOINT
    site = (os.environ.get("RAKUTEN_REFERER") or os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")
    p = dict(params, applicationId=os.environ.get("RAKUTEN_APP_ID", "").strip(), format="json", formatVersion=2)
    headers = {"accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", "").strip(), "Referer": site + "/", "Origin": site, "User-Agent": "game-nyuka/1.0"}
    r = requests.get(ENDPOINT, params=p, headers=headers, timeout=20)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        err = data.get("error_description") or data.get("error") or data.get("errors") or r.text[:200]
        raise RuntimeError(f"楽天API {r.status_code}: {err}")
    return data.get("Items") or []


def update(settings, items, fetch=None, sleep=1.1):
    """items（lotteries.json の値）の商品を楽天ブックスで探し、state/game/rakuten.json を更新して返す。
    fetch(params) → 楽天の Items のリスト（テストでは偽物を渡す）"""
    cache = load_json(CACHE, {})
    if fetch is None:
        if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
            return cache
        fetch = lambda p: http_fetch(p, settings)  # noqa: E731
    budget = int(settings.get("rakuten_max_calls_per_run", 15))
    hours = float(settings.get("rakuten_refresh_hours", 24))
    aff = affiliate_id(settings)
    models = _models()
    t = now()
    todo, seen = [], set()
    for i in sorted(items, key=lambda x: (x.get("end") or x.get("start") or "9999")):
        q = query_of(i, manual_of(i, models))
        if not q or q[0] in seen:
            continue
        seen.add(q[0])
        c = cache.get(q[0])
        if c and parse_dt(c.get("checkedAt")) and (t - parse_dt(c["checkedAt"])).total_seconds() < hours * 3600:
            continue
        todo.append(q)
    called = 0
    for key, how, word in todo:
        if called >= budget:
            break
        params = {"hits": 30, "availability": 0, "imageFlag": 1}   # availability=0：売り切れの商品も（入荷お知らせのため）
        if how == "code":
            params = {"itemCode": word, "availability": 0}
        else:
            params.update(keyword=word if how == "jan" else keyword(word), shopCode="book")
        if aff:
            params["affiliateId"] = aff
        if called and sleep:
            time.sleep(sleep)   # 楽天は1秒に1回まで。失敗した後も必ず間をあける
        called += 1
        found, err = None, None
        for attempt in range(2):
            try:
                found = fetch(params)
                break
            except Exception as e:
                err = e
                if "429" in str(e) and attempt == 0:
                    if sleep:
                        time.sleep(max(sleep, 1) * 3)   # 混んでいたら少し待ってもう1回だけ
                    continue
                break
        if found is None:
            log(f"楽天（ゲーム）: {word} 取得失敗 {err}")
            if "401" in str(err) or "403" in str(err):
                break   # 鍵・Referer の設定ミス。無駄に叩かない
            continue
        best = None
        for it in found:
            if how == "name":
                sc = match(it, word)
            else:   # JAN・商品ページのURLで探したものは、その商品そのもの（周辺機器・中古だけは外す）
                sc = None if NG.search(it.get("itemName") or "") and how == "jan" else 0
            if sc is not None and (best is None or sc > best[0]):
                best = (sc, it)
        if best:
            it = best[1]
            url = it.get("itemUrl") or ""
            if "hb.afl.rakuten.co.jp" in url:
                from urllib.parse import parse_qs
                url = (parse_qs(urlparse(url).query).get("pc") or [url])[0]
            url = url.split("?")[0]   # ?rafcid=… などの計測用の付け足しは外す
            cache[key] = {"itemUrl": url, "affiliateUrl": rakuten_link(url, aff), "imageUrl": _image(it),
                          "title": it.get("itemName") or "", "checkedAt": t.isoformat()}
            log(f"楽天（ゲーム）: {word[:30]} → {(it.get('itemName') or '')[:40]}")
        else:
            cache[key] = {"itemUrl": "", "checkedAt": t.isoformat()}   # 見つからないものも記録（24時間は探さない）
            log(f"楽天（ゲーム）: {word[:30]} 該当なし")
    if called:
        save_json(CACHE, cache)
    return cache


def links_for(i, cache, settings, models=None):
    """1件分の {"rk": {"u": 楽天の商品ページ（アフィリエイト）, "img": 写真}, "az": Amazonの商品ページ}（無いものは入れない）"""
    man = manual_of(i, models)
    out = {}
    q = query_of(i, man)
    c = (cache or {}).get(q[0]) if q else None
    aff = affiliate_id(settings)
    url = man["rakuten_url"] if man["rakuten_url"] and item_page_ok(man["rakuten_url"]) else (c or {}).get("itemUrl") or ""
    if url and item_page_ok(url):
        rk = {"u": rakuten_link(url, aff)}
        if c and c.get("imageUrl"):
            rk["img"] = thumb(c["imageUrl"])
        out["rk"] = rk
    az = amazon_link(man["amazon_asin"], amazon_tag(settings))
    if az:
        out["az"] = az
    # Yahoo!ショッピング（商品ページの指定があればそれ、なければ商品名で探すページ）・メルカリ（商品名で探すページ）
    from urllib.parse import quote
    import game_souba
    q = game_souba._q(i.get("product") or i.get("series") or "")
    # ポケカ・ワンピカード：楽天ブックスに商品ページが無いことが多いので、楽天・Amazonの「商品名で探す」ページ（アフィリエイト）を出す（11/10）
    if i.get("game") in ("pokemon", "onepiece") and q:
        if "rk" not in out:
            out["rk"] = {"u": rakuten_link(f"https://search.rakuten.co.jp/search/mall/{quote(q)}/", aff), "search": True}
        if "az" not in out:
            out["az"] = f"https://www.amazon.co.jp/s?k={quote(q)}&tag={amazon_tag(settings)}"
    yh = (man.get("yahoo_url") or "").strip()
    if yh or q:
        out["yh"] = yh or f"https://shopping.yahoo.co.jp/search?p={quote(q)}"
    if q:
        out["mc"] = f"https://jp.mercari.com/search?keyword={quote(q)}&status=on_sale&afid=1350793153"   # メルカリのアフィリエイト（ユーザーのID）
    return out


def watch_list(lots, settings, cache=None, models=None):
    """楽天・Amazonの見張り（worker/game-watch）に渡す一覧：サイトに載っている商品のうち、楽天の商品ページかAmazonの商品番号が分かっているもの"""
    import re as _re
    from common import now as _now, parse_dt as _pd
    cache = cache if cache is not None else load_json(CACHE, {})
    models = models if models is not None else _models()
    t = _now()
    out, seen = [], set()
    for k, i in lots.items():
        if i.get("status") not in ("approved", "listed", "posted"):
            continue
        e = _pd(i.get("end"))
        if e and e < t and i.get("kind") != "release":
            continue
        man = manual_of(i, models)
        q = query_of(i, man)
        c = (cache or {}).get(q[0]) if q else None
        rk = man["rakuten_url"] or (c or {}).get("itemUrl") or ""
        m = _re.search(r"item\.rakuten\.co\.jp/([^/]+)/([^/?#]+)", rk)
        code = f"{m.group(1)}:{m.group(2)}" if m else ""
        asin = man["amazon_asin"].upper() if _re.fullmatch(r"[A-Za-z0-9]{10}", man["amazon_asin"] or "") else ""
        if not (code or asin) or (code, asin) in seen:
            continue
        seen.add((code, asin))
        import game_xpost as gx
        out.append({"k": k, "n": (i.get("product") or "")[:40], "g": gx.is_game(i), "rk": code, "asin": asin,
                    "nopost": i.get("game") in set(settings.get("x_exclude_games") or []),   # 見張るが投稿しない（一番くじなど）
                    "hot": __import__("game_premium").premium_match(i.get("product") or "", settings) is not None,   # 定価以上で売れる商品
                    "tag": ((__import__("gamecats").by_id(False).get(i.get("game")) or {}).get("hashtags") or "").split()[:1]})
    return out
