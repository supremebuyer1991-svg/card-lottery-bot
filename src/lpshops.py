"""LivePocketの常連店：お店（主催者）のページを覚えておき、Xを使わずに直接見に行く

・抽選ページ（livepocket.jp/e/〇〇）には、お店のページ（livepocket.jp/p/〇〇）へのリンクがある
・お店のページのURLは変わらず、そのお店の受付中・これからの抽選が一覧で並ぶ
・2回以上抽選をしたお店（常連店）は、お店のページを数時間おきに見て、まだ知らない抽選だけをAIに読ませる
・覚えた内容は state/lp_shops.json
"""
import re

from common import load_json, save_json, now, parse_dt, log
from fetch import get

EVENT_RE = re.compile(r"https?://livepocket\.jp/e/([A-Za-z0-9_\-]+)")
ORG_RE = re.compile(r'href="(?:https?://livepocket\.jp)?(/p/[A-Za-z0-9_\-]+)"')
KEYWORDS = ["ポケモンカード", "ポケカ", "ワンピース", "ワンピ", "ONE PIECE", "フュージョンワールド", "ドラゴンボール"]
FILE = "lp_shops.json"


def canon(url):
    """抽選ページのURLをそろえる（?以降や末尾の/の違いをなくす）"""
    m = EVENT_RE.match(url or "")
    return f"https://livepocket.jp/e/{m.group(1)}" if m else None


def org_of(html):
    """抽選ページのHTMLから、お店のページのURL"""
    m = ORG_RE.search(html or "")
    return f"https://livepocket.jp{m.group(1)}" if m else None


def _load():
    db = load_json(FILE, {})
    db.setdefault("events", {})  # 抽選ID → お店のページ（分からなかったら ""）
    db.setdefault("shops", {})   # お店のページ → {"name", "events": [抽選ID], "checked": 最後に見た時刻}
    return db


def _remember(db, eid, org, store):
    db["events"][eid] = org or ""
    if org:
        s = db["shops"].setdefault(org, {"name": store or "", "events": []})
        if eid not in s["events"]:
            s["events"].append(eid)
        if not s.get("name") and store:
            s["name"] = store


def record(url, html, store=""):
    """ほかの処理ですでに読んだ抽選ページから、お店のページを覚える（追加のアクセスなし）"""
    c = canon(url)
    if not c:
        return
    db = _load()
    eid = c.rsplit("/", 1)[1]
    if db["events"].get(eid):
        return
    _remember(db, eid, org_of(html), store)
    save_json(FILE, db)


def learn(lots, fetcher=get, limit=8):
    """まだお店が分からない抽選ページを、新しいものから少しずつ読んでお店のページを覚える"""
    db = _load()
    todo = {}
    for it in sorted(lots.values(), key=lambda i: i.get("found_at") or "", reverse=True):
        for u in (it.get("apply_url"), it.get("url")):
            c = canon(u)
            if c:
                eid = c.rsplit("/", 1)[1]
                if eid not in db["events"] and eid not in todo:
                    todo[eid] = it.get("store") or ""
                break
    n = 0
    for eid, store in list(todo.items())[:limit]:
        try:
            html = fetcher(f"https://livepocket.jp/e/{eid}")
        except Exception as e:
            log(f"LivePocket常連店: 抽選ページ取得失敗 {eid} {e}")
            db["events"][eid] = ""  # 読めないページで毎回つまずかないように
            continue
        org = org_of(html)
        _remember(db, eid, org, store)
        n += 1 if org else 0
    save_json(FILE, db)
    if todo:
        log(f"LivePocket常連店: 抽選ページ{min(len(todo), limit)}件からお店{n}件を確認（残り{max(0, len(todo) - limit)}件）")


def sources(settings, lots, base_sources):
    """今回見に行く常連店のお店ページを、情報元（html_newlinks）の形で返す"""
    db = _load()
    have = {s_.get("url") for s_ in base_sources}  # すでに情報元にあるお店（キデイランドなど）は除く
    min_ev = settings.get("lp_shop_min_events", 2)
    every = settings.get("lp_shop_every_hours", 4)
    per_run = settings.get("lp_shops_per_run", 12)
    due = []
    for org, s in db["shops"].items():
        if len(s.get("events") or []) < min_ev or org in have:
            continue
        t = parse_dt(s.get("checked"))
        if t and (now() - t).total_seconds() < every * 3600 - 300:
            continue
        due.append((s.get("checked") or "", org, s))
    due.sort(key=lambda x: x[0])  # 長く見ていないお店から
    known = sorted({c for it in lots.values() for c in (canon(it.get("apply_url")), canon(it.get("url"))) if c})
    out = []
    for _, org, s in due[:per_run]:
        s["checked"] = now().isoformat()
        out.append({"id": "lpshop_" + org.rsplit("/", 1)[1], "game": "auto", "name": f"{s.get('name') or 'お店'}（LivePocket）",
                    "type": "html_newlinks", "url": org, "link_keywords": KEYWORDS, "max_articles": 30,
                    "skip_urls": known, "not_first": True})
    save_json(FILE, db)
    watched = sum(1 for o, s in db["shops"].items() if len(s.get("events") or []) >= min_ev and o not in have)
    if watched:
        log(f"LivePocket常連店: 常連{watched}店のうち今回{len(out)}店を見る")
    return out
