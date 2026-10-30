"""重複まとめのテスト  python tests/test_dedupe.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import save_json, load_json
import dedupe

E = "2026-10-28T23:59:00+09:00"
cc = "カード抽選まとめ ポケカ"
save_json("lotteries.json", {
    "y1": {"game": "pokemon", "store": "ヤマダデンキ（ヤマダデジタル会員アプリ）", "series": "30th CELEBRATION", "product": "拡張パック「30th CELEBRATION」", "end": E, "status": "approved", "source": cc, "url": "https://www.yamada-denki.jp/x"},
    "y2": {"game": "pokemon", "store": "ヤマダ電機", "series": "30th CELEBRATION", "product": "30th CELEBRATION", "end": E, "status": "approved", "source": "X「ポケカ 抽選」", "url": "https://x.com/a/status/1"},
    "y3": {"game": "pokemon", "store": "ヤマダデンキ", "series": "30th CELEBRATION", "product": "30th BOX", "end": E, "status": "pending", "source": "入荷Now 入荷情報"},
    # cardchusen 同士で商品が違う（セット違い）→ まとめない
    "g1": {"game": "pokemon", "store": "高砂ジム", "series": "御三家", "product": "御三家（フシギダネ）", "end": E, "status": "listed", "source": cc, "url": "u1"},
    "g2": {"game": "pokemon", "store": "高砂ジム", "series": "御三家", "product": "御三家（チコリータ）", "end": E, "status": "listed", "source": cc, "url": "u2"},
    # 締切なしでXから拾った同じ店・同じ弾（書き方違い）→ まとめる
    "p1": {"game": "pokemon", "store": "ポケモンセンターオンライン", "series": None, "product": "ピカピカボックス2027（5,500円税込・お1人様1回まで）", "end": E, "status": "listed", "source": cc, "url": "https://www.pokemon.co.jp/x"},
    "p2": {"game": "pokemon", "store": "ポケモンセンターオンライン", "series": None, "product": "ピカピカボックス2027", "end": None, "status": "listed", "source": "X「ポケカ 抽選」", "url": "https://t.co/x"},
    # 別のゲームはまとめない
    "w1": {"game": "onepiece", "store": "ヤマダ電機", "series": "30th CELEBRATION", "product": "x", "end": E, "status": "approved", "source": "X「ワンピカード 抽選」"},
})
n = dedupe.dedupe({"rakuten_aliases": {}})
L = load_json("lotteries.json", {})
assert L["y1"]["status"] == "approved" and L["y2"]["status"] == "duplicate" and L["y3"]["status"] == "duplicate", L
assert L["g1"]["status"] == "listed" and L["g2"]["status"] == "listed"
assert L["p1"]["status"] == "listed" and L["p2"]["status"] == "duplicate"
assert L["w1"]["status"] == "approved" and n == 3
print("DEDUPE OK")

# 1つのフォームで別々の商品（あみあみ：BOX と デッキセット）→ まとめない。前にまとめたものは戻す
F = "https://form.amiami.jp/draw20261030"
E2 = "2099-11-04T13:59:00+09:00"
save_json("lotteries.json", {
    "a1": {"game": "pokemon", "store": "あみあみ本店", "series": "ハドウシーカー", "product": "ハドウシーカー BOX", "end": E2, "status": "duplicate", "duplicate_of": "a2", "source": "入荷Now 入荷情報", "url": F},
    "a2": {"game": "pokemon", "store": "あみあみ本店", "series": "ドリームex", "product": "スペシャルデッキセットMEGA", "end": E2, "status": "approved", "source": "入荷Now 入荷情報", "url": F},
    "a3": {"game": "pokemon", "store": "あみあみ", "series": "ハドウシーカー", "product": "ハドウシーカー", "end": None, "status": "approved", "source": "X「ポケカ 抽選」", "url": F},
})
dedupe.dedupe({"rakuten_aliases": {}})
L = load_json("lotteries.json", {})
assert L["a1"]["status"] == "approved" and L["a2"]["status"] == "approved", L
assert L["a3"]["status"] == "duplicate" and L["a3"]["duplicate_of"] == "a1", L
dedupe.dedupe({"rakuten_aliases": {}})
L = load_json("lotteries.json", {})
assert L["a1"]["status"] == "approved" and L["a2"]["status"] == "approved", L
print("DEDUPE AMIAMI OK")
