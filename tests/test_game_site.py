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
            "ps5/ps5-midnight-black/index.html", "switch2/index.html", "gunpla/index.html", "fukubukuro/index.html",
            "chain/sonystore/ps5/index.html", "chain/pbandai/gunpla/index.html", "l/a1/index.html", "guide/index.html",
            "guide/how-to-read/index.html", "x-draft.html", "sitemap.xml", "robots.txt", "404.html", "privacy.html", "og.png", "favicon.svg", "llms.txt", ".changed"]
    for f in need:
        assert f in files, (f, files)
    # すべてのカテゴリ（有効なもの）のページができる
    for c in gamecats.categories():
        assert f"{c['slug']}/index.html" in files, c["slug"]
    top = (out / "index.html").read_text(encoding="utf-8")
    head = top[:top.index("</head>")]
    assert "<title>ゲーム機・ホビーの抽選・予約・再入荷情報まとめ【" in head and "｜ゲーム・ホビー入荷速報</title>" in head
    assert 'rel="canonical" href="https://example-game.jp/"' in head and '"BreadcrumbList"' not in head and '"WebSite"' in head and '"FAQPage"' in head
    assert "記載の社名・製品名は各社の商標です。当サイトは各社と関係ありません。" in top                 # 商標の注意書き
    assert "Amazonのアソシエイトとして、ゲーム・ホビー入荷速報は適格販売により収入を得ています" in top     # アフィリエイト表記
    assert "本ページはプロモーションを含みます" in top
    assert 'class="pin"' in top and "tag=g-22" in top and "Amazon 招待リクエスト（PS5）" in top         # 先頭の固定の招待
    assert "ソニーストア" in top and "終了店" not in top and "一番くじONLINE" not in top                  # 終了して20日・承認待ちは載せない
    assert "119,980円" in top and "PSN必須" in top
    assert 'content="#1b3a5c"' in head                                                                 # 別ブランドの色（トレカの赤ではない）
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
    assert 'content="#1b3a5c"' in d1
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
