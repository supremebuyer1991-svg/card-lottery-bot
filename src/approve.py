"""承認：自動承認 or GitHub Issue での手動承認
手動モードでは新着ごとにIssueが立つ → スマホのGitHubアプリで
  ラベル「approved」を付ける = 投稿OK / ラベルなしでClose = 却下
"""
import os

import requests

from common import load_json, save_json, parse_dt, now, log

GH = "https://api.github.com"



def _post_date(url):
    """XのポストのURLから投稿日時を出す（ポストIDに日時が入っている）"""
    import re
    from datetime import datetime, timezone
    m = re.search(r"(?:x|twitter)\.com/[^/]+/status/(\d{15,})", url or "")
    if not m:
        return None
    return datetime.fromtimestamp(((int(m.group(1)) >> 22) + 1288834974657) / 1000, timezone.utc)

def _gh(method, path, **kw):
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return None
    r = requests.request(method, f"{GH}/repos/{repo}{path}", timeout=30, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()
    return r.json()


def _issue_body(it):
    return "\n".join([
        f"- ゲーム: {it['game']}", f"- 店舗: {it['store']}", f"- 商品: {it['product']}",
        f"- 受付: {it.get('start')} 〜 {it.get('end')}", f"- 当選発表: {it.get('announce')}",
        f"- 方法: {it.get('method')}", f"- 条件: {it.get('conditions')}",
        f"- URL: {it.get('url')}", f"- 出典: {it.get('source')} {it.get('source_url')}",
        f"- AI自信度: {it.get('confidence')}", "",
        "投稿OKならラベル `approved` を付けてください。不要ならそのままCloseで却下。",
        f"<!-- key:{it['key']} -->"])


def approve(settings):
    lots = load_json("lotteries.json", {})
    minc = settings.get("min_confidence", 0.7)

    for it in lots.values():
        if it["status"] != "new":
            continue
        ok = float(it.get("confidence") or 0) >= minc and it.get("end")
        if settings["auto_approve"] and ok:
            it["status"] = "approved"
            continue
        # 手動承認（自動モードでも自信度不足・締切不明はここに回す）
        it["status"] = "pending"
        try:
            res = _gh("POST", "/issues", json={
                "title": f"[抽選候補] {it['store']} / {it['product']}",
                "body": _issue_body(it), "labels": ["candidate", it["game"]]})
            if res:
                it["issue"] = res["number"]
        except Exception as e:
            log(f"Issue作成失敗: {e}")

    # Issueの状態を反映
    for it in lots.values():
        if it["status"] != "pending" or not it.get("issue"):
            continue
        try:
            iss = _gh("GET", f"/issues/{it['issue']}")
        except Exception as e:
            log(f"Issue取得失敗: {e}")
            continue
        if not iss:
            continue
        labels = {l["name"] for l in iss.get("labels", [])}
        if "approved" in labels:
            it["status"] = "approved"
        elif iss.get("state") == "closed":
            it["status"] = "rejected"

    # 締切が過ぎたものは終了に。締切が書かれていないものは、見つけてから一定日数で終了に
    no_end_days = settings.get("no_end_expire_days", 10)
    post_days = settings.get("no_end_post_days", 21)
    manual = [u for u in (settings.get("closed_urls") or []) if u]
    for it in lots.values():
        if it["status"] not in ("new", "pending", "approved", "posted", "listed"):
            continue
        end, found = parse_dt(it.get("end")), parse_dt(it.get("found_at"))
        too_old = not end and found and (now() - found).days >= no_end_days
        # Xの告知は投稿日が分かる。情報元が古い告知を載せたままでも、投稿から post_days 日で締切不明なら終了扱い
        posted = _post_date(it.get("url"))
        old_post = not end and posted and (now() - posted).days >= post_days
        hand = any(u in (it.get("url") or "") or u in (it.get("apply_url") or "") for u in manual)
        if (end and end < now()) or too_old or old_post or hand:
            it["status"] = "closed" if it["status"] in ("posted", "listed") else "expired"
            it["closed_at"] = now().isoformat()
            if hand:
                it["closed_reason"] = "手動で終了"
            elif too_old:
                it["closed_reason"] = f"締切不明のまま{no_end_days}日経過"
            elif old_post:
                it["closed_reason"] = f"告知の投稿から{post_days}日以上たって締切不明"

    # 終了したものは一定日数たったらデータから削除（ファイルが大きくなり続けないように）
    purge_days = settings.get("purge_closed_days", 30)
    for k in [k for k, it in lots.items() if it["status"] in ("closed", "expired", "rejected", "duplicate")]:
        it = lots[k]
        t = parse_dt(it.get("closed_at")) or parse_dt(it.get("end")) or parse_dt(it.get("found_at"))
        if t and (now() - t).days >= purge_days:
            del lots[k]
    save_json("lotteries.json", lots)
