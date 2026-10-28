"""拾い漏れチェック（1日1回・夜）：Xを追加で読まずに、手元のデータだけで調べる

A. 取り込み漏れ：カード抽選まとめ（cardchusen）の一覧に今も載っている抽選が、こっちのサイトに出ていない
   （まとめ間違い・終了扱い・却下など）。出ていない理由も書く
B. 遅れ：お店のXのポストから、こっちが拾うまで3時間以上かかった抽選（直近24時間に見つかった分）
C. Xで拾えずに、まとめサイトや手動で初めて見つかった抽選（＝Xの検索の漏れ）。お店のポストのURLつき

結果は state/gapcheck.json に残し、気になる点があれば GitHub の Issue で知らせる
"""
from datetime import datetime, timedelta, timezone

from common import load_json, save_json, parse_dt, now, log

ACTIVE = ("new", "pending", "approved", "posted", "listed")
LATE_HOURS = 3


def _post_time(url):
    import re
    m = re.search(r"(?:x|twitter)\.com/[^/]+/status/(\d{15,})", url or "")
    if not m:
        return None
    return datetime.fromtimestamp(((int(m.group(1)) >> 22) + 1288834974657) / 1000, timezone.utc)


def _final(lots, k):
    """まとめ先をたどって、最後にサイトに出ている（はずの）抽選"""
    seen = set()
    it = lots.get(k)
    while it and it.get("status") == "duplicate" and it.get("duplicate_of") and it["duplicate_of"] not in seen:
        seen.add(it["duplicate_of"])
        it = lots.get(it["duplicate_of"])
    return it


def _kind(src):
    s = str(src or "")
    if s.startswith("X"):
        return "x"
    if s.startswith("手動"):
        return "manual"
    return "site"


def check(settings, force=False):
    t = now()
    meta = load_json("gapcheck.json", {})
    today = t.date().isoformat()
    if not force and (t.hour < settings.get("gapcheck_hour", 21) or meta.get("checked") == today):
        return None
    lots = load_json("lotteries.json", {})
    live = load_json("cc_live.json", {})

    # A. 取り込み漏れ
    missing = []
    for name, keys in live.items():
        for k in keys:
            it = lots.get(k)
            if not it:
                continue  # まだ取り込む前（次の回で入る）
            end = parse_dt(it.get("end"))
            if end and end < t:
                continue
            f = _final(lots, k)
            if (not end and "締切不明" in ((f or it).get("closed_reason") or "")) or (f or it).get("closed_reason") == "手動で終了":
                continue  # 締切が書かれていない古い告知は、こっちで終了にしている（まとめサイトに残っていても出さない）
            if f and f.get("status") in ACTIVE and not (parse_dt(f.get("end")) and parse_dt(f["end"]) < t):
                continue
            missing.append({"store": it.get("store"), "product": (it.get("product") or "")[:60], "end": it.get("end"),
                            "status": (f or it).get("status"), "reason": (f or it).get("closed_reason") or "",
                            "merged_into": (f or {}).get("store") if f is not it else None, "url": it.get("url")})

    # 同じ抽選のまとまり（残っている1件＋まとめられた分）
    groups = {}
    for k, it in lots.items():
        f = _final(lots, k)
        if f and f.get("status") in ACTIVE:
            groups.setdefault(f["key"], []).append(it)
    late, x_missed = [], []
    since = t - timedelta(hours=24)
    for key, its in groups.items():
        found = sorted((parse_dt(i.get("found_at")), i) for i in its if parse_dt(i.get("found_at")))
        if not found or found[0][0] < since:
            continue  # 直近24時間に初めて見つかった抽選だけ
        first_t, first = found[0]
        posts = [(p, i.get("x_post")) for i in its for p in [_post_time(i.get("x_post"))] if p]
        posted, post_url = min(posts) if posts else (None, None)
        top = lots[key]
        row = {"store": top.get("store"), "product": (top.get("product") or "")[:60], "end": top.get("end"),
               "first_source": first.get("source"), "found_at": first_t.isoformat(), "post": post_url,
               "posted_at": posted.astimezone(t.tzinfo).isoformat() if posted else None}
        if posted and (first_t - posted).total_seconds() > LATE_HOURS * 3600:
            row["hours_late"] = round((first_t - posted).total_seconds() / 3600, 1)
            late.append(row)
        if _kind(first.get("source")) != "x" and post_url:
            x_missed.append(row)  # お店はXでポストしていたのに、Xの検索では最初に拾えなかった
    late.sort(key=lambda r: -r["hours_late"])
    x_missed.sort(key=lambda r: r["found_at"])
    report = {"date": today, "checked_at": t.isoformat(), "missing": missing, "late": late, "x_missed": x_missed,
              "new_total": sum(1 for its in groups.values()
                               if min((parse_dt(i.get("found_at")) for i in its if parse_dt(i.get("found_at"))), default=t) >= since)}
    meta.update(checked=today, last=report)
    hist = meta.setdefault("history", {})
    hist[today] = {"new": report["new_total"], "missing": len(missing), "late": len(late), "x_missed": len(x_missed)}
    meta["history"] = dict(sorted(hist.items())[-30:])
    save_json("gapcheck.json", meta)
    log(f"拾い漏れチェック: 新しい抽選{report['new_total']}件／取り込み漏れ{len(missing)}件・遅れ{len(late)}件・Xで拾えなかった{len(x_missed)}件")
    if missing or late or x_missed:
        _issue(report)
    return report


def _fmt_dt(s):
    d = parse_dt(s)
    return f"{d.month}/{d.day} {d:%H:%M}" if d else "締切不明"


def _issue(r):
    lines = [f"今日（{r['date']}）見つかった新しい抽選は {r['new_total']} 件でした。気になる点だけまとめています。", ""]
    if r["missing"]:
        lines += [f"## A. まとめサイトに載っているのに、サイトに出ていない抽選（{len(r['missing'])}件）",
                  "まとめ間違い・終了扱いなどで消えている可能性があります。"]
        lines += [f"- {m['store']}｜{m['product']}｜締切 {_fmt_dt(m['end'])}｜状態: {m['status']} {m['reason']}"
                  + (f"（{m['merged_into']} にまとめられている）" if m.get("merged_into") else "") for m in r["missing"][:20]]
        lines.append("")
    if r["late"]:
        lines += [f"## B. お店のポストから拾うまで{LATE_HOURS}時間以上かかった抽選（{len(r['late'])}件）"]
        lines += [f"- {x['store']}｜{x['product']}｜{x['hours_late']}時間おくれ（最初に拾った所: {x['first_source']}）｜{x['post']}"
                  for x in r["late"][:20]]
        lines.append("")
    if r["x_missed"]:
        lines += [f"## C. お店はXでポストしていたのに、Xの検索では拾えなかった抽選（{len(r['x_missed'])}件）",
                  "Xの検索の言葉を見直すヒントです（まとめサイトや手動で拾えています）。"]
        lines += [f"- {x['store']}｜{x['product']}｜最初に拾った所: {x['first_source']}｜{x['post']}" for x in r["x_missed"][:20]]
        lines.append("")
    lines.append("Claudeに「拾い漏れチェックのIssue見て直して」と言えば、原因を調べて直します。確認したらこのIssueは閉じてください。")
    try:
        from approve import _gh
        _gh("POST", "/issues", json={
            "title": f"【拾い漏れチェック】{r['date'][5:].replace('-', '/')}：取り込み漏れ{len(r['missing'])}件・遅れ{len(r['late'])}件・X漏れ{len(r['x_missed'])}件",
            "body": "\n".join(lines)})
    except Exception as e:
        log(f"拾い漏れチェックのIssue作成失敗: {e}")
