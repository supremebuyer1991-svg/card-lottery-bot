import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import xbuzz

lots = {str(n): {"status": "listed", "game": "pokemon" if n % 2 else "onepiece", "store": f"店{n}",
                 "series": ["A弾", "B弾", "C弾"][n % 3], "channel": "store" if n % 4 else "online",
                 "area": ["東京都", "大阪府", "愛知県"][n % 3]} for n in range(30)}
s = {"hashtags": {"pokemon": "#ポケカ", "onepiece": "#ワンピカード"}}
kinds = set()
for d in range(5):
    k, t = xbuzz.compose_buzz(lots, s, day=d)
    assert t and "http" not in t and xbuzz.x_len(t) <= 280, t
    kinds.add(k)
assert len(kinds) == 5, kinds
k, t = xbuzz.compose_buzz({}, s, day=0)
assert k == "aruaru"  # データが無くても、あるあるは出せる
print("ok")
