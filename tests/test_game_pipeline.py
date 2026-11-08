"""ゲーム・ホビー入荷速報（SITE=game）の一連の流れのテスト（AIと取得はダミー）  python tests/test_game_pipeline.py"""
import os
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
    os.environ.pop("ANTHROPIC_API_KEY", None)   # 締切の調査・振り分けのAIは呼ばない
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import common  # noqa: E402

    common.STATE_DIR = Path(tempfile.mkdtemp())
    from common import now, load_settings, load_json, lottery_key, fix_game  # noqa: E402
    import extract  # noqa: E402
    import game_pipeline  # noqa: E402
    from dedupe import norm_series  # noqa: E402

    assert common.SITE == "game" and common.STATE_DIR.name  # state は別フォルダ
    s = load_settings()
    assert s["game_names"]["ps5"].startswith("PS5") and "gunpla" in s["game_names"]
    # ゲーム版の指示（プロンプト）とカテゴリの一覧
    assert "kind を次から1つ決める" in extract.PROMPT and "転売やフリマの値段は絶対に出力しない" in extract.PROMPT
    assert extract._category_list().startswith("ps5（") and "gunpla（" in extract._category_list()
    assert "ps5" in extract.valid_games() and "pokemon" not in extract.valid_games()
    # トレカの指示はファイルから読んでも同じ
    assert "トレカ抽選情報の抽出係" in (common.ROOT / "src/prompts/tcg_extract.txt").read_text(encoding="utf-8")

    end = (now() + timedelta(hours=10)).isoformat(timespec="minutes")
    end2 = (now() + timedelta(days=5)).isoformat(timespec="minutes")
    past = (now() - timedelta(days=1)).isoformat(timespec="minutes")


    def fake_extract(text, game, gname, sname, url):
        items = [
            {"store": "ソニーストア", "product": "PlayStation 5 Pro 本体", "series": "PS5 Pro", "kind": "lottery", "end": end,
             "conditions": "PSNアカウント連携・プレイ時間の条件あり", "tags": ["PSN必須", "プレイ時間"], "url": "https://store.example/ps5pro", "confidence": 0.9, "game": "ps5", "price": "119,980円"},
            {"store": "ビックカメラ.com", "product": "PlayStation 5 本体", "series": "PS5 本体", "kind": "restock", "end": None, "url": "https://bic.example/ps5", "confidence": 0.9, "game": "ps5"},
            {"store": "ヨドバシ.com", "product": "PlayStation 5 ミッドナイト ブラック", "series": "PS5 ミッドナイト ブラック", "kind": "preorder",
             "start": (now() + timedelta(days=2)).isoformat(timespec="minutes"), "end": None, "url": "https://yodo.example/mb", "confidence": 0.9, "game": "ps5"},
            {"store": "謎の店", "product": "不明商品", "kind": "lottery", "end": None, "confidence": 0.3, "game": "ps5"},
            {"store": "終了店", "product": "古い抽選", "kind": "lottery", "end": past, "confidence": 0.9, "game": "ps5"},
            {"store": "BANDAI SPIRITS", "product": "HG 1/144 νガンダム 再販", "series": "HG νガンダム", "kind": "release",
             "end": (now() + timedelta(days=9)).date().isoformat() + "T23:59", "confidence": 0.9, "game": "ps5"},   # カテゴリがまちがっている → hints で gunpla に直る
        ]
        for it in items:
            it.update(source=sname, source_url=url, url=it.get("url") or url)
            fix_game(it)
        return items


    # カテゴリの直し（hints）と strip_words
    x = {"game": "ps5", "product": "HG 1/144 νガンダム", "series": None}
    assert fix_game(x) and x["game"] == "gunpla"
    assert norm_series("PlayStation 5 Pro 本体 通常版", {}) == norm_series("PlayStation 5 Pro", {})   # 「本体」「通常版」は無視
    # 再入荷・先着のキーは見つけた日が入る（同じ商品でも日が違えば別）
    k1 = lottery_key({"game": "ps5", "store": "A", "product": "PS5", "kind": "restock", "found_at": "2026-11-01T10:00"})
    k2 = lottery_key({"game": "ps5", "store": "A", "product": "PS5", "kind": "restock", "found_at": "2026-11-02T10:00"})
    k3 = lottery_key({"game": "ps5", "store": "A", "product": "PS5", "kind": "lottery", "end": "2026-11-10T23:59"})
    assert k1 != k2 and k1 != k3
    assert lottery_key({"game": "gunpla", "store": "X", "product": "HG", "kind": "release", "end": "2026-11-20"}) == \
           lottery_key({"game": "gunpla", "store": "Y", "product": "HG", "kind": "release", "end": "2026-11-20"})   # 発売日はお店に関係なく1件

    src = [{"id": "t", "game": "auto", "name": "テスト", "type": "html", "url": "https://example.com"}]
    html = "<html><body><p>PS5 Pro 抽選のお知らせ</p></body></html>"
    common.save_json("seen.json", {"_v": 5, "t": "x"})
    out = Path(tempfile.mkdtemp())
    game_pipeline.run("all", extractor=fake_extract, fetcher=lambda u: html, out_dir=out, sources=src)
    lots = load_json("lotteries.json", {})
    by = {i["store"]: i for i in lots.values() if not i.get("manual")}   # 手動追加分は別に確認
    assert "終了店" not in by                                   # 締切済みは拾わない
    assert by["ソニーストア"]["status"] == "approved" and by["ソニーストア"]["kind"] == "lottery"
    assert by["ビックカメラ.com"]["status"] == "approved"      # 再入荷は締切が無くても載せる
    assert by["ヨドバシ.com"]["status"] == "approved"          # 予約（開始日あり）
    assert by["謎の店"]["status"] == "pending"                 # 自信度不足は承認待ち
    assert by["BANDAI SPIRITS"]["game"] == "gunpla" and by["BANDAI SPIRITS"]["kind"] == "release"
    # 手動追加（config/game/manual.yaml）は、有効なカテゴリ・種類で取り込まれている
    import yaml
    import gamecats
    cats = gamecats.by_id()
    mf = Path(__file__).resolve().parent.parent / "config/game/manual.yaml"
    want = {e["slug"] for e in (yaml.safe_load(mf.read_text(encoding="utf-8")).get("lotteries") or [])}
    manual = [i for i in lots.values() if i.get("manual")]
    assert len(manual) == len(want)
    assert all(i["game"] in cats for i in manual)
    # サイトができている
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert "index.html" in files and "ps5/index.html" in files and "gunpla/index.html" in files and "x-draft.html" in files
    top = (out / "index.html").read_text(encoding="utf-8")
    assert "ソニーストア" in top and "謎の店" not in top and "トレカ抽選ナビ" not in top
    # 2回目：変化なし → AIを呼ばない・.changed なし
    game_pipeline.run("all", extractor=lambda *a: (_ for _ in ()).throw(AssertionError("再抽出した")), fetcher=lambda u: html, out_dir=out, sources=src)
    # 再入荷は3日で一覧から外れる
    lots = load_json("lotteries.json", {})
    by["ビックカメラ.com"] = next(i for i in lots.values() if i["store"] == "ビックカメラ.com")
    by["ビックカメラ.com"]["found_at"] = (now() - timedelta(days=4)).isoformat()
    common.save_json("lotteries.json", lots)
    from approve import approve
    approve(s)
    lots = load_json("lotteries.json", {})
    assert next(i for i in lots.values() if i["store"] == "ビックカメラ.com")["status"] in ("closed", "expired")
    # 発売日を過ぎた release は終了
    r = next(i for i in lots.values() if i["store"] == "BANDAI SPIRITS")
    r["end"] = (now() - timedelta(days=1)).isoformat()
    common.save_json("lotteries.json", lots)
    game_pipeline._end_releases(lots)
    assert r["status"] == "closed"
    print("GAME PIPELINE OK")
