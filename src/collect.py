"""収集：各ソースを見て、新しい抽選を state/lotteries.json に追加する"""
from common import (load_json, save_json, sha, lottery_key, parse_dt, now, log, normalize)
from fetch import get, html_to_text, parse_rss, article_links, cards, cardchusen_items
from extract import extract
from fetch_x import search as x_search


SEEN_VERSION = 5
MANUAL_FIELDS = ("game", "store", "product", "series", "products", "channel", "area", "method", "start", "end",
                 "announce", "buy", "conditions", "member", "id_check", "tags", "url", "image")


def _iso(v):
    """YAMLの日時（2026-11-01T23:00 / 文字列 / datetime）を +09:00 付きの文字列に"""
    from datetime import datetime, date
    if isinstance(v, datetime):
        v = v.isoformat()
    elif isinstance(v, date):
        v = f"{v.isoformat()}T23:59"
    dt = parse_dt(str(v)) if v else None
    return dt.isoformat(timespec="minutes") if dt else None


def load_manual():
    """config/manual.yaml（自分で追加した抽選）"""
    import yaml
    from common import ROOT
    p = ROOT / "config" / "manual.yaml"
    if not p.exists():
        return []
    rows = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("lotteries") or []
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("store") or not r.get("game"):
            continue
        it = {k: r.get(k) for k in MANUAL_FIELDS if r.get(k) not in (None, "", [])}
        for k in ("start", "end"):
            if k in it:
                it[k] = _iso(it[k])
        for k in ("announce", "buy"):
            if k in it:
                it[k] = str(it[k])
        it.setdefault("product", it.get("series") or "")
        it.setdefault("channel", "online")
        if r.get("slug"):
            it["slug"] = str(r["slug"])
        out.append(it)
    return out


def sync_manual():
    """main から毎回呼ぶ：manual.yaml の抽選を lotteries.json に反映"""
    lots = load_json("lotteries.json", {})
    try:
        add_manual(lots)
    except Exception as e:
        log(f"手動追加: スキップ {e}")
        return
    save_json("lotteries.json", lots)


def add_manual(lots):
    """手で追加した抽選を載せる（毎回 manual.yaml の内容で上書き。自動投稿はしない＝listed）"""
    n = 0
    for it in load_manual():
        end = parse_dt(it.get("end"))
        k = lottery_key(it)
        old = lots.get(k)
        if old is None:
            if end and end < now():
                continue
            lots[k] = dict(it, key=k, status="listed", found_at=now().isoformat(), manual=True,
                           source="手動追加", confidence=1.0)
            n += 1
            log(f"手動追加: [{it['game']}] {it['store']} / {it['product']}")
        else:
            old.update(it, manual=True)
            if old.get("status") == "duplicate":  # 手動の方を正にする
                old["status"] = "listed"
                old.pop("duplicate_of", None)
    return n


def collect(sources, settings, extractor=extract, fetcher=get, x_client=None) -> list:
    seen = load_json("seen.json", {})
    if seen.get("_v") != SEEN_VERSION:  # 仕組みを直した時は、もう一度全部読み直す
        seen = {"_v": SEEN_VERSION}
    lots = load_json("lotteries.json", {})
    new_items = []
    live = {}  # cardchusen：今回の一覧に載っている抽選のキー（情報元ごと）。載っていない抽選は終了とみなす
    # 弾名の表記ゆれをそろえる（スペース・大文字小文字違いは同じ弾として扱う）
    series_names = {normalize(i.get("series")): i["series"] for i in lots.values() if i.get("series")}

    # Xを読むのは1時間に1回（30分ごとの実行の1回おき）。読む量（費用）を抑えるため
    xmeta = load_json("x_meta.json", {})
    last_x = parse_dt(xmeta.get("last_x_run"))
    x_turn = settings.get("x_every_minutes", 55)
    x_ok = not last_x or (now() - last_x).total_seconds() >= x_turn * 60
    if x_ok and any(s_.get("type") == "x" and s_.get("enabled") is not False for s_ in sources):
        xmeta["last_x_run"] = now().isoformat()
    elif not x_ok:
        log("X: 今回はお休み（1時間に1回だけ読む）")
    src_last = xmeta.setdefault("src_last", {})

    for src in sources:
        if src.get("enabled") is False:
            continue
        if src["type"] == "x":
            if not x_ok:
                continue
            # あまり抽選が見つからない検索は、数時間に1回だけ（every_hours）
            lt = parse_dt(src_last.get(src["id"]))
            if src.get("every_hours") and lt and (now() - lt).total_seconds() < src["every_hours"] * 3600 - 300:
                continue
            src_last[src["id"]] = now().isoformat()
        sid, game = src["id"], src["game"]
        gname = settings["game_names"].get(game) or "・".join(settings["game_names"].values())
        texts = []  # (テキスト, 出典URL)
        direct = []  # AIを通さずに読めた抽選
        first_run = sid not in seen  # 初回は既存の抽選を一気に拾うので、Xには流さずWP掲載だけにする

        if src["type"] == "x":
            try:
                posts, newest = x_search(src, settings, seen.get(sid), client=x_client)
            except Exception as e:
                log(f"X取得失敗 {sid}: {e}")
                continue
            if newest:
                seen[sid] = newest
            try:  # 読んだポストの中に抽選結果の発表があれば拾う（追加の読み取りはしない）
                from results import scan as scan_results
                scan_results(posts, src, lots)
            except Exception as e:
                log(f"抽選結果の確認失敗 {sid}: {e}")
            for i in range(0, len(posts), 5):  # 5件ずつAIへ（多すぎると返事が途中で切れる）
                texts.append(("\n\n=====\n\n".join(t for t, _ in posts[i:i + 5]), "https://x.com/"))
            body = None
        else:
            try:
                body = fetcher(src["url"])
            except Exception as e:
                log(f"取得失敗 {sid}: {e}")
                continue

        if src["type"] == "rss":
            done = set(seen.get(sid, []))
            for it in parse_rss(body):
                if it["guid"] in done:
                    continue
                done.add(it["guid"])
                texts.append((f"{it['title']}\n{it['date']}\n{it['summary']}\nURL: {it['link']}", it["link"]))
            seen[sid] = list(done)[-500:]
        elif src["type"] == "html":
            text = html_to_text(body, src["url"])
            h = sha(text)
            if seen.get(sid) == h:
                continue  # 変化なし → AIを呼ばない（費用節約）
            seen[sid] = h
            texts.append((text, src["url"]))
        elif src["type"] == "html_index":
            # 一覧ページ → 該当記事を開き、記事ごとに変化があったものだけAIへ
            prev = seen.get(sid) if isinstance(seen.get(sid), dict) else {}
            cur = {}
            for url in article_links(body, src["url"], src.get("link_keywords", []),
                                     src.get("max_articles", 10)):
                try:
                    text = html_to_text(fetcher(url), url)
                except Exception as e:
                    log(f"記事取得失敗 {url}: {e}")
                    continue
                cur[url] = sha(text)
                if prev.get(url) != cur[url]:
                    texts.append((text, url))
            seen[sid] = cur
        elif src["type"] == "html_cards" and "board-card" in body and cardchusen_items(body, src["url"]):
            # cardchusen：整理済みデータを直接読む（AI不要・無料）
            prev = seen.get(sid) if isinstance(seen.get(sid), dict) else {}
            cur = {}
            keys = set()
            for key, h, item in cardchusen_items(body, src["url"]):
                cur[key] = h
                item.update(game=item.get("game") or (game if game != "auto" else "pokemon"),
                            source=src["name"], source_url=src["url"])
                keys.add(lottery_key(item))
                if prev.get(key) != h:
                    direct.append(item)
            live[src["name"]] = keys
            seen[sid] = cur
            log(f"{sid}: 直接読み取り 新規・変更 {len(direct)}件 / 全{len(cur)}件")
        elif src["type"] == "html_cards":
            # 一覧型サイト：カード（応募URL単位）で差分を取り、新規・変更分だけをまとめてAIへ
            prev = seen.get(sid) if isinstance(seen.get(sid), dict) else {}
            cur, fresh = {}, []
            for key, h, text in cards(body, src["url"], src.get("card_link_text", "応募")):
                cur[key] = h
                if prev.get(key) != h:
                    fresh.append(text)
            seen[sid] = cur
            chunk = []
            for t in fresh + [None]:  # 約3500字（10件前後）ずつに分けて抽出
                if t is not None and sum(len(x) for x in chunk) + len(t) < 3500 and len(chunk) < 12:
                    chunk.append(t)
                    continue
                if chunk:
                    texts.append(("\n\n=====\n\n".join(chunk), src["url"]))
                chunk = [t] if t else []
            if fresh:
                log(f"{sid}: 新規・変更 {len(fresh)}件 / 全{len(cur)}件")
                log(f"  見本: {fresh[0][:200]!r}")

        batches = []
        for text, url in texts:
            try:
                items = extractor(text, game, gname, src["name"], url)
            except Exception as e:
                log(f"抽出失敗 {sid}: {e}")
                continue
            log(f"  {sid}: AIが {len(items)}件 抽出")
            batches.append((items, url))
        if direct:
            batches.append((direct, None))
        for items, url in batches:
            for it in items:
                end = parse_dt(it.get("end"))
                if end and end < now():
                    continue  # 締切済み
                if it.get("series"):
                    it["series"] = series_names.setdefault(normalize(it["series"]), it["series"])
                k = lottery_key(it)
                if k in lots:
                    old = lots[k]  # 既存なら空欄だけ補完
                    for f in ("start", "end", "announce", "method", "conditions", "x_post", "series",
                              "id_check", "member", "tags", "area", "image"):
                        if old.get(f) in (None, "", []) and it.get(f) not in (None, "", []):
                            old[f] = it[f]
                    continue
                if src.get("quote") is False:
                    it["no_quote"] = True  # ネタ元アカは引用しない
                if src.get("hide_source_url") and it.get("url") == url:
                    # 他サイトの記事URLは載せない。店舗の応募ページが取れなかった場合は承認待ちへ
                    it["url"] = None
                    it["confidence"] = min(float(it.get("confidence") or 0), 0.5)
                it.update(key=k, status="listed" if first_run else "new", found_at=now().isoformat())
                lots[k] = it
                new_items.append(it)
                log(f"新規: [{it['game']}] {it['store']} / {it['product']} 締切={it.get('end')}")

    # cardchusen の一覧から消えた抽選は終了（締切が書かれていない古い抽選が残り続けないように）
    for name, keys in live.items():
        if len(keys) < 30:
            continue  # 読み込みが不完全かもしれない時は何もしない
        gone = [i for i in lots.values() if i.get("source") == name and i.get("status") in ("listed", "posted", "approved", "new", "pending")
                and i.get("key") not in keys]
        for i in gone:
            i["status"] = "closed" if i["status"] in ("listed", "posted") else "expired"
            i["closed_reason"] = "情報元の一覧から消えた"
            i["closed_at"] = now().isoformat()
        if gone:
            log(f"{name}: 一覧から消えた {len(gone)}件を終了に")

    save_json("x_meta.json", {**load_json("x_meta.json", {}), "last_x_run": xmeta.get("last_x_run"), "src_last": src_last})

    save_json("seen.json", seen)
    save_json("lotteries.json", lots)
    return new_items
