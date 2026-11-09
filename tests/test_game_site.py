"""ゲーム・ホビー入荷速報（SITE=game）のサイト書き出しのテスト  python tests/test_game_site.py
ネットもAIも使わない。見本のデータから site_game/ 相当を一時フォルダに作って確かめる"""
import os
import re
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

if __name__ != "__main__":
    # pytest から呼ばれた時は別プロセスで動かす（SITE=game の環境変数と読み込み済みの部品が、トレカのテストに混ざらないように）
    import subprocess
    _r = subprocess.run([sys.executable, __file__], capture_output=True, text=True, env=dict(os.environ, SITE="game"))
    assert _r.returncode == 0, _r.stdout[-2000:] + _r.stderr[-3000:]
else:
    os.environ["SITE"] = "game"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import common  # noqa: E402

    common.STATE_DIR = Path(tempfile.mkdtemp())
    from common import now, save_json, load_settings  # noqa: E402
    import sitegen_game  # noqa: E402
    import gamecats  # noqa: E402

    assert common.SITE == "game" and common.CONFIG_DIR.name == "game"
    s = load_settings()
    assert "ps5" in s["game_names"] and "gunpla" in s["game_names"], s["game_names"]   # カテゴリは categories.yaml から
    assert "pokemon" not in s["game_names"]
    s.update(site_public_url="https://example-game.jp", amazon_tag="g-22",
             amazon_invite={"enabled": True, "label": "Amazon 招待リクエスト（PS5）", "url": "https://www.amazon.co.jp/dp/TEST"})
    out = Path(tempfile.mkdtemp())


    def it(k, g, store, series, product, kind, h_end=None, h_start=None, status="listed", **kw):
        d = {"key": k, "game": g, "store": store, "series": series, "product": product, "kind": kind, "status": status,
             "url": "https://shop.example/x", "channel": "online", "tags": [], "found_at": (now() - timedelta(hours=2)).isoformat()}
        if h_end is not None:
            d["end"] = (now() + timedelta(hours=h_end)).isoformat()
        if h_start is not None:
            d["start"] = (now() + timedelta(hours=h_start)).isoformat()
        d.update(kw)
        return d


    lots = [
        it("a1", "ps5", "ソニーストア", "PS5 Pro", "PlayStation 5 Pro 本体", "lottery", 30, -10, tags=["PSN必須", "プレイ時間", "1人1台"], price="119,980円", announce=(now() + timedelta(days=3)).date().isoformat()),
        it("a2", "ps5", "ヨドバシ.com", "PS5 ミッドナイト ブラック", "PlayStation 5 ミッドナイト ブラック 本体", "preorder", None, 48, tags=["会員"]),
        it("a3", "ps5", "ビックカメラ.com", "PS5 本体", "PlayStation 5 本体", "restock"),
        it("a4", "switch2", "マイニンテンドーストア", "Switch 2 本体", "Nintendo Switch 2 本体 第8回抽選", "lottery", -5, -200, announce=(now() + timedelta(days=1)).date().isoformat(), round="第8回", tags=["NSO加入", "前回落選者優先"]),
        it("a5", "fukubukuro", "ヨドバシ.com", "夢のお年玉箱 2027", "夢のお年玉箱 2027 ゲームの夢", "fukubukuro", 100, -1, tags=["会員", "購入履歴"]),
        it("a6", "gunpla", "プレミアムバンダイ", "RG Hi-νガンダム", "RG 1/144 Hi-νガンダム 抽選販売", "lottery", 72, price="5,500円"),
        it("a7", "gunpla", "BANDAI SPIRITS", "HG νガンダム", "HG 1/144 νガンダム 再販", "release", 24 * 10, store_is_maker=True),
        it("a8", "ps5", "終了店", "PS5 本体", "PlayStation 5 本体", "lottery", -24 * 20),   # 20日前に終了 → 載せない
        it("a9", "handheld_pc", "Steam（Valve）", "Steam Deck", "Steam Deck OLED 再入荷", "restock", status="listed"),
        it("b1", "ichibankuji", "一番くじONLINE", "一番くじ テスト", "一番くじ テスト ONLINE", "lottery", 10, status="pending"),   # 承認待ちは載せない
    ]
    save_json("lotteries.json", {x["key"]: x for x in lots})
    sitegen_game.build(s, out_dir=out)
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    need = ["index.html", "now/index.html", "today/index.html", "calendar/index.html", "ps5/index.html", "ps5/ps5-pro/index.html",
            "ps5/ps5-midnight-black/index.html", "switch2/index.html", "gunpla/index.html",
            "chain/sonystore/ps5/index.html", "chain/pbandai/gunpla/index.html", "l/a1/index.html", "guide/index.html",
            "guide/how-to-read/index.html", "x-draft.html", "sitemap.xml", "robots.txt", "404.html", "privacy.html", "og.png", "favicon.svg", "llms.txt", ".changed"]
    for f in need:
        assert f in files, (f, files)
    # すべてのカテゴリ（有効なもの）のページができる
    for c in gamecats.categories():
        assert f"{c['slug']}/index.html" in files, c["slug"]
    top = (out / "index.html").read_text(encoding="utf-8")
    head = top[:top.index("</head>")]
    assert "<title>ゲーム・ホビーの再販・入荷速報と買取相場【" in head and "｜ゲーム・ホビー入荷速報</title>" in head
    assert 'rel="canonical" href="https://example-game.jp/"' in head and '"BreadcrumbList"' not in head and '"WebSite"' in head and '"FAQPage"' in head
    assert "記載の社名・製品名は各社の商標です。当サイトは各社と関係ありません。" in top                 # 商標の注意書き
    assert "Amazonのアソシエイトとして、ゲーム・ホビー入荷速報は適格販売により収入を得ています" in top     # アフィリエイト表記
    assert "本ページはプロモーションを含みます" in top
    assert 'class="pin"' in top and "tag=g-22" in top and "Amazon 招待リクエスト（PS5）" in top         # 先頭の固定の招待
    assert "ソニーストア" in top and "終了店" not in top and "一番くじONLINE" not in top                  # 終了して20日・承認待ちは載せない
    assert "119,980円" in top and "PSN必須" in top
    assert 'name="theme-color" content="#0b0d12"' in head                                              # 暗い見た目のブランドの色（トレカの赤ではない）
    # 見た目（11/8 承認のデザイン）：左のメニュー・リンリンのお知らせ・絞り込み・今週の発売・フォント
    assert 'class="side"' in top and 'カテゴリ（商品数）' in top and '抽選・受付' in top and 'Xで発売の通知を受け取る' in top   # 11/9：カテゴリを上に、抽選・受付は下に
    assert 'id="rin"' in top and 'src="/rinrin.png"' in top and 'id="bubble"' in top and 'id="week"' in top
    for f_ in ("f-nomember", "f-online", "f-nohist"):
        assert f'id="{f_}"' in top, f_
    assert "Zen+Kaku+Gothic+New" in head and "Chakra+Petch" in head and "display=swap" in head
    assert '"cc":[' in top
    assert "<header" not in top                                                                         # 上のバーではなく左のメニュー
    assert "#c8102e" not in top
    # トレカの言葉がまぎれこんでいない
    for bad in ("トレカ抽選ナビ", "ポケカ", "ワンピース", "tcg-chusen", "pokepi_tcg", "フュージョンワールド"):
        assert bad not in top, bad
    # 任天堂・ソニーの名前をサイト名に入れない（本文のお店名としては出てよい）
    assert "ゲーム・ホビー入荷速報" in head and not re.search(r"<title>[^<]*(Nintendo|Switch|PlayStation|Sony|任天堂)[^<]*入荷速報", head)
    # 下書きは検索に載せない
    xd = (out / "x-draft.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex' in xd and "#PS5Pro" in xd and "#ガンプラ" in xd
    # サイトマップ：主なページとカテゴリ・モデル・個別ページ。下書きは入れない
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://example-game.jp/ps5/ps5-pro/" in sm and "https://example-game.jp/l/a1/" in sm and "https://example-game.jp/gunpla/" in sm
    assert "x-draft" not in sm and "https://example-game.jp/now/" in sm and "https://example-game.jp/calendar/" in sm
    assert "Disallow: /x-draft.html" in (out / "robots.txt").read_text(encoding="utf-8")
    # 個別ページ
    d1 = (out / "l/a1/index.html").read_text(encoding="utf-8")
    assert "<title>ソニーストアのPS5抽選「PS5 Pro」" in d1 and "｜ゲーム・ホビー入荷速報</title>" in d1
    assert "定価" in d1 and "119,980円" in d1 and "トレカ抽選ナビ" not in d1 and "応募した" not in d1 and "記載の社名・製品名は各社の商標です" in d1
    assert 'name="theme-color" content="#0b0d12"' in d1 and 'class="side"' in d1 and "Chakra+Petch" in d1 and "IBM+Plex" not in d1
    assert not re.search("[\U0001F300-\U0001FAFF]", d1)                                               # 絵文字のアイコンは出さない
    assert 'class="shell"' in d1 and d1.count("<main") == 1 and "本ページはプロモーションを含みます" in d1
    e404 = (out / "404.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex"' in e404 and 'class="side"' in e404
    assert 'class="side"' in (out / "privacy.html").read_text(encoding="utf-8")
    # カレンダー：発売日（release）と予約開始が載る
    cal = (out / "calendar/index.html").read_text(encoding="utf-8")
    assert "HG 1/144 νガンダム 再販" in cal and "発売・再販" in cal and "ミッドナイト ブラック" in cal
    # 今日締切ページ・いま一覧
    assert 'id="matrix"' in (out / "now/index.html").read_text(encoding="utf-8")
    # JSの文法チェック
    js = re.findall(r"<script>(.*?)</script>", top, re.S)
    assert js
    jsp = Path(tempfile.gettempdir(), "g.js")
    jsp.write_text(js[-1], encoding="utf-8")
    assert subprocess.run(["node", "--check", str(jsp)]).returncode == 0
    jsp.write_text(re.findall(r"<script>(.*?)</script>", xd, re.S)[-1], encoding="utf-8")
    assert subprocess.run(["node", "--check", str(jsp)]).returncode == 0
    # 2回目：変化なし → .changed を作らない
    save_json("lotteries.json", {x["key"]: x for x in lots})
    sitegen_game.build(s, out_dir=out)
    print("GAME SITE OK", len(files), "files")

    # ---- カテゴリを設定ファイルで足すと、ページとサイトマップにその分が増える ----
    import yaml
    cy = yaml.safe_load((common.ROOT / "config/game/categories.yaml").read_text(encoding="utf-8"))
    cy["categories"].append({"id": "testcat", "group": "hobby", "name": "テストのカテゴリ", "short": "テスト", "slug": "testcat",
                             "hashtags": "#テスト", "hints": "テスト商品", "strip_words": "テスト", "kinds": ["lottery"], "enabled": True})
    cp = Path(tempfile.mkdtemp()) / "categories.yaml"
    cp.write_text(yaml.safe_dump(cy, allow_unicode=True), encoding="utf-8")
    gamecats.PATH = cp
    gamecats._CACHE.clear()
    s2 = load_settings()
    s2.update(site_public_url="https://example-game.jp")
    assert "testcat" in s2["game_names"]
    assert gamecats.hints()["testcat"].search("テスト商品 A")
    save_json("lotteries.json", {"t1": it("t1", "testcat", "テスト店", "テストA", "テスト商品 A", "lottery", 20)})
    out2 = Path(tempfile.mkdtemp())
    sitegen_game.build(s2, out_dir=out2)
    assert (out2 / "testcat/index.html").exists() and "https://example-game.jp/testcat/" in (out2 / "sitemap.xml").read_text(encoding="utf-8")
    assert "テスト商品 A" in (out2 / "index.html").read_text(encoding="utf-8")
    gamecats.PATH = common.ROOT / "config" / "game" / "categories.yaml"
    gamecats._CACHE.clear()
    print("CATEGORY CONFIG OK")

    # ---- 商品写真と「楽天で見る」「Amazonで見る」（楽天は偽物のAPIで。ネットにはつながない） ----
    import json
    import game_affi
    for k_ in ("RAKUTEN_AFFILIATE_ID_GAME", "RAKUTEN_AFFILIATE_ID", "AMAZON_TAG_GAME", "AMAZON_TAG", "RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY"):
        os.environ.pop(k_, None)
    common.STATE_DIR = Path(tempfile.mkdtemp())
    s3 = load_settings()
    s3.update(site_public_url="https://example-game.jp", amazon_tag="g-22", rakuten_affiliate_id="aff.test")
    IMG = "https://thumbnail.image.rakuten.co.jp/@0_mall/book/cabinet/0000/4948872000000.jpg"
    BOOK = {"shopName": "楽天ブックス", "shopCode": "book"}
    calls = []

    def fake_fetch(params):
        calls.append(params)
        kw = params.get("keyword") or ""
        if params.get("itemCode") == "book:12345678":
            return [dict(BOOK, itemName="RG 1/144 Hi-νガンダム", itemUrl="https://item.rakuten.co.jp/book/12345678/?rafcid=x", mediumImageUrls=[IMG + "?_ex=128x128"])]
        if "Pro" in kw:
            return [dict(BOOK, itemName="PS5 Pro用 保護フィルム", itemUrl="https://item.rakuten.co.jp/book/1/", mediumImageUrls=[IMG]),            # 周辺機器は使わない
                    dict(BOOK, itemName="【中古】PlayStation 5 Pro", itemUrl="https://item.rakuten.co.jp/book/2/", mediumImageUrls=[IMG]),           # 中古は使わない
                    dict(BOOK, itemName="PlayStation 5 Pro(CFI-7000B01)", itemUrl="https://item.rakuten.co.jp/book/18000001/?rafcid=wsc", mediumImageUrls=[IMG + "?_ex=128x128"])]
        if "ミッドナイト" in kw:
            return [dict(BOOK, itemName="PlayStation 5 Pro(CFI-7000B01)", itemUrl="https://item.rakuten.co.jp/book/3/", mediumImageUrls=[IMG])]  # 別のモデルは使わない
        return []

    lots3 = [
        it("p1", "ps5", "ソニーストア", "PS5 Pro", "PlayStation 5 Pro 本体", "lottery", 30, -10, price="119,980円", amazon_asin="B0TEST1234"),
        it("p2", "ps5", "ヨドバシ.com", "PS5 ミッドナイト ブラック", "PlayStation 5 ミッドナイト ブラック 本体", "preorder", None, 48),
        it("p3", "gunpla", "プレミアムバンダイ", "RG Hi-νガンダム", "RG 1/144 Hi-νガンダム 抽選販売", "lottery", 72, rakuten_url="https://books.rakuten.co.jp/rb/12345678/"),
        it("p4", "ichibankuji", "ローソン", "一番くじ テスト", "一番くじ テスト", "release", 24),
        it("p5", "gunpla", "プレミアムバンダイ", "HG テスト", "HG 1/144 テストガンダム", "lottery", 50, rakuten_url="https://search.rakuten.co.jp/search/mall/HG/"),   # 検索ページは使わない
    ]
    save_json("lotteries.json", {x["key"]: x for x in lots3})
    cache = game_affi.update(s3, lots3, fetch=fake_fetch, sleep=0)
    assert all(c.get("shopCode") == "book" for c in calls if "keyword" in c), calls          # 楽天ブックスにしぼる
    assert all(c.get("availability") == 0 for c in calls), calls                              # 売り切れも（入荷お知らせのため）
    assert not any("一番くじ" in (c.get("keyword") or "") for c in calls)                       # 一番くじは探さない
    assert any(c.get("itemCode") == "book:12345678" and c.get("affiliateId") == "aff.test" for c in calls)   # 手で書いた商品ページは商品コードで写真を取る
    pro = cache["q:" + game_affi._n("PlayStation 5 Pro")]
    assert pro["itemUrl"] == "https://item.rakuten.co.jp/book/18000001/" and pro["imageUrl"] == IMG and pro["checkedAt"] and "CFI-7000" in pro["title"]
    assert "hb.afl.rakuten.co.jp/hgc/aff.test/" in pro["affiliateUrl"]
    mb = cache["q:" + game_affi._n("PlayStation 5 ミッドナイト ブラック")]
    assert mb["itemUrl"] == "" and mb["checkedAt"]                                           # 見つからないものも記録
    n_calls = len(calls)
    game_affi.update(s3, lots3, fetch=fake_fetch, sleep=0)
    assert len(calls) == n_calls                                                             # 24時間はもう一度探さない
    # 1回の上限
    common.STATE_DIR = Path(tempfile.mkdtemp())
    calls.clear()
    game_affi.update(dict(s3, rakuten_max_calls_per_run=1), lots3, fetch=fake_fetch, sleep=0)
    assert len(calls) == 1
    # 鍵が無ければ何もしない（ネットにつながない・state も作らない）
    common.STATE_DIR = Path(tempfile.mkdtemp())
    assert game_affi.update(s3, lots3) == {} and not (common.STATE_DIR / "rakuten.json").exists()
    # サイトに出す（さっきの結果で）
    common.STATE_DIR = Path(tempfile.mkdtemp())
    save_json("lotteries.json", {x["key"]: x for x in lots3})
    save_json("rakuten.json", cache)
    out3 = Path(tempfile.mkdtemp())
    sitegen_game.build(s3, out_dir=out3)
    top3 = (out3 / "index.html").read_text(encoding="utf-8")
    data3 = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', top3, re.S).group(1))
    by = {i["key"]: i for i in data3["items"]}
    assert by["p1"]["rk"]["img"] == IMG + "?_ex=300x300" and by["p1"]["rk"]["u"].startswith("https://hb.afl.rakuten.co.jp/hgc/aff.test/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fbook%2F18000001%2F")
    assert by["p1"]["az"] == "https://www.amazon.co.jp/dp/B0TEST1234?tag=g-22"                 # ASIN を書いたものだけ Amazon
    assert by["p3"]["rk"]["u"].startswith("https://hb.afl.rakuten.co.jp/hgc/aff.test/?pc=https%3A%2F%2Fbooks.rakuten.co.jp%2Frb%2F12345678%2F") and by["p3"]["rk"]["img"]  # 手で書いたURLが優先
    assert "rk" not in by["p2"] and "az" not in by["p2"]                                     # 見つからない → 写真もボタンも無し
    assert "rk" not in by["p4"] and "rk" not in by["p5"]                                     # 一番くじ・検索ページのURL
    assert "楽天で見る" in top3 and "Amazonで見る" in top3 and 'class="ph"' in top3 and "has-ph" in top3 and 'loading="lazy"' in top3
    assert "商品の写真は楽天ブックス（楽天市場）の商品の写真です" in top3                          # 写真の出どころ
    assert "Amazonのアソシエイトとして、ゲーム・ホビー入荷速報は適格販売により収入を得ています" in top3
    for b_ in ("円〜", "itemPrice"):                                                          # 楽天の値段は出さない
        assert b_ not in top3, b_
    d1 = (out3 / "l/p1/index.html").read_text(encoding="utf-8")
    assert 'class="pics n1"' in d1 and IMG + "?_ex=300x300" in d1 and 'width="150" height="150"' in d1 and 'alt="PS5 Pro"' in d1
    assert 'class="btn btn-rk"' in d1 and "楽天で見る" in d1 and "https://www.amazon.co.jp/dp/B0TEST1234?tag=g-22" in d1 and "Amazonで見る" in d1
    assert "商品の写真は楽天ブックス" in d1
    d2 = (out3 / "l/p2/index.html").read_text(encoding="utf-8")
    assert 'class="pics' not in d2 and "楽天で見る" not in d2 and "Amazonで見る" not in d2 and "商品の写真は楽天ブックス" not in d2
    assert "メルカリで探す" in d2 and "jp.mercari.com/search?keyword=" in d2 and "Yahoo!で見る" in d2          # 楽天・Amazonが無くても、Yahoo!・メルカリは出す
    # 楽天・Amazon のリンクは、どのページでも検索結果のページではない
    for f_ in out3.rglob("*.html"):
        for u_ in re.findall(r"https?://[^\"'\s<>]*(?:rakuten|amazon)[^\"'\s<>]*", f_.read_text(encoding="utf-8")):
            if "thumbnail.image.rakuten" in u_:
                continue
            assert "search" not in u_.lower() and "/s?" not in u_, (f_, u_)
    # 機種・モデルごとの指定（models.yaml の series_shop）
    game_affi._models = lambda: {"ps5": {"PS5 ミッドナイト ブラック": {"amazon_asin": "B0MIDNIGHT", "rakuten_url": "https://books.rakuten.co.jp/rb/99999999/"}}}
    lk = game_affi.links_for(lots3[1], {}, s3)
    assert lk["az"] == "https://www.amazon.co.jp/dp/B0MIDNIGHT?tag=g-22" and "books.rakuten.co.jp%2Frb%2F99999999" in lk["rk"]["u"] and "img" not in lk["rk"]
    assert game_affi.amazon_tag({}) == game_affi._tcg_setting("amazon_tag") != ""            # ゲーム側が空ならトレカ側と同じタグ
    assert game_affi.affiliate_id({}) == game_affi._tcg_setting("rakuten_affiliate_id") != ""
    _tcg = game_affi._tcg_setting
    game_affi._tcg_setting = lambda k: ""
    assert "az" not in game_affi.links_for(lots3[1], {}, dict(s3, amazon_tag=""))            # タグがどこにも無ければ Amazon は出さない
    game_affi._tcg_setting = _tcg
    # 楽天：半角1文字の語は検索語から外す（keyword is not valid の対策）。429 は待ってもう1回、間は毎回あける
    assert game_affi.keyword("Nintendo Switch 2 選べるソフト セット") == "Nintendo Switch 選べるソフト セット"
    assert game_affi.keyword("PlayStation 5 ミッドナイト ブラック") == "PlayStation ミッドナイト ブラック"
    # JSの文法チェック
    jsp.write_text(re.findall(r"<script>(.*?)</script>", top3, re.S)[-1], encoding="utf-8")
    assert subprocess.run(["node", "--check", str(jsp)]).returncode == 0
    print("AFFILIATE OK")
