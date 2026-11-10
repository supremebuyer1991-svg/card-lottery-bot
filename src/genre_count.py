"""ほかのトレカのタイトルの抽選がどれくらいあるかを数えるだけ（11/10 ユーザー：取り扱うタイトルを広げる前に1週間調べる）

・cardchusen.com のトップにあるジャンル別の件数（遊戯王・デュエマ・ヴァイス など）を1日1回記録する
・AIは使わない。サイトにもXにも出さない。記録は state/genre_counts.json（日付ごと）
"""
import re

from common import load_json, save_json, log, now

URL = "https://cardchusen.com/"
NAMES = ("ポケカ", "ワンピ", "遊戯王", "ドラゴンボール", "デュエマ", "ヴァイス", "ガンダム", "ユニオンアリーナ", "ユニアリ",
         "ロルカナ", "シャドウバース", "バトスピ", "ドラクエ", "ほかのジャンル")


def parse(html):
    """ページの文字から「ジャンル名 〇件」を拾う"""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"&nbsp;|\s+", " ", txt)
    out = {}
    for n in NAMES:
        m = re.search(re.escape(n) + r"[^\d件]{0,12}?(\d{1,5})\s*件", txt)
        if m:
            out[n] = int(m.group(1))
    return out, txt


def update(settings=None):
    data = load_json("genre_counts.json", {})
    today = now().strftime("%Y-%m-%d")
    if today in data:
        return
    from fetch import get
    html = get(URL)
    got, txt = parse(html)
    if len(got) < 3:
        i = txt.find("遊戯王")
        log(f"ジャンル別の件数: 読めなかった（{got}）。周辺: {txt[max(0, i - 200):i + 400]!r}")
        return
    data[today] = got
    save_json("genre_counts.json", dict(sorted(data.items())[-60:]))
    log("ジャンル別の件数: " + "・".join(f"{k}{v}" for k, v in got.items()))
