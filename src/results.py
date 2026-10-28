"""抽選結果（当選発表）の情報を拾う

・新しくXを読むことはしない。抽選を探すために読んだポスト（collect.py）の中から、
  「抽選結果を発表しました」「当選者の方へメールを送りました」のようなお店・公式の発表だけを選ぶ
・どの抽選の結果かは、ポストしたアカウント・お店の名前・弾の名前で今の抽選と照らし合わせる
・state/results.json に残す（30日分）。サイトの /kekka/ と results.json に出し、Xの予約作業が読む
"""
import re
from datetime import timedelta

from common import load_json, save_json, now, normalize, parse_dt, log

KEEP_DAYS = 30

# 結果の発表らしい言葉
HIT = re.compile(r"(抽選結果|当選者|当選された|当選のお客様|当選番号|当選発表|当選メール|当選連絡|当選のご連絡|当選の方|当選者様|当選者さま)")
# 「発表した・送った」など、もう出たことを表す言葉
DONE = re.compile(r"(しました|いたしました|致しました|しております|お送り|送信|ご連絡|掲載|公開|発表です|発表中|出ました|きました|来ました|届い|確認できます|ご確認ください|下記|以下|こちら)")
# 抽選の受付の告知（結果ではない）・個人の当選報告
NOT = re.compile(r"(予定|後日|受付期間|応募期間|受付中|応募方法|応募受付|応募はこちら|当選報告|当たった|当たりました|当選しました[!！]|外れ|落選しました|ハズレ)")
GAME_WORDS = {"pokemon": re.compile(r"(ポケカ|ポケモンカード|ポケモンセンター|ポケセン|MEGA|ハドウシーカー|30th)"),
              "onepiece": re.compile(r"(ワンピ|ONE ?PIECE|ヒロインズ|神の支配)", re.I)}


def is_result(body: str) -> bool:
    return bool(HIT.search(body) and DONE.search(body) and not NOT.search(body))


def _parse(text):
    """fetch_x.search の文（投稿者・日時・本文・リンク・ポストURL）を分ける"""
    m = re.match(r"投稿者: (.*?) \(@(\w+)\)\n日時: (.*?)\n(.*)\nリンク: (.*)\nポストURL: (\S+)", text, re.S)
    if not m:
        return None
    name, handle, at, body, links, url = m.groups()
    return {"author": name, "handle": handle, "at": at, "body": body.strip(),
            "links": [x for x in links.split() if x.startswith("http")], "post": url}


def _handle(u):
    m = re.search(r"x\.com/(\w+)/status/", u or "") or re.search(r"twitter\.com/(\w+)/status/", u or "")
    return m.group(1).lower() if m else None


def _is_store(author, store):
    """ポストしたアカウントの名前に、お店（またはチェーン）の名前が入っているか。
    抽選の告知を個人が紹介したポストもあるので、アカウントが一致するだけでは「お店本人」と決めない"""
    a = normalize(author or "").replace(" ", "")
    core = normalize(re.sub(r"[（(][^）)]*[）)]", "", store or "")).replace(" ", "")
    names = {core} | {w for w in re.split(r"[・/]", core) if len(w) >= 3}
    try:
        from sitegen import chain_of, CHAIN
        c = chain_of(store)
        if c:
            names.add(normalize(CHAIN[c][1]).replace(" ", ""))
    except Exception:
        pass
    return any(len(n) >= 3 and n in a for n in names)


def _match(p, game, lots):
    """どの抽選の結果か。締切が過ぎた（か近い）抽選から、アカウント → お店の名前 の順で探す"""
    t = now()
    cand = []
    for it in lots.values():
        if it.get("status") in ("duplicate", "rejected") or not it.get("store"):
            continue
        if game and it.get("game") != game:
            continue
        end = parse_dt(it.get("end"))
        if not end or not (t - timedelta(days=21) <= end <= t + timedelta(days=1)):
            continue
        cand.append(it)
    # お店本人のアカウント（その抽選を告知したアカウント）のポストだけを使う。
    # 個人の当選報告や、ほかのまとめアカウントのポストを「結果発表」として載せない
    h = p["handle"].lower()
    hit = [i for i in cand if _handle(i.get("x_post")) == h and _is_store(p["author"], i["store"])]
    if not hit:
        return []
    # 弾の名前がポストに出ていればそれに絞る
    ser = [i for i in hit if i.get("series") and normalize(i["series"]) in normalize(p["body"])]
    return ser or hit


def scan(posts, src, lots=None):
    """collect.py で読んだXのポストから結果の発表を拾って results.json に足す。足した数を返す"""
    data = load_json("results.json", {})
    lots = lots if lots is not None else load_json("lotteries.json", {})
    added = 0
    for text, _ in posts:
        p = _parse(text)
        if not p or p["post"] in data or not is_result(p["body"]):
            continue
        if src.get("id") == "x_info_accounts":
            continue  # まとめ・情報アカウントのポストは使わない
        game = src.get("game")
        if game not in GAME_WORDS:
            game = next((g for g, rx in GAME_WORDS.items() if rx.search(p["body"])), None)
        if not game:
            continue  # ポケカ・ワンピースカードのどちらの話か分からないものは使わない
        m = _match(p, game, lots)
        if not m:
            continue  # どのお店の抽選か（お店本人のポストか）分からないものは使わない
        stores = sorted({i["store"] for i in m})
        series = sorted({i["series"] for i in m if i.get("series")})
        data[p["post"]] = {"game": game, "found_at": now().isoformat(), "posted_at": p["at"],
                           "author": p["author"], "handle": p["handle"],
                           "store": stores[0] if len(stores) == 1 else "・".join(stores[:3]),
                           "series": series[:3], "lottery_keys": [i["key"] for i in m][:10],
                           "matched": bool(m), "text": re.sub(r"https?://\S+", "", p["body"])[:140].strip(),
                           "links": p["links"][:2], "source": src.get("id")}
        added += 1
        log(f"抽選結果: {data[p['post']]['store']} の発表を見つけました {p['post']}")
    if added:
        cut = (now() - timedelta(days=KEEP_DAYS)).isoformat()
        data = {k: v for k, v in data.items() if v.get("found_at", "") >= cut}
        save_json("results.json", data)
    return added


def scheduled_today(lots=None):
    """今日が「当選発表日」になっている抽選（お店の告知に書いてあった発表日）"""
    lots = lots if lots is not None else load_json("lotteries.json", {})
    today = now().date().isoformat()
    out = {}
    for it in lots.values():
        if it.get("status") in ("duplicate", "rejected") or str(it.get("announce") or "")[:10] != today:
            continue
        k = (it["game"], normalize(it.get("store")))
        out.setdefault(k, {"game": it["game"], "store": it.get("store"), "series": set()})
        if it.get("series"):
            try:
                from sitegen import canon_series  # サイトと同じ弾名に（「EB-05」→「ヒロインズエディション vol.2」など）
                out[k]["series"].update(canon_series(it["game"], it["series"]) or [it["series"]])
            except Exception:
                out[k]["series"].add(it["series"])
    return [dict(v, series=sorted(v["series"])) for v in out.values()]


def clean(lots=None):
    """前の決まりで入った、お店本人以外のポスト（個人・まとめアカウント）を消す"""
    data = load_json("results.json", {})
    lots = lots if lots is not None else load_json("lotteries.json", {})
    own = {_handle(i.get("x_post")) for i in lots.values() if i.get("x_post")}
    keep = {k: v for k, v in data.items() if v.get("matched") and v.get("source") != "x_info_accounts"
            and (v.get("handle") or "").lower() in own and _is_store(v.get("author"), v.get("store"))}
    if len(keep) != len(data):
        save_json("results.json", keep)
        log(f"抽選結果: お店本人以外のポスト{len(data) - len(keep)}件を外しました")
    return keep
