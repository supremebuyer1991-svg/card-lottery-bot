"""自作サイト書き出しのテスト"""
import sys, tempfile, re, subprocess
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
from common import now, save_json, load_settings
import sitegen

common.STATE_DIR = Path(tempfile.mkdtemp())
out = Path(tempfile.mkdtemp())
s = load_settings(); s.update(site_public_url="https://example.jp", amazon_tag="t-22")
def it(k, g, store, series, h, ch="online", area=None, status="posted"):
    return {"key": k, "game": g, "store": store, "product": f"「{series}」BOX", "series": series,
            "end": (now() + timedelta(hours=h)).isoformat(), "url": "https://shop.example/", "channel": ch,
            "area": area, "status": status, "id_check": False, "member": "none", "tags": []}
lots = [it("a", "pokemon", "ヨドバシ", "弾A", 5), it("b", "pokemon", "イオン難波店", "弾A", 20, "store", "大阪府"),
        it("c", "pokemon", "店C", "弾B", 30, status="listed"), it("d", "onepiece", "プレバン", "航海", 10),
        it("e", "pokemon", "終了店", "弾A", -3), it("f", "pokemon", "保留店", "弾A", 9, status="pending")]
save_json("lotteries.json", {x["key"]: x for x in lots})
sitegen.build(s, out_dir=out)
files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
assert "index.html" in files and "pokeka/index.html" in files and "pokeka/area/osaka/index.html" in files, files
assert "sitemap.xml" in files and "robots.txt" in files and ".changed" in files
assert sum(1 for f in files if f.startswith("pokeka/s-")) == 2 and any(f.startswith("onepiece/s-") for f in files)
sp = next(out.glob("pokeka/s-*/index.html"))
seriesA = [p for p in out.glob("pokeka/s-*/index.html") if "「弾A」の抽選" in p.read_text()][0].read_text()
assert re.search(r"<title>【ポケカ】弾Aの抽選販売・予約の最新情報まとめ【\d+/\d+更新】受付中2件", seriesA)       # 終了・保留は載せない
assert "FAQPage" in seriesA and "よくある質問" in seriesA and "WebPage" in seriesA  # 弾ページのQ&A・更新日（検索向け）
head = seriesA[:seriesA.index("</head>")]                                          # title・説明・正規URLは <head> の中
assert "<title>" in head and 'name="description"' in head and 'rel="canonical"' in head and 'og:image' in head
assert '"BreadcrumbList"' in head and '"ItemList"' in head and 'class="crumbs"' in seriesA and 'class="summary"' in seriesA
assert (out / "og.png").exists() and (out / "favicon.svg").exists()
assert "ヨドバシ" in seriesA and "終了店" not in re.sub(r'<script type="application/json".*?</script>', "", seriesA, flags=re.S)
assert 'rel="canonical" href="https://example.jp/pokeka/s-' in seriesA and "tag=t-22" in seriesA
osaka = (out / "pokeka/area/osaka/index.html").read_text()
assert "大阪府のポケカ店頭抽選" in osaka and '"area": "大阪府"' in osaka
assert "https://example.jp/pokeka/area/osaka/" in (out / "sitemap.xml").read_text()
# JSの文法チェック
js = re.findall(r"<script>(.*?)</script>", seriesA, re.S)[0]
Path(tempfile.gettempdir(), "s.js").write_text(js)
assert subprocess.run(["node", "--check", str(Path(tempfile.gettempdir(), "s.js"))]).returncode == 0
# 変化なし → .changed を作らない（無駄な公開をしない）
sitegen.build(s, out_dir=out)
assert not (out / ".changed").exists()
print("SITE ALL OK")
