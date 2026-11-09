"""ゲーム・ホビー入荷速報：ページごとの中身の量を毎回測る（11/9 ユーザーの指示）

・サイトを書き出したあとに、検索に出す全ページの「本文の文字数」と「そのページだけの文字数」を数える
  そのページだけの文字数＝同じ種類のページ（/premium/… など）の半分以上に出てくる行（決まり文句・メニュー）を除いた文字数
・state/game/content_volume.json に {パス: [本文, そのページだけ]} を残す（次の回の解説文づくり game_aitext が、少ないページから順に使う）
・/content-report.html（検索に出さない）に、種類ごとの平均と、少ないページの一覧を出す。ログにも1行
"""
import html as _html
import re
from collections import Counter, defaultdict
from html import escape

from common import load_json, save_json, now, log

STATE = "content_volume.json"


def _lines(h):
    m = re.search(r"<h1[^>]*>.*", h, re.S)   # 見出しから下＝本文（左のメニュー・検索窓は入れない）
    h = m.group(0) if m else h
    h = re.sub(r"(?s)<(script|style|nav|aside|footer)[^>]*>.*?</\1>", " ", h)
    t = _html.unescape(re.sub(r"<[^>]+>", "\n", h))
    return [re.sub(r"\s+", " ", x).strip() for x in t.split("\n") if len(x.strip()) >= 2]


def measure(out, target=1500):
    """out（書き出したフォルダ）の検索に出すページを数える → {パス: [本文, そのページだけ]}"""
    pages = {}
    for p in out.rglob("index.html"):
        h = p.read_text(encoding="utf-8")
        if 'content="noindex' in h[:6000]:
            continue
        path = str(p.parent.relative_to(out)).replace("\\", "/")
        pages["" if path == "." else path + "/"] = _lines(h)
    by_tpl = defaultdict(list)
    for path, ls in pages.items():
        by_tpl[path.split("/")[0] if path.count("/") >= 2 else "(一覧)"].append(path)
    res = {}
    for tpl, ps in by_tpl.items():
        freq = Counter(x for path in ps for x in set(pages[path]))
        common = {x for x, c in freq.items() if len(ps) >= 4 and c >= len(ps) * 0.5}
        for path in ps:
            ls = pages[path]
            res[path] = [sum(len(x) for x in ls), sum(len(x) for x in ls if x not in common)]
    save_json(STATE, {"at": now().isoformat(), "target": target, "pages": res})
    # 報告のページ（検索に出さない）
    rows = []
    for tpl, ps in sorted(by_tpl.items(), key=lambda kv: -len(kv[1])):
        u = [res[p][1] for p in ps]
        rows.append((tpl, len(ps), round(sum(res[p][0] for p in ps) / len(ps)), round(sum(u) / len(u)), sum(1 for x in u if x < target)))
    thin = sorted(res.items(), key=lambda kv: kv[1][1])[:80]
    t_rows = "".join(f"<tr><td>{escape(a)}</td><td>{b}</td><td>{c:,}</td><td>{d:,}</td><td>{e}</td></tr>" for a, b, c, d, e in rows)
    p_rows = "".join(f'<tr><td><a href="/{escape(p)}">/{escape(p)}</a></td><td>{v[0]:,}</td><td>{v[1]:,}</td></tr>' for p, v in thin)
    (out / "content-report.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><title>ページの中身の量</title><style>body{font-family:system-ui;max-width:900px;margin:0 auto;padding:16px}'
        'table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}</style></head><body>'
        f'<h1>ページの中身の量（{now():%m/%d %H:%M}）</h1><p>「そのページだけの文字数」＝同じ種類のページの半分以上に出てくる決まり文句を除いた文字数。目標 {target:,}文字。</p>'
        f'<h2>種類ごと</h2><table><tr><th>種類</th><th>ページ数</th><th>本文の平均</th><th>そのページだけの平均</th><th>目標未満</th></tr>{t_rows}</table>'
        f'<h2>そのページだけの文字数が少ないページ</h2><table><tr><th>ページ</th><th>本文</th><th>そのページだけ</th></tr>{p_rows}</table></body></html>', encoding="utf-8")
    u_all = [v[1] for v in res.values()]
    if u_all:
        log(f"ページの中身：検索に出す{len(u_all)}ページ・そのページだけの文字数の平均 {round(sum(u_all) / len(u_all)):,}文字・"
            f"目標{target:,}文字未満 {sum(1 for x in u_all if x < target)}ページ（/content-report.html）")
    return res
