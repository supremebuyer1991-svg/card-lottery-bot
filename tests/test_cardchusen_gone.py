"""cardchusen の一覧から消えた抽選を終了にするテスト  python tests/test_cardchusen_gone.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import load_settings, load_json, save_json, now
from collect import collect

s = load_settings()
end = (now().replace(microsecond=0)).isoformat()[:10] + "T23:59:00+09:00"


def page(n, skip=()):
    arts = []
    for k in range(n):
        if k in skip:
            continue
        arts.append(f'<article class="board-card" id="c{k}" data-entry-end="{end}" data-lottery-type="store" data-area="tokyo">'
                    f'<div class="board-card__store" title="テスト商品{k}">店{k}</div>'
                    f'<a class="board-card__cta" href="https://shop.example/{k}">応募</a></article>')
    return "<html><body>" + "".join(arts) + "</body></html>"


src = [{"id": "cc", "game": "pokemon", "name": "カード抽選まとめ ポケカ", "type": "html_cards", "url": "https://cardchusen.example/"}]
save_json("seen.json", {"_v": 5, "cc": {}})
html = {"v": page(40)}
collect(src, s, extractor=lambda *a: [], fetcher=lambda u: html["v"])
L = load_json("lotteries.json", {})
assert len(L) == 40 and all(i["status"] in ("new", "listed") for i in L.values())

# 2件が一覧から消える → その2件だけ終了
html["v"] = page(40, skip={3, 7})
collect(src, s, extractor=lambda *a: [], fetcher=lambda u: html["v"])
L = load_json("lotteries.json", {})
closed = sorted(i["store"] for i in L.values() if i["status"] in ("closed", "expired"))
assert closed == ["店3", "店7"], closed

# 読み込みが少なすぎる（壊れた可能性）時は何もしない
html["v"] = page(5)
collect(src, s, extractor=lambda *a: [], fetcher=lambda u: html["v"])
L = load_json("lotteries.json", {})
assert sum(1 for i in L.values() if i["status"] in ("closed", "expired")) == 2
print("CARDCHUSEN GONE OK")
