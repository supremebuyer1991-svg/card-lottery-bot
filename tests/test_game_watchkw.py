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
st = w.update(S, fetch=lambda p: rows, sleep=lambda s: None)
assert set(st["items"]) == {"book:1", "book:5"}, st
out = w.watch_items(S, have_codes={"book:5"})
assert [o["rk"] for o in out] == ["book:1"] and out[0]["k"] == "kwbook:1" and out[0]["nopost"] is False, out
# 1日1回：すぐもう一度呼んでも探し直さない
called = []
w.update(S, fetch=lambda p: called.append(1) or rows, sleep=lambda s: None)
assert not called
print("WATCHKW OK")
