"""Threads の自分の投稿の数字（表示回数・いいね・返信など）を集めて state/threads_stats.json に保存する
（threads_manage_insights の許可が無いトークンだと数字は取れず、エラー内容だけ残す）"""
import json
import requests
from common import load_json, save_json, log, now
from threads import API, _token

FIELDS = "views,likes,replies,reposts,quotes,shares"


def main(limit=60):
    tok = _token(load_json("threads_meta.json", {}))
    out = {"at": now().isoformat(), "posts": [], "errors": []}
    r = requests.get(f"{API}/me/threads", params={"fields": "id,text,timestamp,permalink,is_reply", "limit": limit,
                                                  "access_token": tok}, timeout=30)
    if not r.ok:
        out["errors"].append(f"list {r.status_code} {r.text[:300]}")
        save_json("threads_stats.json", out)
        return
    for p in r.json().get("data", []):
        row = {"id": p["id"], "t": p.get("timestamp"), "text": (p.get("text") or "")[:80], "url": p.get("permalink")}
        q = requests.get(f"{API}/{p['id']}/insights", params={"metric": FIELDS, "access_token": tok}, timeout=30)
        if q.ok:
            for m in q.json().get("data", []):
                v = m.get("values") or [{}]
                row[m["name"]] = (m.get("total_value") or {}).get("value", v[0].get("value"))
        elif len(out["errors"]) < 3:
            out["errors"].append(f"insights {q.status_code} {q.text[:300]}")
        out["posts"].append(row)
    u = requests.get(f"{API}/me/threads_insights", params={"metric": "views,likes,replies,followers_count",
                                                            "access_token": tok}, timeout=30)
    out["account"] = u.json() if u.ok else f"{u.status_code} {u.text[:300]}"
    save_json("threads_stats.json", out)
    log(f"Threads: {len(out['posts'])}件の数字を保存（エラー{len(out['errors'])}）")


if __name__ == "__main__":
    main()
