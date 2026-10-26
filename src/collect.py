"""収集：各ソースを見て、新しい抽選を state/lotteries.json に追加する"""
from common import (load_json, save_json, sha, lottery_key, parse_dt, now, log, normalize)
from fetch import get, html_to_text, parse_rss, article_links, cards
from extract import extract
from fetch_x import search as x_search


def collect(sources, settings, extractor=extract, fetcher=get, x_client=None) -> list:
    seen = load_json("seen.json", {})
    lots = load_json("lotteries.json", {})
    new_items = []
    # 弾名の表記ゆれをそろえる（スペース・大文字小文字違いは同じ弾として扱う）
    series_names = {normalize(i.get("series")): i["series"] for i in lots.values() if i.get("series")}

    for src in sources:
        if src.get("enabled") is False:
            continue
        sid, game = src["id"], src["game"]
        gname = settings["game_names"].get(game) or "・".join(settings["game_names"].values())
        texts = []  # (テキスト, 出典URL)
        first_run = sid not in seen  # 初回は既存の抽選を一気に拾うので、Xには流さずWP掲載だけにする

        if src["type"] == "x":
            try:
                posts, newest = x_search(src, settings, seen.get(sid), client=x_client)
            except Exception as e:
                log(f"X取得失敗 {sid}: {e}")
                continue
            if newest:
                seen[sid] = newest
            if posts:  # まとめて1回のAI呼び出しで抽出
                texts.append(("\n\n=====\n\n".join(t for t, _ in posts), "https://x.com/"))
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
            for t in fresh + [None]:  # 約8000字ずつに分けて抽出
                if t is not None and sum(len(x) for x in chunk) + len(t) < 8000:
                    chunk.append(t)
                    continue
                if chunk:
                    texts.append(("\n\n=====\n\n".join(chunk), src["url"]))
                chunk = [t] if t else []
            if fresh:
                log(f"{sid}: 新規・変更 {len(fresh)}件 / 全{len(cur)}件")

        for text, url in texts:
            try:
                items = extractor(text, game, gname, src["name"], url)
            except Exception as e:
                log(f"抽出失敗 {sid}: {e}")
                continue
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

    save_json("seen.json", seen)
    save_json("lotteries.json", lots)
    return new_items
