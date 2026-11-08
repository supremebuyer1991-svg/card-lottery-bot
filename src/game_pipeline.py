"""ゲーム・ホビー入荷速報（SITE=game）の1回分の実行

収集 → 締切の調査 → 応募ページの確認 → 振り分け → 重複まとめ → 承認 → サイト書き出し（site_game/）
トレカ抽選ナビにある相場・Threads・海外向けページ・WordPress・新弾・BOXランキングはこのサイトでは使わない。
Xへの自動投稿も無し（/x-draft.html の下書きをコピペして手で投稿する）。
"""
import sys

from common import load_settings, load_sources, load_json, save_json, log, now, parse_dt


def _end_releases(lots):
    """発売日・再販日（kind=release）は、その日が過ぎたら自動で終了（お店の受付ではないので承認の仕組みを通さずここで）"""
    n = 0
    for it in lots.values():
        if it.get("kind") == "release" and it.get("status") in ("new", "approved", "listed", "posted"):
            e = parse_dt(it.get("end"))
            if e and e.date() < now().date():
                it["status"] = "closed"
                it["closed_at"] = now().isoformat()
                it["closed_reason"] = "発売日・再販日を過ぎた"
                n += 1
    return n


def _fill_kind(lots):
    """kind が無いデータ（表から直接読んだ入荷Nowなど）に kind を付ける"""
    import re
    for it in lots.values():
        if it.get("kind"):
            continue
        txt = " ".join(str(it.get(k) or "") for k in ("product", "method", "conditions", "store"))
        if re.search(r"amazon|アマゾン", it.get("store") or "", re.I) and re.search(r"招待", txt):
            it["kind"] = "invite"
        elif re.search(r"福袋|お年玉箱", txt):
            it["kind"] = "fukubukuro"
        elif re.search(r"再入荷|在庫復活|入荷", txt) and not re.search(r"抽選", txt):
            it["kind"] = "restock"
        elif re.search(r"先着", txt) and not re.search(r"抽選", txt):
            it["kind"] = "first_come"
        elif re.search(r"予約", txt) and not re.search(r"抽選", txt):
            it["kind"] = "preorder"
        else:
            it["kind"] = "lottery"


def run(step="all", extractor=None, fetcher=None, out_dir=None, sources=None):
    s = load_settings()
    log(f"開始（ゲーム・ホビー入荷速報） auto_approve={s['auto_approve']} dry_run={s['dry_run']}")
    from collect import collect, sync_manual
    sync_manual()  # 自分で追加した抽選（config/game/manual.yaml）
    if step in ("all", "publish") and fetcher is None and sources is None:
        try:  # 買取店の新品の買取価格（1回2店まで・各店1日1回）。情報集めの前に読む（残り時間は情報集めの側で調整）
            import game_kaitori
            game_kaitori.update(s)
            import game_premium   # 定価以上で売れる商品：毎日の最高買取価格の記録と、楽天ブックスの定価（1回8件まで）
            game_premium.update(s)
            game_premium.watch_map()   # 見張りが見た楽天・Amazonの状態（予約受付中・販売中）と商品ページ → サイトに出す
        except Exception as e:
            log(f"買取価格: スキップ {e}")
    if step in ("all", "collect"):
        srcs = sources if sources is not None else load_sources()
        kw = {}
        if extractor is not None:
            kw["extractor"] = extractor
        if fetcher is not None:
            kw["fetcher"] = fetcher
        new = collect(srcs, s, **kw)
        log(f"新着 {len(new)} 件")
    if step in ("all", "publish"):
        lots = load_json("lotteries.json", {})
        _fill_kind(lots)
        n = _end_releases(lots)
        save_json("lotteries.json", lots)
        if n:
            log(f"発売日を過ぎた予定 {n}件を終了に")
        try:
            from deadline import fill_deadlines
            fill_deadlines(s)  # 締切が分からないものは応募ページから読み取る（AIの鍵が無ければ何もしない）
        except Exception as e:
            log(f"締切の調査: スキップ {e}")
        try:
            from pagecheck import check_pages
            check_pages(s)
        except Exception as e:
            log(f"応募ページの確認: スキップ {e}")
        try:
            from classify import classify
            classify(s)
        except Exception as e:
            log(f"振り分け: スキップ {e}")
        try:
            from dedupe import dedupe
            dedupe(s)
        except Exception as e:
            log(f"重複: スキップ {e}")
        from approve import approve
        approve(s)
        try:  # 応募先がニュース記事のものは、記事の中の公式ページ（プレバンの商品ページなど）に差し替える
            import official_link
            from fetch import get as _get
            lots = load_json("lotteries.json", {})
            official_link.resolve(s, lots, fetcher or _get)
            save_json("lotteries.json", lots)   # 差し替え・まとめの両方を残す
        except Exception as e:
            log(f"公式リンク探し: スキップ {e}")
        try:  # 楽天ブックスの商品ページ・写真（鍵が無ければ何もしない。1回15回まで・同じ商品は24時間に1回）
            import game_affi
            lots = load_json("lotteries.json", {})
            t = now()
            game_affi.update(s, [i for i in lots.values() if i.get("status") in ("approved", "posted", "listed")
                                 and not (parse_dt(i.get("end")) and parse_dt(i["end"]) < t)])
        except Exception as e:
            log(f"楽天の商品写真: スキップ {e}")
        if out_dir is None:
            try:  # スニダンの相場（1日1回・models.yaml の series_souba に書いたモデルだけ）
                import game_souba
                game_souba.update(s)
                # 買取ルデヤの1商品ずつの検索（kaitori_update）は、9店まとめての読み取り（game_kaitori）に置き換えたので使わない（時間の節約）
            except Exception as e:
                log(f"相場（ゲーム）: スキップ {e}")
        import sitegen_game
        sitegen_game.build(s, out_dir=out_dir)
        if out_dir is None:   # テストでサイトだけ作るときは投稿しない
            try:  # Xの速報（@a9994aaa。鍵が無ければ文面を記録に出すだけ）
                import game_xpost
                game_xpost.post_speed(s)
            except Exception as e:
                log(f"X速報: スキップ {e}")
            try:  # 楽天・Amazonの見張り（Cloudflare Worker game-watch）に渡す一覧 → site_game/watch.json
                import json as _json
                import game_affi
                from common import ROOT
                wl = game_affi.watch_list(load_json("lotteries.json", {}), s)
                try:   # 買取価格が分かる商品すべても見張る（JANで楽天・Amazonの商品ページを見張りの側で探す）
                    import re as _re
                    import game_premium
                    import gamecats
                    gh = "|".join(c.get("hints") or "" for c in gamecats.categories(False) if c.get("group") in ("console", "game_goods") and c.get("hints"))
                    pmin = float(s.get("premium_min_ratio", 1.03))
                    for x in game_premium.catalog(s, game_premium.watch_map())[:int(s.get("watch_catalog_max", 600))]:
                        wl.append({"k": "j" + x["jan"], "jan": x["jan"], "n": x["name"][:40],
                                   "g": bool(_re.search(gh, " ".join(x["names"]), _re.I)), "rk": "", "asin": "", "tag": [],
                                   "tk": x["teika"] or 0, "mx": x["max"], "hot": bool(x["ratio"] and x["ratio"] >= pmin),
                                   "pm": (f"最高買取 {x['max']:,}円（定価比 +{round((x['ratio'] - 1) * 100)}%）" if x["ratio"] and x["ratio"] >= pmin else "")})
                except Exception as e:
                    log(f"見張り（相場の商品）: スキップ {e}")
                (ROOT / "site_game" / "watch.json").write_text(_json.dumps({"updated": now().isoformat(), "items": wl}, ensure_ascii=False), encoding="utf-8")
                log(f"楽天・Amazonの見張り：{len(wl)}件")
            except Exception as e:
                log(f"見張りの一覧: スキップ {e}")
            try:  # Xの予約投稿の計画（明日の分）→ site_game/x-plan.json
                import game_xplan
                from common import ROOT
                site = (s.get("site_public_url") or "https://game-nyuka.com").rstrip("/")
                game_xplan.write(ROOT / "site_game", s, site)
            except Exception as e:
                log(f"予約投稿の計画: スキップ {e}")
    log("完了")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "all")
