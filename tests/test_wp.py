"""WP自動更新のテスト（WPはダミー）。output/ にプレビューHTMLも書き出す"""
import sys, tempfile
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
from common import now, load_settings, save_json, lottery_key
import wp as wpmod

common.STATE_DIR = Path(tempfile.mkdtemp())
s = load_settings()
s.update(dry_run=False, site_url="https://example.com", amazon_tag="test-22")


def lot(store, series, hours, status="posted", cond=None):
    it = {"game": "pokemon", "store": store, "product": f"拡張パック「{series}」BOX", "series": series,
          "end": (now() + timedelta(hours=hours)).isoformat(timespec="minutes"), "conditions": cond,
          "url": "https://example.com/apply", "status": status}
    it["key"] = lottery_key(it)
    return it


shop1 = lot("イオン難波店", "テスト弾A", 30); shop1.update(channel="store", area="大阪府")
shop2 = lot("カードショップ〇〇 梅田店", "テスト弾A", 50); shop2.update(channel="store", area="大阪府")
shop3 = lot("イオン幕張新都心店", "テスト弾A", 40); shop3.update(channel="store", area="千葉県")
items = [shop1, shop2, shop3, lot("ヨドバシ.com", "テスト弾A", 10, cond="ゴールドポイントカード会員"),
         lot("セブンネット", "テスト弾A", 72), lot("ビックカメラ", "テスト弾A", -30, status="closed"),
         lot("イオン", "テスト弾B", 100)]
save_json("lotteries.json", {i["key"]: i for i in items})


class FakeWP:
    def __init__(self):
        self.calls = []

    def upsert(self, kind, slug, title, content, extra=None):
        self.calls.append((kind, slug, title, content))


f = FakeWP()
wpmod.update_pages(s, wp=f)
kinds = sorted(c[0] for c in f.calls)
assert kinds.count("pages") == 3 and kinds.count("posts") == 2, kinds
a = next(c for c in f.calls if "テスト弾A" in c[2])
assert a[2].startswith("【5件受付中】"), a[2]
assert "実店舗の抽選（3件）" in a[3] and "<h3>大阪府</h3>" in a[3] and "<h3>千葉県</h3>" in a[3]
from xpost import compose
assert compose(shop1, s).startswith("【🏪店頭抽選】［大阪府］イオン難波店")
assert "締切間近" in a[3] and "ヨドバシ" in a[3].split("受付終了")[0]
assert "amazon.co.jp/s?k=" in a[3] and "tag=test-22" in a[3] and 'rel="nofollow sponsored' in a[3]
assert "プロモーション" in a[3]
top = next(c for c in f.calls if c[1] == "pokeca-lottery")
assert wpmod.series_slug("pokemon", "テスト弾A") in top[3]          # まとめ→弾記事の内部リンク

f2 = FakeWP()
wpmod.update_pages(s, wp=f2)
assert f2.calls == [], f2.calls                                       # 変化なしなら更新しない

out = Path(__file__).resolve().parent.parent / "output"
out.mkdir(exist_ok=True)
(out / "preview_series.html").write_text(
    f'<html><head><meta charset="utf-8"><title>{a[2]}</title>'
    '<style>body{font-family:sans-serif;max-width:760px;margin:24px auto;padding:0 16px;line-height:1.7}'
    'table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px}'
    'th{background:#f5f5f5}</style></head><body>'
    f'<h1>{a[2]}</h1>{a[3]}</body></html>', encoding="utf-8")

# ---- まとめサイト（一覧→記事）からの収集 ----
from collect import collect
for f in ("seen.json", "lotteries.json"):
    (common.STATE_DIR / f).unlink(missing_ok=True)
pages = {
    "https://site.example/cat": '<a href="/a/1">ポケモンカード テスト弾の抽選まとめ</a><a href="/a/2">GeForce 入荷</a>'
                                '<a href="https://other.example/x">ポケモンカード 外部</a>',
    "https://site.example/a/1": '<p>ヨドバシ 抽選 11/3まで</p><a href="https://shop.example/apply">応募はこちら</a><p>B店 抽選</p>',
}
opened = []
def fetcher(u):
    opened.append(u); return pages[u]
def ext(text, game, gname, sname, url):
    assert "https://shop.example/apply" in text
    e = (now() + timedelta(days=3)).isoformat()
    return [{"store": "ヨドバシ", "product": "テスト弾", "end": e, "url": "https://shop.example/apply", "confidence": 0.9, "game": "pokemon"},
            {"store": "B店", "product": "テスト弾", "end": e, "url": url, "confidence": 0.9, "game": "pokemon"}]
src = [{"id": "idx", "game": "auto", "name": "まとめ", "type": "html_index", "url": "https://site.example/cat",
        "link_keywords": ["ポケモンカード"], "quote": False, "hide_source_url": True}]
common.save_json("seen.json", {"idx": {}})
new = collect(src, s, extractor=ext, fetcher=fetcher)
assert opened == ["https://site.example/cat", "https://site.example/a/1"], opened   # 無関係・外部記事は開かない
by = {i["store"]: i for i in new}
assert by["ヨドバシ"]["url"] == "https://shop.example/apply"
assert by["B店"]["url"] is None and by["B店"]["confidence"] <= 0.5             # 他サイトURLは載せず承認待ちへ
opened.clear()
assert collect(src, s, extractor=ext, fetcher=fetcher) == [] and len(opened) == 2  # 記事に変化なし→AI呼ばない

# ---- 一覧型サイト（カード単位の差分） ----
def page(n_extra=0, remain="15"):
    cards_html = "".join(
        f'<div class="card"><p>店{i}</p><p>テスト弾 BOX</p><p>残り{remain}時間</p><span>会員</span>'
        f'<a href="https://shop{i}.example/apply">抽選に応募する！</a><a href="/how">応募方法をみる</a></div>'
        for i in range(3 + n_extra))
    return f'<html><body><a href="/pokeka">ポケカ</a><div class="list">{cards_html}</div></body></html>'
sent = []
def ext2(text, game, gname, sname, url):
    sent.append(text)
    return []
src2 = [{"id": "cc", "game": "pokemon", "name": "一覧", "type": "html_cards",
         "url": "https://list.example/pokeka", "quote": False, "hide_source_url": True}]
collect(src2, s, extractor=ext2, fetcher=lambda u: page())
assert len(sent) == 1 and sent[0].count("応募URL:") == 3, sent
assert "店1" in sent[0].split("=====")[1] and "店0" not in sent[0].split("=====")[1]  # カードごとに分離
sent.clear()
collect(src2, s, extractor=ext2, fetcher=lambda u: page(remain="9"))
assert sent == []                                    # 残り時間が変わっただけ → AIを呼ばない
collect(src2, s, extractor=ext2, fetcher=lambda u: page(n_extra=1, remain="8"))
assert len(sent) == 1 and sent[0].count("応募URL:") == 1 and "shop3" in sent[0]  # 新着1件だけ
print("WP ALL OK")
