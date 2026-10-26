"""WordPress 自動更新
  - ゲーム別まとめページ（固定ページ）: 例「ポケモンカード 抽選・予約情報まとめ」
  - 弾ごとの記事（投稿）: 例「〇〇 抽選・予約情報まとめ【店舗別・締切順】」← 検索流入の本命
中身が変わった時だけ更新し、アフィリンク（Amazon検索リンク等）も自動で差し込む
"""
import os
import re
from html import escape
from urllib.parse import quote

import requests

from common import load_json, save_json, now, parse_dt, sha, normalize, log
from xpost import fmt_dt

ACTIVE = ("approved", "posted", "listed")


def series_of(it):
    return (it.get("series") or "").strip()


def series_slug(game, series):
    return f"{game}-lottery-{sha(normalize(series))[:8]}"


def series_url(settings, game, series):
    return f"{settings['site_url'].rstrip('/')}/{series_slug(game, series)}/"


def _table(items, show_product=True):
    head = "<tr><th>店舗</th>" + ("<th>商品</th>" if show_product else "") + \
           "<th>締切</th><th>条件</th><th>リンク</th></tr>"

    def row(i):
        e = parse_dt(i.get("end"))
        soon = e and (e - now()).total_seconds() < 86400 and i["status"] in ACTIVE
        badge = '<strong style="color:#C8102E">締切間近</strong><br>' if soon else ""
        link = (f'<a href="{escape(i["url"])}" target="_blank" rel="noopener">応募ページ</a>'
                if i.get("url") else "")
        return ("<tr>" f"<td>{escape(i['store'])}</td>"
                + (f"<td>{escape(i['product'])}</td>" if show_product else "")
                + f"<td>{badge}{fmt_dt(i.get('end'))}</td>"
                f"<td>{escape(i.get('conditions') or '-')}</td><td>{link}</td></tr>")
    return f'<figure class="wp-block-table"><table>{head}{"".join(row(i) for i in items)}</table></figure>'


def _affiliate(game, series, settings):
    links = [a for a in settings.get("affiliate", {}).get(game, []) if a.get("url")]
    tag = os.environ.get("AMAZON_TAG") or settings.get("amazon_tag")
    if tag and series:  # 弾名でAmazon検索リンクを自動生成
        links.insert(0, {"label": f"「{series}」をAmazonで探す",
                         "url": f"https://www.amazon.co.jp/s?k={quote(series)}&tag={tag}"})
    if not links:
        return ""
    return "<h2>関連商品</h2><ul>" + "".join(
        f'<li><a href="{escape(a["url"])}" target="_blank" rel="nofollow sponsored noopener">'
        f'{escape(a["label"])}</a></li>' for a in links) + "</ul>"


PR = '<p style="font-size:12px;color:#666">※本ページはプロモーション（広告）を含みます。</p>'


def _sort(items, reverse=False):
    return sorted(items, key=lambda i: i.get("end") or "9999", reverse=reverse)


def render(game, settings, lots) -> str:
    """ゲーム別まとめページ"""
    name = settings["game_names"][game]
    items = [i for i in lots.values() if i["game"] == game]
    active = _sort([i for i in items if i["status"] in ACTIVE])
    ended = _sort([i for i in items if i["status"] == "closed"], reverse=True)[:20]

    html = [PR, f"<p>{escape(name)}の抽選・予約情報を自動で集めて掲載しています。"
            f"最終更新：{now():%Y/%m/%d %H:%M}。応募前に必ず各店舗の公式ページで条件をご確認ください。</p>"]

    # 弾ごとの記事への内部リンク
    series = sorted({series_of(i) for i in active if series_of(i)})
    if series and settings.get("site_url"):
        html.append("<h2>弾ごとの抽選まとめ</h2><ul>" + "".join(
            f'<li><a href="{series_url(settings, game, s)}">{escape(s)} の抽選・予約情報</a></li>'
            for s in series) + "</ul>")

    html.append(f"<h2>受付中の抽選（{len(active)}件）</h2>")
    html.append(_table(active) if active else
                "<p>現在受付中の抽選はありません。新しい抽選はXで最速でお知らせします。</p>")
    html.append(_affiliate(game, "", settings))
    if ended:
        html.append(f"<h2>終了した抽選</h2><details><summary>直近{len(ended)}件</summary>"
                    f"{_table(ended)}</details>")
    return "\n".join(h for h in html if h)


def render_series(game, series, settings, lots) -> str:
    """弾ごとの記事"""
    items = [i for i in lots.values() if i["game"] == game and series_of(i) == series]
    active = _sort([i for i in items if i["status"] in ACTIVE])
    ended = _sort([i for i in items if i["status"] == "closed"], reverse=True)
    soon = [i for i in active if parse_dt(i.get("end")) and
            (parse_dt(i["end"]) - now()).total_seconds() < 86400]
    name = settings["game_names"][game]
    html = [PR,
            f"<p>{escape(name)}「{escape(series)}」の抽選・予約情報を、店舗別・締切が近い順にまとめています。"
            f"新しい抽選が見つかり次第、自動で追記されます（最終更新：{now():%Y/%m/%d %H:%M}）。</p>",
            f"<h2>受付中の抽選（{len(active)}件）</h2>"]
    if soon:
        html.append(f'<p><strong style="color:#C8102E">⏰ 24時間以内に締切：'
                    f'{"、".join(escape(i["store"]) for i in soon)}</strong></p>')
    online = [i for i in active if i.get("channel") != "store"]
    shops = [i for i in active if i.get("channel") == "store"]
    html.append("<h3>ネット抽選</h3>" + _table(online, show_product=False) if online
                else "<p>現在受付中のネット抽選はありません。</p>")
    if shops:  # 実店舗は都道府県ごと（「〇〇 抽選 大阪」などの検索にも強い）
        html.append(f"<h2>実店舗の抽選（{len(shops)}件）</h2>")
        for area in sorted({i.get("area") or "地域不明" for i in shops}):
            rows = [i for i in shops if (i.get("area") or "地域不明") == area]
            html.append(f"<h3>{escape(area)}</h3>" + _table(rows, show_product=False))
    html.append(_affiliate(game, series, settings))
    if ended:
        html.append(f"<h2>受付終了した抽選（{len(ended)}件）</h2>{_table(ended)}")
    html.append("<p>※応募条件や期間は変更される場合があります。必ず各店舗の公式ページでご確認ください。</p>")
    if settings.get("site_url"):
        html.append(f'<p><a href="{settings["site_url"].rstrip("/")}/{settings["wp_pages"][game]}/">'
                    f'▶ {escape(name)}の抽選情報まとめ一覧へ</a></p>')
    return "\n".join(h for h in html if h)


def _fingerprint(html):
    return sha(re.sub(r"最終更新：[0-9/ :]+", "", html))  # 更新時刻以外が変わった時だけ更新


class WP:
    def __init__(self, site, user, pw, session=None):
        self.api = f"{site.rstrip('/')}/wp-json/wp/v2"
        self.auth = (user, pw)
        self.s = session or requests

    def upsert(self, kind, slug, title, content, extra=None):
        found = self.s.get(f"{self.api}/{kind}", params={"slug": slug, "status": "publish,draft",
                                                          "context": "edit"},
                           auth=self.auth, timeout=30).json()
        data = {"title": title, "content": content, "slug": slug, "status": "publish", **(extra or {})}
        url = f"{self.api}/{kind}/{found[0]['id']}" if found else f"{self.api}/{kind}"
        r = self.s.post(url, json=data, auth=self.auth, timeout=30)
        r.raise_for_status()
        return r.json()


def update_pages(settings, wp=None):
    site = settings.get("site_url")
    user, pw = os.environ.get("WP_USER"), os.environ.get("WP_APP_PASSWORD")
    if wp is None and not (site and user and pw):
        log("WP未設定のためスキップ")
        return
    wp = wp or WP(site, user, pw)
    lots = load_json("lotteries.json", {})
    fp = load_json("wp_hash.json", {})
    jobs = []
    for game, slug in settings["wp_pages"].items():
        jobs.append(("pages", slug, f"【最新】{settings['game_names'][game]} 抽選・予約情報まとめ",
                     render(game, settings, lots), {}))
        cats = settings.get("wp_categories", {}).get(game)
        for s in sorted({series_of(i) for i in lots.values() if i["game"] == game and series_of(i)}):
            n = sum(1 for i in lots.values() if series_of(i) == s and i["game"] == game and i["status"] in ACTIVE)
            title = (f"【{n}件受付中】{s} 抽選・予約情報まとめ【店舗別・締切順】" if n
                     else f"{s} 抽選・予約情報まとめ【受付終了】")
            jobs.append(("posts", series_slug(game, s), title, render_series(game, s, settings, lots),
                         {"categories": [cats]} if cats else {}))

    for kind, slug, title, content, extra in jobs:
        h = _fingerprint(title + content)
        if fp.get(slug) == h:
            continue
        if settings["dry_run"]:
            log(f"DRY_RUN WP更新: {kind}/{slug} {title}")
            continue
        try:
            wp.upsert(kind, slug, title, content, extra)
            fp[slug] = h
            log(f"WP更新OK: {title}")
        except Exception as e:
            log(f"WP更新失敗 {slug}: {e}")
    save_json("wp_hash.json", fp)
