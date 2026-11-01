"""サイトの見張り（1日2回・本体とは別の動き）：おかしい所があればGitHubのIssueで知らせる

・本体（1時間ごとの実行）が失敗し続けていないか／しばらく動いていないか
・サイトが開けるか（トップ・ポケカ・ワンピース・相場）
・新しい抽選が24時間ゼロになっていないか
・BOX相場の更新が止まっていないか
何もなければ何もしない（Issueも立てない）
"""
import os
import sys
from datetime import timedelta

import requests

sys.path.insert(0, os.path.dirname(__file__))
from common import load_json, load_settings, now, parse_dt, log  # noqa: E402

GH = "https://api.github.com"


def _gh(method, path, **kw):
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return None
    r = requests.request(method, f"{GH}/repos/{repo}{path}", timeout=30, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()
    return r.json()


def check():
    s = load_settings()
    t = now()
    problems = []
    # 1. 本体の実行
    try:
        runs = (_gh("GET", "/actions/workflows/run.yml/runs?per_page=40") or {}).get("workflow_runs") or []
        recent = [r for r in runs if parse_dt(r.get("created_at")) and t - parse_dt(r["created_at"]) < timedelta(hours=24)]
        bad = [r for r in recent if r.get("conclusion") == "failure"]
        ok = [r for r in runs if r.get("conclusion") == "success"]
        if len(bad) >= 3:
            problems.append(f"本体の実行が24時間で{len(bad)}回失敗しています（最新: {bad[0].get('html_url')}）")
        if ok:
            age = (t - parse_dt(ok[0]["updated_at"])).total_seconds() / 3600
            if 7 <= t.hour <= 24 and age > 2.7:  # 実行は最大2時間おき（run_hours）
                problems.append(f"本体が{age:.1f}時間うまく動いていません（最後に成功: {parse_dt(ok[0]['updated_at']).astimezone(t.tzinfo):%m/%d %H:%M}）")
    except Exception as e:
        log(f"見張り: 実行の確認に失敗 {e}")
    # 2. サイト
    site = (s.get("site_public_url") or "").rstrip("/")
    for path in ("/", "/pokeka/", "/onepiece/", "/souba/"):
        try:
            r = requests.get(site + path, timeout=30, headers={"User-Agent": "Mozilla/5.0 (site-health-check)"})
            if r.status_code != 200 or len(r.text) < 5000:
                problems.append(f"サイトの {path} が正しく開けません（{r.status_code}・{len(r.text)}文字）")
        except Exception as e:
            problems.append(f"サイトの {path} が開けません（{str(e)[:60]}）")
    # 3. 新しい抽選
    lots = load_json("lotteries.json", {})
    new24 = sum(1 for i in lots.values() if parse_dt(i.get("found_at")) and t - parse_dt(i["found_at"]) < timedelta(hours=24))
    if new24 == 0:
        problems.append("この24時間、新しい抽選が1件も見つかっていません（情報元の読み取りが止まっているかもしれません）")
    # 4. BOX相場
    sb = load_json("souba.json", {})
    if t.hour >= 10 and sb.get("checked") and sb["checked"] < (t - timedelta(days=1)).date().isoformat():
        problems.append(f"BOX相場の更新が止まっています（最後: {sb['checked']}）")
    log(f"見張り: 新しい抽選（24時間）{new24}件・問題{len(problems)}件")
    if problems:
        body = "サイトの見張りで気になる点が見つかりました。\n\n" + "\n".join(f"- {p}" for p in problems) + \
               "\n\nClaudeに「見張りのIssue見て直して」と言えば調べて直します。直ったらこのIssueは閉じてください。"
        try:
            _gh("POST", "/issues", json={"title": f"【見張り】{t:%m/%d %H:%M} 気になる点が{len(problems)}件", "body": body})
        except Exception as e:
            log(f"見張り: Issue作成失敗 {e}")
    return problems


if __name__ == "__main__":
    for p in check():
        print("-", p)
