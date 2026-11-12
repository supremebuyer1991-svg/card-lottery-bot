"""言葉で楽天ブックスのおもちゃを探して見張りに足す  python tests/test_game_watchkw.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
import game_watchkw as w

rows = [{"itemName": "BEYBLADE X BX-48 ブースター ○○", "itemCode": "book:1", "itemUrl": "https://item.rakuten.co.jp/book/1/"},
        {"itemName": "ベイブレードX 公式ガイドブック", "itemCode": "book:2"},          # 本は外す
        {"itemName": "BEYBLADE X 中古 BX-01", "itemCode": "book:3"},                # 中古は外す
        {"itemName": "ポケモン ぬいぐるみ", "itemCode": "book:4"},                  # ジャンルの言葉が無いものは外す
        {"Item": {"itemName": "ベイブレードX UX-22 スターター", "itemCode": "book:5"}}]
S = {"watch_keywords": [{"q": "ベイブレードX", "game": "beyblade", "pages": 1}], "x_exclude_games": []}
books = [{"title": "BEYBLADE X BX-48 ブースター ○○", "jan": "4904810000001"},   # JANが分かる → JANで見張る（楽天・Amazonの両方）
         {"title": "ベイブレードX 攻略ガイド", "jan": "9784000000000"},           # 本は外す
         {"title": "BEYBLADE X CX-20 スターター", "jan": "4904810000002"}]
st = w.update(S, fetch=lambda p: rows, sleep=lambda s: None, books=lambda q, pg: books)
assert set(st["items"]) == {"book:1", "book:5"}, st
assert set(st["jans"]) == {"4904810000001", "4904810000002"}, st["jans"]
out = w.watch_items(S, have_codes={"book:5"}, have_jans={"4904810000002"})
# JANの分（BX-48）と、JANの無い楽天の分のうち、同じ名前がJANにあるもの（BX-48）は二重にしない
assert [o["k"] for o in out] == ["j4904810000001"], out
assert out[0]["jan"] == "4904810000001" and out[0]["nopost"] is False, out
# 1日1回：すぐもう一度呼んでも探し直さない
called = []
w.update(S, fetch=lambda p: called.append(1) or rows, sleep=lambda s: None, books=lambda q, pg: called.append(1) or books)
assert not called
print("WATCHKW OK")
