"""収集：各ソースを見て、新しい抽選を state/lotteries.json に追加する"""
from datetime import timedelta
from common import (load_json, save_json, sha, lottery_key, parse_dt, now, log, normalize)
from fetch import get, html_to_text, parse_rss, article_links, cards, cardchusen_items
from extract import extract
from fetch_x import search as x_search


SEEN_VERSION = 5
MANUAL_FIELDS = ("game", "store", "product", "series", "products", "channel", "area", "method", "start", "end",
                 "announce", "buy", "conditions", "member", "id_check", "tags", "url", "image", "address",
                 "kind", "price", "round")  # kind・price・round はゲーム・ホビー版で使う


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
    from common import CONFIG_DIR
    p = CONFIG_DIR / "manual.yaml"
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
        if "price" in it:
            it["price"] = str(it["price"])
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


def _will_read(src, src_fail, src_last):
    """今回この情報元（X以外）のページを読みに行くか（collect の中の判断と同じ。状態は変えない）"""
    if src.get("enabled") is False or src.get("type") == "x" or not src.get("url"):
        return False
    fl = src_fail.get(src["id"]) or {}
    if fl.get("n", 0) >= 2 and parse_dt(fl.get("until")) and parse_dt(fl["until"]) > now():
        return False
    if src.get("every_hours"):
        lt = parse_dt(src_last.get(src["id"]))
        if lt and (now() - lt).total_seconds() < src["every_hours"] * 3600 - 300:
            return False
    return True


def prefetch(urls, fetcher, workers=6):
    """一覧ページをまとめて先に読む（時間短縮）。
    同じサイトは今まで通り1件ずつ順番に（相手に負担をかけない）、別々のサイトだけ同時に読む。
    戻り値：{url: ("ok", 本文) または ("err", 例外)}"""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlparse
    by_host = {}
    for u in dict.fromkeys(urls):
        by_host.setdefault(urlparse(u).netloc, []).append(u)

    def run(us):
        out = {}
        for u in us:
            try:
                out[u] = ("ok", fetcher(u))
            except Exception as e:
                out[u] = ("err", e)
        return out

    res = {}
    if not by_host:
        return res
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(by_host)))) as ex:
        for part in ex.map(run, by_host.values()):
            res.update(part)
    return res


def collect(sources, settings, extractor=extract, fetcher=get, x_client=None) -> list:
    seen = load_json("seen.json", {})
    if seen.get("_v") != SEEN_VERSION:  # 仕組みを直した時は、もう一度全部読み直す
        seen = {"_v": SEEN_VERSION}
    lots = load_json("lotteries.json", {})
    new_items = []
    live = {}  # cardchusen：今回の一覧に載っている抽選のキー（情報元ごと）。載っていない抽選は終了とみなす
    # 弾名の表記ゆれをそろえる（スペース・大文字小文字違いは同じ弾として扱う）
    series_names = {normalize(i.get("series")): i["series"] for i in lots.values() if i.get("series")}

    # Xを読むのは1時間に1回（毎回の実行で読む。実行の間がつまった時だけ休む）。読む量（費用）を抑えるため
    xmeta = load_json("x_meta.json", {})
    last_x = parse_dt(xmeta.get("last_x_run"))
    x_turn = settings.get("x_every_minutes", 40)
    x_ok = not last_x or (now() - last_x).total_seconds() >= x_turn * 60
    if x_ok and any(s_.get("type") == "x" and s_.get("enabled") is not False for s_ in sources):
        xmeta["last_x_run"] = now().isoformat()
    elif not x_ok:
        log("X: 今回はお休み（1時間に1回だけ読む）")
    src_last = xmeta.setdefault("src_last", {})
    src_fail = xmeta.setdefault("src_fail", {})
    # Xの検索ごとの「読んだ数・新しく見つかった抽選の数」（どの検索が効いているかを見て件数を調整するため）
    xstats = load_json("x_stats.json", {})
    today_s = now().date().isoformat()
    xst = xstats.setdefault(today_s, {})

    # 1日の上限（300件）が夜までもつように、1回に読める数を「残り ÷ 今日の残りの回数」にする。
    # よく抽選が見つかる検索から先に読み、足りなくなったら残りの検索は次の回に回す
    x_allow = 0
    if x_ok:
        from fetch_x import budget_left, peak_set
        h = now().hour
        # Xを読むのは0時台と7時〜23時台の1時間に1回（上限は0時で切り替わるので、0時台はその日の最初の回）
        rh = settings.get("run_hours") or list(range(7, 24))  # 1日の実行の時刻（run.yml の cron と合わせる）
        runs_left = max(1, sum(1 for x in rh if x >= h)) if h >= min(rh) else len(rh)
        x_allow = budget_left(settings) // max(1, runs_left)
        days = sorted(xstats)[-4:]

        def _yield(s_):
            rd = sum((xstats[d].get(s_["id"]) or [0, 0])[0] for d in days)
            nw = sum((xstats[d].get(s_["id"]) or [0, 0])[1] for d in days)
            return -(nw + 1) / (rd + 5)
        xs = sorted([s_ for s_ in sources if s_.get("type") == "x"], key=_yield)
        sources = [s_ for s_ in sources if s_.get("type") != "x"] + xs
        log(f"X: 今回読める数 {x_allow}件（今日の残り{budget_left(settings)}件・残り{runs_left}回）" + (f"・新弾「{peak_set(settings)}」の発売前で上限アップ中" if peak_set(settings) else ""))

    # X以外の一覧ページは、別々のサイトどうしを同時に先読みしておく（1件ずつ待つより速い）
    pre = prefetch([s_["url"] for s_ in sources if _will_read(s_, src_fail, src_last)], fetcher)

    def read_top(url):
        if url in pre:
            kind, val = pre.pop(url)
            if kind == "err":
                raise val
            return val
        return fetcher(url)

    # 情報集めの時間の上限（秒）。設定に collect_time_budget がある時だけ効く（トレカ側は設定なし＝今まで通り）
    budget = settings.get("collect_time_budget")
    t_start = now()
    for src in sources:
        if budget and (now() - t_start).total_seconds() > budget:
            log(f"情報集めの時間の上限（{budget}秒）に達したので、残りの情報元は次の回に回します")
            break
        if src.get("enabled") is False:
            continue
        if src["type"] != "x":  # 続けて読めなかった情報元は、しばらくお休み（タイムアウト待ちで実行時間がのびないように）
            fl = src_fail.get(src["id"]) or {}
            if fl.get("n", 0) >= 2 and parse_dt(fl.get("until")) and parse_dt(fl["until"]) > now():
                continue
        if src["type"] != "x" and src.get("every_hours"):  # Xいがいも、数時間に1回だけ見る情報元
            lt = parse_dt(src_last.get(src["id"]))
            if lt and (now() - lt).total_seconds() < src["every_hours"] * 3600 - 300:
                continue
            src_last[src["id"]] = now().isoformat()
        if src["type"] == "x":
            if not x_ok:
                continue
            if x_allow < 10:  # Xの検索は1回10件から。今回の分を使い切ったら次の回へ
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
        # 初回は既存の抽選を一気に拾うので、Xには流さずWP掲載だけにする
        # （LivePocket常連店は、知っている抽選を skip_urls で除くので初回でもふつうに新着扱い）
        first_run = sid not in seen and not src.get("not_first")

        if src["type"] == "x":
            try:
                posts, newest = x_search(dict(src, max_results=min(src.get("max_results", 20), x_allow)), settings,
                                         seen.get(sid), client=x_client)
                x_allow -= len(posts)
            except Exception as e:
                log(f"X取得失敗 {sid}: {e}")
                continue
            if newest:
                seen[sid] = newest
            xst.setdefault(sid, [0, 0])[0] += len(posts)
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
                body = read_top(src["url"])
                src_fail.pop(sid, None)
            except Exception as e:
                fl = src_fail.setdefault(sid, {"n": 0})
                fl["n"] += 1
                if fl["n"] >= 2:  # 2回続けて失敗 → 3時間（5回以上は6時間）お休み
                    fl["until"] = (now() + timedelta(hours=6 if fl["n"] >= 5 else 3)).isoformat()
                log(f"取得失敗 {sid}: {e}" + (f"（{fl['n']}回続けて失敗。しばらく休む）" if fl["n"] >= 2 else ""))
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
                    raw = fetcher(url)
                    text = html_to_text(raw, url)
                except Exception as e:
                    log(f"記事取得失敗 {url}: {e}")
                    continue
                if src.get("parser") == "nyukanow" and "accordionBox" in raw:
                    # 入荷Nowのまとめ記事：表をそのまま読む（AI不要・お店ごとに変わった表だけ）
                    import nyukanow
                    got = nyukanow.items(raw, url)
                    for key, h, item in got:
                        cur[key] = h
                        if prev.get(key) != h:
                            direct.append(dict(item, source=src["name"], source_url=url))
                    log(f"{sid}: 表から直接読み取り {len(got)}件（{url}）")
                    continue
                cur[url] = sha(text)
                if prev.get(url) != cur[url]:
                    texts.append((text, url))
            seen[sid] = cur
        elif src["type"] == "html_newlinks":
            # 主催者ページ（LivePocketのお店の一覧など）→ まだ読んでいない抽選ページだけをAIへ（1ページ1回だけ）
            # 抽選ページは残り時間などで中身が少しずつ変わるので、中身の変化では読み直さない
            done = seen.get(sid) if isinstance(seen.get(sid), list) else []
            skip = set(src.get("skip_urls") or ())  # もう知っている抽選ページ（AIに読ませない）
            for url in article_links(body, src["url"], src.get("link_keywords", []), src.get("max_articles", 30)):
                if url in done or url.split("?")[0].rstrip("/") in skip:
                    continue
                done.append(url)
                try:
                    texts.append((html_to_text(fetcher(url), url), url))
                except Exception as e:
                    log(f"記事取得失敗 {url}: {e}")
                    done.remove(url)
            seen[sid] = done[-300:]
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
                if src["type"] == "x":
                    xst.setdefault(sid, [0, 0])[1] += 1
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

    if live and all(len(v) >= 30 for v in live.values()):  # 拾い漏れチェック用に、まとめサイトに今載っている抽選を残す
        save_json("cc_live.json", {k_: sorted(v_) for k_, v_ in live.items()})
    save_json("x_stats.json", {d_: v_ for d_, v_ in xstats.items() if d_ >= (now().date() - timedelta(days=14)).isoformat()})
    save_json("x_meta.json", {**load_json("x_meta.json", {}), "last_x_run": xmeta.get("last_x_run"), "src_last": src_last, "src_fail": src_fail})

    save_json("seen.json", seen)
    save_json("lotteries.json", lots)
    return new_items
