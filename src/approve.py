"""承認：自動承認 or GitHub Issue での手動承認
手動モードでは新着ごとにIssueが立つ → スマホのGitHubアプリで
  ラベル「approved」を付ける = 投稿OK / ラベルなしでClose = 却下
"""
import os

import requests

from common import load_json, save_json, parse_dt, now, log

GH = "https://api.github.com"




def _vague_store(store):
    """店名として足りないもの：「不明」「未記載」入り、または2文字の地名だけ"""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKC", store or "").strip()
    if not s or re.search(r"不明|未記載|未定", s):
        return True
    core = re.sub(r"[（(].*?[）)]|\s", "", s)
    return len(core) <= 2 and not re.search(r"[A-Za-z]", core)  # 「岡南」「熱田」など（3文字以上は「平和堂」などのチェーン名がある）

def _blog_link(url, store, blogs, pages, limit=8):
    """まとめブログのページから、そのお店の公式リンクを探す（1回の実行で読むページは limit まで）"""
    try:
        if url not in pages:
            if len(pages) >= limit:
                return None
            from fetch import get
            pages[url] = get(url)
        from bloglink import find_link
        return find_link(pages[url], url, store, blogs)
    except Exception as e:
        log(f"まとめブログの読み取り失敗 {url}: {e}")
        pages[url] = ""
        return None


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
        # 店名があいまい（「岡南」「熱田」「北海道（店舗名不明）」など、Xの告知で地名だけのもの）は載せない
        if it["status"] in ("new", "approved", "listed") and _vague_store(it.get("store")):
            it["status"] = "pending"
            it["hold_reason"] = "店名があいまい"
            continue
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
    import re
    blogs = [b.lower() for b in (settings.get("blog_domains") or [])]
    pages = {}  # まとめブログのページ（1回の実行で同じページは1回だけ読む）
    # 応募先が情報元の一覧ページそのもの（個別の告知ではない）＝AIがあいまいに作った抽選なので載せない
    try:
        from common import load_sources
        index_urls = {s_["url"].rstrip("/") for s_ in load_sources() if s_.get("url") and s_.get("type") != "rss"}
    except Exception:
        index_urls = set()
    own = re.compile(r"(x|twitter)\.com/pokepi_tcg/", re.I)  # 自分のアカウント
    for it in lots.values():
        if own.search(it.get("x_post") or ""):
            it["x_post"] = None  # 自分のポストは「お店の告知」ではない
        if it.get("closed_reason") == "自分のポストから拾ったもの" and (it.get("manual") or not own.search(it.get("url") or "")):
            it["status"], it["closed_reason"] = ("listed" if it.get("manual") else "approved"), None  # 前の判定のまちがいを戻す
    for it in lots.values():
        if it["status"] not in ("new", "pending", "approved", "posted", "listed"):
            continue
        end, found = parse_dt(it.get("end")), parse_dt(it.get("found_at"))
        too_old = not end and found and (now() - found).days >= no_end_days
        # Xの告知は投稿日が分かる。情報元が古い告知を載せたままでも、投稿から post_days 日で締切不明なら終了扱い
        posted = _post_date(it.get("url"))
        old_post = not end and posted and (now() - posted).days >= post_days
        hand = any(u in (it.get("url") or "") or u in (it.get("apply_url") or "") for u in manual)
        if own.search(it.get("url") or "") and not it.get("manual"):
            it["status"] = "rejected"  # 自分のアカウントのポストから拾ったもの（元の抽選は別に載っている）
            it["closed_reason"] = "自分のポストから拾ったもの"
            continue
        # Xの短縮リンク（t.co）は行き先のアドレスに置きかえる（どこに飛ぶか分かるように）
        if re.match(r"https?://t\.co/", it.get("url") or "") and not it.get("tco_checked"):
            it["tco_checked"] = True
            try:
                import requests
                r = requests.head(it["url"], allow_redirects=False, timeout=10)
                loc = r.headers.get("location") or ""
                if loc.startswith("http") and "t.co/" not in loc:
                    it["url"] = loc
            except Exception as e:
                log(f"短縮リンクの確認失敗 {it['url']}: {e}")
        # 応募先がまとめブログ（お店・公式ではない）なら、リンクを外す（ブログは情報元としてだけ残す）
        if it.get("blog_url") and not it.get("url"):  # リストから外したブログはリンクを戻す
            bh = re.sub(r"^https?://(www\.)?", "", it["blog_url"]).split("/")[0].lower()
            if not any(bh == b or bh.endswith("." + b) for b in blogs):
                it["url"] = it.pop("blog_url")
        host = re.sub(r"^https?://(www\.)?", "", it.get("url") or "").split("/")[0].lower()
        if host and any(host == b or host.endswith("." + b) for b in blogs):
            it["blog_url"] = it["url"]
            it["url"] = it.get("apply_url") or None
            log(f"応募先がまとめブログのためリンクを外しました: {it.get('store')} {host}")
        if it.get("blog_url") and it.get("url") and it["url"] != it["blog_url"]:  # ブログから拾ったリンクが今のルールで使えないなら外す
            from bloglink import _ok
            bh = re.sub(r"^https?://(www\.)?", "", it["blog_url"]).split("/")[0].lower()
            if any(bh == b or bh.endswith("." + b) for b in blogs) and not _ok(it["url"], bh, blogs):
                it["url"] = None
                it.pop("blog_checked", None)
        # まとめブログのページに貼ってある、そのお店の公式の応募ページ（かお店の告知ポスト）を探してリンクにする（1日1回まで）
        if it.get("blog_url") and not it.get("url") and it.get("blog_checked") != now().date().isoformat():
            it["blog_checked"] = now().date().isoformat()
            found = _blog_link(it["blog_url"], it.get("store"), blogs, pages)
            if found:
                it["url"] = found
                log(f"まとめブログから公式のリンクを見つけました: {it.get('store')} → {found}")
        if (it.get("url") or "").rstrip("/") in index_urls and not it.get("apply_url"):
            it["status"] = "rejected"
            it["closed_reason"] = "応募先が情報元の一覧ページ（個別の抽選ではない）"
            continue
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
