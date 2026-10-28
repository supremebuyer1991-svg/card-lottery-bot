"""新着の抽選を見つけたら、そのままXに貼れる投稿文を Discord に送る（手で投稿する用・無料）

・GitHub の Secret「DISCORD_WEBHOOK_URL」に Discord のウェブフックURLを入れると動く（無ければ何もしない）
・サイトの公開のあとに動く（リンク先にもう載っている状態で届く）
・最初の1回は、いま載っている抽選を「お知らせ済み」にするだけ（大量に届かないように）
・同じ抽選は二度送らない。締切が後から分かって中身が変わっても、同じ店・同じ商品なら送らない
・Xの有料の仕組み（API）は使わない
"""
import os
import re
import time
from datetime import timedelta

import requests

from common import load_json, save_json, load_settings, log, now, parse_dt, normalize

ACTIVE = ("approved", "posted", "listed")
GAME = {
    "pokemon": ("ポケカ", "pokeka", "#ポケカ #ポケカ抽選"),
    "onepiece": ("ワンピースカード", "onepiece", "#ワンピースカード #ワンピースカード抽選"),
}
WEEK = "月火水木金土日"
ROWS_PER_POST = 10   # 1つの投稿文にのせる店の数
POSTS_PER_RUN = 3    # 1回の実行で1ゲームあたり送る投稿文の数（残りは次の回に）
KEEP_DAYS = 7        # 同じ店・同じ商品を「お知らせ済み」とみなす日数（2次抽選などは7日たてば届く）


def _name(i):
    from xdraft import _name as n
    return n(i)


def _sig(i):
    """同じ抽選かどうか（締切が後から変わっても同じになるよう、締切は入れない）"""
    return "|".join([i.get("game") or "", normalize(i.get("store")), normalize(_name(i))])


def _end_text(i):
    e = parse_dt(i.get("end"))
    if not e:
        return "締切は応募ページで確認"
    return f"{e.month}/{e.day}({WEEK[e.weekday()]}) {e:%H:%M}まで"


# ゲームの区分がまちがっていそうな商品は送らない（ポケカにヒロインズエディション、など）
WRONG_GAME = {
    "pokemon": re.compile(r"heroines|ヒロインズ|one\s*piece|ワンピース|ワンピカ", re.I),
    "onepiece": re.compile(r"ポケモン|ポケカ|30th\s*celebration|30周年|ハドウシーカー|ストームエメラルダ|エーフィ|メガ[^\s]*ex", re.I),
}


def _is_open(i, t):
    if i.get("status") not in ACTIVE or i.get("game") not in GAME:
        return False
    if WRONG_GAME[i["game"]].search(" ".join([i.get("series") or "", i.get("product") or ""])):
        return False
    e = parse_dt(i.get("end"))
    return not e or e > t


def compose(game, items, site):
    """X に貼る投稿文。items は締切が早い順"""
    label, slug, tags = GAME[game]
    rows, seen = [], {}
    for i in items:
        k = re.sub(r"\s", "", i.get("store") or "")
        if k in seen:
            if _name(i) not in seen[k][1]:
                seen[k][1].append(_name(i))
            continue
        seen[k] = (i, [_name(i)])
        rows.append(k)
    lines = [f"🆕新着｜{label}の抽選", ""]
    for k in rows:
        i, names = seen[k]
        lines.append(f"・{(i.get('store') or '').strip()}（{_end_text(i)}）")
        lines.append("　" + names[0] + (f" ほか{len(names) - 1}種" if len(names) > 1 else ""))
    lines += ["", "応募方法・ほかのお店はこちら👇", f"{site}/{slug}/", "", tags]
    return "\n".join(lines)


def _send(url, text):
    # flags=4 … リンクのプレビュー（大きなカード）を出さない。投稿文だけをコピーしやすくする
    for _ in range(3):
        r = requests.post(url, json={"content": text[:2000], "username": "トレカ抽選ナビ 新着", "flags": 4},
                          timeout=20)
        if r.status_code == 429:  # 送りすぎ → 少し待ってもう1回
            time.sleep(min(float((r.json() or {}).get("retry_after", 2)), 10))
            continue
        r.raise_for_status()
        return True
    return False


def run(webhook=None, lots=None, site=None, t=None):
    webhook = "".join((webhook if webhook is not None else os.environ.get("DISCORD_WEBHOOK_URL", "")).split())
    if not webhook:
        log("新着のお知らせ: DISCORD_WEBHOOK_URL が未登録なのでスキップ")
        return 0
    s = load_settings()
    site = (site or s.get("site_public_url") or os.environ.get("SITE_URL") or "").rstrip("/")
    t = t or now()
    lots = lots if lots is not None else load_json("lotteries.json", {})
    st = load_json("notify.json", {})
    keys, sigs = set(st.get("keys") or []), dict(st.get("sigs") or {})
    open_items = {k: i for k, i in lots.items() if _is_open(i, t)}

    if not st.get("started"):
        # 最初の1回：いま載っている分は送らずに「お知らせ済み」にする
        keys |= set(open_items)
        for i in open_items.values():
            sigs[_sig(i)] = t.isoformat(timespec="minutes")
        try:
            _send(webhook, "✅ トレカ抽選ナビの新着お知らせを始めました。\n"
                           "これから新しい抽選が見つかるたびに、Xにそのまま貼れる投稿文がここに届きます。")
        except Exception as e:
            log(f"新着のお知らせ: 送信失敗 {e}")
            return 0
        st["started"] = t.isoformat(timespec="minutes")
        sent = 0
    else:
        todo = {}
        for k, i in open_items.items():
            if k in keys:
                continue
            if _sig(i) in sigs:  # 同じ店・同じ商品はもう送った（締切が後から分かった等）
                keys.add(k)
                continue
            todo.setdefault(i["game"], []).append((k, i))
        sent = 0
        far = t + timedelta(days=3650)
        for g, li in todo.items():
            li.sort(key=lambda x: parse_dt(x[1].get("end")) or far)
            for n in range(POSTS_PER_RUN):
                chunk, stores = [], set()
                for k, i in li:  # 同じ店はまとめて1行なので、店の数で区切る
                    if any(k == c[0] for c in chunk):
                        continue
                    sk = re.sub(r"\s", "", i.get("store") or "")
                    if sk not in stores and len(stores) >= ROWS_PER_POST:
                        continue
                    stores.add(sk)
                    chunk.append((k, i))
                if not chunk:
                    break
                text = compose(g, [i for _, i in chunk], site)
                try:
                    _send(webhook, text)
                except Exception as e:
                    log(f"新着のお知らせ: 送信失敗 {e}")
                    break
                for k, i in chunk:
                    keys.add(k)
                    sigs[_sig(i)] = t.isoformat(timespec="minutes")
                sent += 1
                li = [x for x in li if x not in chunk]
        log(f"新着のお知らせ: {sent} 件送信")

    # 古い記録は捨てる（サイトから消えた抽選・7日より前のもの）
    old = (t - timedelta(days=KEEP_DAYS)).isoformat()
    st["keys"] = sorted(k for k in keys if k in lots and k in open_items)
    st["sigs"] = {k: v for k, v in sigs.items() if v >= old[:16]}
    save_json("notify.json", st)
    return sent


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        run()
    except Exception as e:
        log(f"新着のお知らせ: スキップ {e}")
