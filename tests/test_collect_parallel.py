"""情報元を同時に読む（collect_parallel）のテスト  python tests/test_collect_parallel.py
同時に読んでも、順番どおり読んだときと同じ抽選が同じ順番で登録されること・記事の数の上限を守ること"""
import sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common


def rss(n, tag):
    items = "".join(f"<item><title>{tag} 抽選 {i}</title><link>https://ex{tag}.jp/a{i}</link><guid>{tag}-{i}</guid>"
                    f"<pubDate>Wed, 11 Nov 2026 10:00:00 +0900</pubDate><description>d</description></item>" for i in range(n))
    return f"<rss><channel>{items}</channel></rss>"


def run(par):
    common.STATE_DIR = Path(tempfile.mkdtemp())
    import importlib, collect
    importlib.reload(collect)
    pages = {f"https://feed{k}.jp/rss": rss(2, f"s{k}") for k in range(8)}
    busy, peak = [0], [0]
    lk = threading.Lock()

    def fetch(u):   # 一覧ページはもともと先読みで同時に読むので、AIの読み取りの同時数を見る
        return pages[u]

    def ext(text, game, gname, sname, url):
        with lk:
            busy[0] += 1
            peak[0] = max(peak[0], busy[0])
        time.sleep(0.05)
        with lk:
            busy[0] -= 1
        first = text.split("\n")[0]
        return [{"game": "ps5", "store": sname, "product": first, "kind": "lottery", "end": "2099-01-01T00:00:00+09:00"}]

    src = [{"id": f"s{k}", "game": "ps5", "name": f"店{k}", "type": "rss", "url": f"https://feed{k}.jp/rss"} for k in range(8)]
    S = {"game_names": {"ps5": "PS5"}, "collect_parallel": par}
    got = collect.collect(src, S, extractor=ext, fetcher=fetch)
    return [(i["store"], i["product"]) for i in got], peak[0]


seq, p1 = run(1)
par, p6 = run(6)
assert len(seq) == 16, seq
assert seq == par, (seq, par)       # 同じものが同じ順番で
assert p6 > 1 and p1 == 1, (p1, p6)  # 同時に読んでいる
print("COLLECT PARALLEL OK", len(par), "件・同時に最大", p6)
