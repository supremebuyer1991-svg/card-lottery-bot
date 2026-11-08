"""ゲーム・ホビー入荷速報：Xの予約投稿の計画（明日の分）

急がない新着（game_xpost が state/game/xpost.json の queue に入れたもの）と、締切・発売日の情報から、
翌日の決まった時刻の投稿文を作り、site_game/x-plan.json と /x-plan.html（検索には出さない）に書き出す。
予約投稿は無料なのでリンクを付ける（アフィリエイトのページがあれば PR 表記つきでそれ、なければサイトの個別ページ）。
このアカウントはゲームが本業なので、ゲーム（ゲーム機・ゲーム関連の限定品）を優先し、ホビーはまとめの中の一部にとどめる。

時刻（11/8 Fable の調査より）：7:30 今日の締切／10:30 ピックアップ／12:30 新着まとめ／17:00 ピックアップ／20:30 今夜締切／日曜21:00 来週の発売
"""
import json
import re
from datetime import timedelta
from html import escape

from common import load_json, save_json, now, parse_dt, log

WEEK = "月火水木金土日"


def _md(dt, time=True):
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]})" + (f" {dt:%H:%M}" if time else "")


def _short(s, n):
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").strip()
    s = re.sub(r"[（(][^）)]{12,}[）)]", "", s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _xlen(text):
    import unicodedata
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


def _fit(lines):
    while _xlen("\n".join(lines)) > 280 and len(lines) > 3:
        lines.pop(-3)
    return "\n".join(lines)


def build(lots, settings, site, t=None, st=None):
    """翌日（t の次の日）の投稿の計画。[{"at": ISO, "slot": 名前, "text": 本文}]。st は xpost.json（queue / planned を使う・書き換える）"""
    import game_xpost as gx
    import detail
    t = t or now()
    st = st if st is not None else {}
    day = (t + timedelta(days=1)).date()
    dkey = day.isoformat()
    tz = t.tzinfo

    def at(h, m):
        from datetime import datetime
        return datetime(day.year, day.month, day.day, h, m, tzinfo=tz)

    def link(it):
        try:
            import game_affi
            lk = game_affi.links_for(it, load_json(game_affi.CACHE, {}), settings)
            u = lk.get("az") or (lk.get("rk") or {}).get("u")
            if u:
                return u, True
        except Exception:
            pass
        return f"{site}/{detail.lottery_path(dict(it, key=it.get('key') or ''))}", False

    def tag(items):
        return gx._tags(items)

    live = {k: dict(i, key=i.get("key") or k) for k, i in lots.items() if i.get("status") in ("approved", "listed", "posted")}
    gfirst = lambda kv: (not gx.is_game(kv[1]), kv[1].get("end") or "9999")   # noqa: E731
    # 待ち行列 → この日に割り当て（前の日に割り当てたものは使わない。この日の分は作り直しても同じ）
    planned = st.setdefault("planned", {})
    queue = st.get("queue", {})
    mine = [k for k, d in planned.items() if d == dkey and k in live]
    for k in sorted([k for k in queue if k in live and k not in planned],
                    key=lambda k: (not gx.is_game(live[k]), queue[k])):
        if len(mine) >= 6:
            break
        planned[k] = dkey
        mine.append(k)
    picks = sorted([(k, live[k]) for k in mine], key=gfirst)
    # 新着が少ない日は、受付中・まもなく発売のゲームから選んで埋める（同じものは3日あけて）
    feat = st.setdefault("featured", {})
    if len([kv for kv in picks if gx.is_game(kv[1])]) < 2:
        def soon(i):
            e = parse_dt(i.get("end"))
            return e and day <= e.date() <= day + timedelta(days=10)
        pool = sorted([(k, i) for k, i in live.items() if gx.is_game(i) and k not in mine and soon(i)
                       and (feat.get(k, "") < (day - timedelta(days=3)).isoformat() or feat.get(k) == dkey)],
                      key=lambda kv: (feat.get(kv[0]) != dkey, kv[1].get("kind") == "release", kv[1].get("end") or "9999"))
        for k, i in pool[:2 - len([kv for kv in picks if gx.is_game(kv[1])])]:
            feat[k] = dkey
            picks.insert(0, (k, i))
    game_picks = [kv for kv in picks if gx.is_game(kv[1])]
    plan = []

    # 7:30 今日の締切
    ends = sorted([(k, i) for k, i in live.items() if i.get("kind") != "release" and parse_dt(i.get("end"))
                   and parse_dt(i["end"]).date() == day], key=gfirst)
    if ends:
        lines = [f"🔔おはよ、リンリンだよ！ 今日{_md(at(0, 0), False)}締切は{len(ends)}件", ""]
        lines += [f"▶{_short(i.get('product'), 26)}（{i.get('store') or '公式'}・{parse_dt(i['end']):%H:%M}まで）" for _, i in ends[:5]]
        lines += ["", "まだの人は忘れずにね👇", f"{site}/now/", tag([i for _, i in ends[:2]])]
        plan.append({"at": at(7, 30), "slot": "今日の締切", "text": _fit(lines)})

    def single(kv, h, m, label):
        k, it = kv
        u, aff = link(it)
        lines = [f"🔔{label}", "", f"【{it.get('store') or '公式'}】{_short(it.get('product'), 60)}",
                 f"▶{gx._kind(it)}"]
        stt, en = parse_dt(it.get("start")), parse_dt(it.get("end"))
        if stt and stt > at(h, m):
            lines.append(f"▶受付開始 {_md(stt)}")
        if en and it.get("kind") != "release":
            lines.append(f"▶締切 {_md(en)}")
        elif en:
            lines.append(f"▶発売日 {_md(en, False)}")
        if it.get("price"):
            lines.append(f"▶定価 {str(it['price']).replace('（税込）', '')}")
        lines += ["", (f"{'Amazon' if 'amazon.' in u else '楽天'}の商品ページ👉 {u}" if aff else f"くわしくはこちら👉 {u}"), tag([it])]
        plan.append({"at": at(h, m), "slot": "ピックアップ", "text": _fit(lines)})

    # 10:30・17:00 ピックアップ（ゲームを優先。ゲームが無ければホビーも）
    singles = (game_picks or picks)[:2]
    for kv, (h, m), label in zip(singles, [(10, 30), (17, 0)], ["今日のピックアップ！", "夕方のピックアップ！"]):
        single(kv, h, m, label)
    # 12:30 新着まとめ（ピックアップで出していない分。ホビーは2件まで）
    rest = [kv for kv in picks if kv not in singles]
    rest = [kv for kv in rest if gx.is_game(kv[1])][:4] + [kv for kv in rest if not gx.is_game(kv[1])][:2]
    if rest:
        lines = [f"🔔新着まとめ{len(rest)}件だよ！", ""]
        for _, i in rest:
            en = parse_dt(i.get("end"))
            lines.append(f"▶{_short(i.get('product'), 26)}（{i.get('store') or '公式'}・{gx._kind(i)}{'・〜' + _md(en) if en and i.get('kind') != 'release' else ''}）")
        lines += ["", "一覧はこちら👇", f"{site}/", tag([i for _, i in rest[:2]])]
        plan.append({"at": at(12, 30), "slot": "新着まとめ", "text": _fit(lines)})
    # 20:30 今夜締切
    tonight = [kv for kv in ends if parse_dt(kv[1]["end"]) >= at(20, 45)]
    if tonight:
        lines = ["🔔今夜締切、まだの人いる？", ""]
        lines += [f"▶{_short(i.get('product'), 26)}（{i.get('store') or '公式'}・{parse_dt(i['end']):%H:%M}まで）" for _, i in tonight[:5]]
        lines += ["", "応募したらリプで教えてね🔔", f"{site}/now/", tag([i for _, i in tonight[:2]])]
        plan.append({"at": at(20, 30), "slot": "今夜締切", "text": _fit(lines)})
    # 日曜 21:00 来週の発売（ゲームを先に）
    if day.weekday() == 6:
        wk = sorted([(k, i) for k, i in live.items() if i.get("kind") == "release" and parse_dt(i.get("end"))
                     and day < parse_dt(i["end"]).date() <= day + timedelta(days=7)], key=lambda kv: kv[1]["end"])
        wk = [kv for kv in wk if gx.is_game(kv[1])] + [kv for kv in wk if not gx.is_game(kv[1])][:2]
        if wk:
            lines = ["📅来週の発売日だよ！ 保存してね🔔", ""]
            lines += [f"▶{_md(parse_dt(i['end']), False)} {_short(i.get('product'), 30)}" for _, i in sorted(wk, key=lambda kv: kv[1]["end"])[:6]]
            lines += ["", f"{site}/calendar/", tag([i for _, i in wk[:2]])]
            plan.append({"at": at(21, 0), "slot": "来週の発売", "text": _fit(lines)})
    plan.sort(key=lambda p: p["at"])
    # 古い割り当て・待ち行列の掃除（2日より前の日の分）
    for k in [k for k, d in planned.items() if d < (t.date() - timedelta(days=2)).isoformat()]:
        planned.pop(k, None)
        queue.pop(k, None)
    return [dict(p, at=p["at"].isoformat()) for p in plan]


def write(out, settings, site):
    """site_game/x-plan.json と x-plan.html を書く（明日の分）"""
    import game_xpost as gx
    st = load_json(gx.STATE, {})
    if "seen" not in st:
        return []
    plan = build(load_json("lotteries.json", {}), settings, site, st=st)
    save_json(gx.STATE, st)
    data = {"for": (now() + timedelta(days=1)).date().isoformat(), "updated": now().isoformat(), "posts": plan}
    (out / "x-plan.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = "".join(f'<div class="d"><b>{escape(p["at"][11:16])} {escape(p["slot"])}</b><textarea>{escape(p["text"])}</textarea></div>' for p in plan)
    (out / "x-plan.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><title>Xの予約投稿の計画</title><style>body{font-family:system-ui;max-width:760px;margin:0 auto;padding:16px}'
        'textarea{width:100%;min-height:170px;font:14px/1.5 system-ui}.d{margin:12px 0}</style></head><body>'
        f'<h1>Xの予約投稿（{escape(data["for"])}）</h1><p>更新 {escape(data["updated"][:16])}</p>{rows or "<p>予定なし</p>"}</body></html>', encoding="utf-8")
    log(f"Xの予約投稿の計画：{data['for']} の {len(plan)}本")
    return plan
