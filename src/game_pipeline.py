"""ゲーム・ホビー入荷速報（SITE=game）の1回分の実行

収集 → 締切の調査 → 応募ページの確認 → 振り分け → 重複まとめ → 承認 → サイト書き出し（site_game/）
トレカ抽選ナビにある相場・Threads・海外向けページ・WordPress・新弾・BOXランキングはこのサイトでは使わない。
Xへの自動投稿も無し（/x-draft.html の下書きをコピペして手で投稿する）。
"""
import re
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


# 大手のお店（ポケカの抽選はここだけ載せる。11/10 ユーザーの指示「大手のポケカ抽選は取り扱っていいよ」）
BIG_STORES = re.compile(r"ポケモンセンター|Amazon|アマゾン|楽天ブックス|ヨドバシ|ビックカメラ|ヤマダ|エディオン|ジョーシン|Joshin|ノジマ|セブンネット|イオン|ゲオ|GEO|TSUTAYA|ツタヤ|ケーズ|コジマ|ソフマップ")
TCG = re.compile(r"ポケモンカード|ポケカ|カードゲーム|拡張パック|強化拡張|ブースター|遊戯王|デュエマ|デュエル・?マスターズ|ワンピースカード|ヴァイス|ユニオンアリーナ|トレカ")
DROP_REASON = "このサイトの対象外（トレカなど）"
BIG_TCG = ("pokemon", "onepiece")   # 大手のお店の抽選だけ載せるトレカ（11/10 ユーザー：ポケカ・ワンピースは大手ならいい）


def _tcg_full_names(lots):
    """ポケカ・ワンピカードの抽選の商品名を正式な名前に（「ハドウシーカー」→「ポケモンカードゲーム MEGA 拡張パック「ハドウシーカー」」）。
    トレカ抽選ナビ（state/lotteries.json）で同じ商品にいちばん多く使われている正式な名前を使う（11/10 ユーザーの指示：何の商品か分かるように）"""
    import json
    from collections import Counter
    from common import ROOT
    try:
        tcg = json.loads((ROOT / "state" / "lotteries.json").read_text(encoding="utf-8"))
    except Exception:
        return 0
    head = {"pokemon": ("ポケモンカード",), "onepiece": ("ONE PIECEカード", "ワンピースカード")}
    n = 0
    for it in lots.values():
        g, prod = it.get("game"), (it.get("product") or "").strip()
        if g not in head or not prod or prod.startswith(head[g]):
            continue
        core = re.sub(r"\s*(BOX|ボックス|1BOX)$", "", prod).strip()
        c = Counter()
        for v in tcg.values():
            full = re.sub(r"[（(][^）)]*[）)]\s*$", "", (v.get("product") or "")).strip()
            full = re.sub(r"\s*\d*\s*BOX$", "", full).strip()
            if v.get("game") == g and core and core in full and full.startswith(head[g]) and len(full) <= 70:
                c[full] += 1
        if c:
            best = c.most_common(1)[0][0]
            it.setdefault("product_short", prod)
            it["product"] = best + ("BOX" if re.search(r"BOX|ボックス", prod) and "BOX" not in best else "")
            n += 1
    return n


def _import_tcg(lots):
    """トレカ抽選ナビ（state/lotteries.json）のポケカ・ワンピースカードの受付中の抽選を、このサイトにも載せる
    （11/14 ユーザー：「ポケモンもワンピースも抽選やってるやろ、俺のトレカ抽選ナビに書いてるで」）。
    載せるのは大手のお店とネットの抽選（BIG_STORES か channel=online）。トレカ抽選ナビで確かめ済みなのでここで確かめ直さない。
    Xの速報・投稿の候補には入れない（from_tcg）。トレカ抽選ナビで終わった・消えたものはこちらも終わりにする"""
    import json
    from datetime import datetime
    from common import ROOT, now as now_jst
    try:
        tcg = json.loads((ROOT / "state" / "lotteries.json").read_text(encoding="utf-8"))
    except Exception:
        return 0
    now = now_jst()

    def live(v):
        try:
            return v.get("status") in ("approved", "posted", "listed") and v.get("end") and datetime.fromisoformat(v["end"]) > now
        except Exception:
            return False
    try:   # トレカ抽選ナビの楽天の写真・商品ページ（キー：ゲーム|シリーズ）
        photos = json.loads((ROOT / "state" / "rakuten.json").read_text(encoding="utf-8"))
    except Exception:
        photos = {}
    want = {}
    for k, v in tcg.items():
        if v.get("game") not in BIG_TCG or not live(v):
            continue
        if not (v.get("channel") == "online" or BIG_STORES.search(v.get("store") or "")):
            continue
        want["tc" + (v.get("key") or k)] = v
    # もうこのサイトにある同じお店・同じ商品の抽選（入荷Nowなどから入ったもの）は重ねない
    def nk(store, prod):
        return (re.sub(r"\s", "", store or ""), re.sub(r"\s|1?BOX|ボックス|[「」『』【】()（）]", "", prod or ""))
    have = {nk(it.get("store"), it.get("product")) for kk, it in lots.items()
            if not it.get("from_tcg") and it.get("status") in ("approved", "posted", "listed", "pending")}
    n = 0
    for k, v in want.items():
        if nk(v.get("store"), v.get("product")) in have:
            continue
        it = {f: v.get(f) for f in ("store", "product", "series", "start", "end", "announce", "url", "channel", "area", "method",
                                    "conditions", "tags", "id_check", "member", "game", "source", "source_url", "found_at", "price")
              if v.get(f) is not None}
        it.update({"status": lots.get(k, {}).get("status", "approved") if lots.get(k, {}).get("status") in ("approved", "posted", "listed") else "approved",
                   "kind": "lottery", "from_tcg": True, "verified": True, "key": k})
        ph = photos.get(f"{v.get('game')}|{v.get('series')}") or {}
        if ph.get("image") and ph.get("url"):
            it["photo"] = {"u": ph["url"], "img": ph["image"]}
        if k not in lots:
            n += 1
        lots[k] = {**lots.get(k, {}), **it}
    for it in lots.values():   # 入荷Nowなどから入ったポケカ・ワンピの抽選にも、トレカ抽選ナビの写真を付ける
        if it.get("game") in BIG_TCG and not it.get("from_tcg"):
            ph = photos.get(f"{it.get('game')}|{it.get('series')}") or {}
            if ph.get("image") and ph.get("url"):
                it["photo"] = {"u": ph["url"], "img": ph["image"]}
    for k, it in lots.items():
        if it.get("from_tcg") and k not in want and it.get("status") in ("approved", "posted", "listed", "pending"):
            it["status"] = "expired"
    return n


def _drop_other_games(lots):
    """このサイトのカテゴリ（config/game/categories.yaml）に無いもの・トレカは載せない・投稿しない
    11/10 ユーザー指摘：入荷Nowの抽選情報からポケカ「ハドウシーカー」が入り、ゲームのXアカウントにAPIで投稿された
    → そのあと「大手のポケカ抽選は取り扱っていいよ」：ポケカ（game=pokemon）は大手のお店だけ載せる（投稿はXの予約投稿で・API速報はしない）"""
    import gamecats
    ok = set(gamecats.by_id(False).keys())
    n = 0
    for it in lots.values():
        big_poke = it.get("game") in BIG_TCG and it["game"] in ok and BIG_STORES.search(it.get("store") or "")
        if it.get("status") == "rejected" and it.get("reject_reason") == DROP_REASON and big_poke:
            it["status"] = "approved"   # 前に外した大手のポケカを戻す
            it.pop("reject_reason", None)
            continue
        if it.get("status") in ("rejected", "expired") or big_poke or it.get("from_tcg"):
            continue
        text = " ".join(str(it.get(k) or "") for k in ("product", "title", "summary"))
        if (it.get("game") and it["game"] not in ok) or it.get("game") in BIG_TCG or TCG.search(text):
            it["status"] = "rejected"
            it["reject_reason"] = DROP_REASON
            n += 1
    return n


def run(step="all", extractor=None, fetcher=None, out_dir=None, sources=None):
    s = load_settings()
    log(f"開始（ゲーム・ホビー入荷速報） auto_approve={s['auto_approve']} dry_run={s['dry_run']}")
    # 時間の目安は「ゲームの処理が始まってから」で数える（11/10：トレカ側が3〜4分かかるようになり、
    # 実行の最初から数えると買取価格・定価・解説がいつも時間切れで1件も進まなかった）。game_job_offset_sec 秒たった所から始めた扱い
    import os
    import time
    if os.environ.get("JOB_T0", "").isdigit():
        os.environ["JOB_T0"] = str(int(time.time()) - int(s.get("game_job_offset_sec", 90)))
    from collect import collect, sync_manual
    sync_manual()  # 自分で追加した抽選（config/game/manual.yaml）
    if step == "all" and fetcher is None and sources is None and extractor is None:
        try:   # 商品ページに足す商品の事実（メーカー公式など）を、情報集めの間に裏で取る（時間を延ばさない。11/14）
            import game_facts
            game_facts.start(s)
        except Exception as e:
            log(f"商品の事実: スキップ {e}")
    if step in ("all", "collect"):
        srcs = sources if sources is not None else load_sources()
        kw = {}
        if extractor is not None:
            kw["extractor"] = extractor
        if fetcher is not None:
            kw["fetcher"] = fetcher
        new = collect(srcs, s, **kw)
        log(f"新着 {len(new)} 件")
    if step in ("all", "publish") and fetcher is None and sources is None:
        try:  # 買取店の新品の買取価格（1回2店まで・各店1日1回）。抽選集めのあと、残りの時間で（11/9：先に読むと抽選集めの時間が無くなったため）
            import game_premium
            game_premium.watch_map()   # 見張りが見た楽天・Amazonの状態（予約受付中・販売中）と商品ページ → サイトに出す（すぐ終わる）
            import game_kaitori
            game_kaitori.update(s)
            game_premium.update(s)    # 定価以上で売れる商品：毎日の最高買取価格の記録と、楽天ブックスの定価
            try:
                game_premium.photo_update(s)   # 写真の無い商品（家電・カメラなど）の写真を楽天市場からJANで（11/14）
                game_premium.az_photo_update(s)   # 楽天にも無ければAmazonからJANで（11/14）
            except Exception as e:
                log(f"相場の写真: スキップ {e}")
            import game_upcoming
            game_upcoming.update(s)   # 発売予定のゲーム（楽天ブックス・1日1回）
            try:
                import game_watchkw
                game_watchkw.update(s)    # 言葉で楽天ブックスのおもちゃを探して見張りに足す（ベイブレードX など・1日1回。11/13）
            except Exception as e:
                log(f"見張りの言葉: スキップ {e}")
            try:   # 11/10：解説を先にすると40秒かかり、買取価格の更新がずっと時間切れで止まっていた → 買取価格のあと、残りの時間で
                import game_aitext
                try:
                    import game_facts
                    from common import job_elapsed as _je
                    game_facts.wait(float(s.get("product_facts_until_sec", 200)) - _je())   # 裏で取っていた商品の事実を待つ（上限つき）
                except Exception as e:
                    log(f"商品の事実: スキップ {e}")
                game_aitext.update(s)     # 中身の少ない商品ページから順に解説を足す（前の回の測定を使う）
            except Exception as e:
                log(f"解説: スキップ {e}")
        except Exception as e:
            log(f"買取価格: スキップ {e}")
    if step in ("all", "publish"):
        lots = load_json("lotteries.json", {})
        _fill_kind(lots)
        # AIが「本文に記載はありません」のような説明を条件の欄に書いてしまうことがある → サイトに出さない（11/10 ちいかわクリスマスマーケット）
        for it in lots.values():
            if re.search(r"本文|記載はありません|記載がありません|書かれていません|明記されていません", it.get("conditions") or ""):
                it["conditions"] = None
        try:
            ni = _import_tcg(lots)
            if ni:
                log(f"トレカ抽選ナビのポケカ・ワンピースカードの抽選 {ni}件を載せました")
        except Exception as e:
            log(f"トレカ抽選ナビの取り込み: スキップ {e}")
        nt = _drop_other_games(lots)
        _tcg_full_names(lots)
        if nt:
            log(f"このサイトのカテゴリ以外（トレカなど）{nt}件を外しました")
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
        if fetcher is None:
            try:  # 載せる前に、読み取った内容（お店・商品・種類・日時・通販/店頭）が元の記事と合っているかAIでもう一度確かめる
                import game_verify
                game_verify.verify(s)
            except Exception as e:
                log(f"内容の確認: スキップ {e}")
        try:  # 楽天ブックスの商品ページ・写真（鍵が無ければ何もしない。1回15回まで・同じ商品は24時間に1回）
            import game_affi
            lots = load_json("lotteries.json", {})
            t = now()
            _live = [i for i in lots.values() if i.get("status") in ("approved", "posted", "listed")
                     and not (parse_dt(i.get("end")) and parse_dt(i["end"]) < t) and not i.get("from_tcg")]   # トレカ抽選ナビから載せたものは向こうの写真を使う
            _c = game_affi.update(s, _live)
            game_affi.photo_update(s, _live, cache=_c)   # 楽天ブックスに無い商品の写真を楽天市場から（11/14）
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
                _kw = []
                try:
                    import game_watchkw
                    _kw = game_watchkw.watch_items(s, {w_.get("rk") for w_ in wl if w_.get("rk")})
                except Exception as e:
                    log(f"見張り（言葉）: スキップ {e}")
                try:   # 買取価格が分かる商品すべても見張る（JANで楽天・Amazonの商品ページを見張りの側で探す）
                    import re as _re
                    import game_premium
                    import gamecats
                    gh = "|".join(c.get("hints") or "" for c in gamecats.categories(False) if c.get("group") in ("console", "game_goods") and c.get("hints"))
                    pmin = float(s.get("premium_min_ratio", 1.03))
                    for x in game_premium.catalog(s, game_premium.watch_map())[:int(s.get("watch_catalog_max", 600))]:
                        wl.append({"k": "j" + x["jan"], "jan": x["jan"], "n": x["name"][:40],
                                   "g": bool(_re.search(gh, " ".join(x["names"]), _re.I)), "rk": "", "asin": "", "tag": [],
                                   "tk": x["teika"] or 0, "mx": x["max"], "hot": bool(x["ratio"] and x["ratio"] >= pmin), "pg": f"/premium/{x['jan']}/",
                                   "neg": bool(x["teika"] and x["max"] < x["teika"] * float(s.get("x_min_buy_ratio", 0.8))),   # 買取が定価の8割未満（速報しない。11/13）
                                   "pm": (f"最高買取 {x['max']:,}円（定価比 +{round((x['ratio'] - 1) * 100)}%）" if x["ratio"] and x["ratio"] >= pmin else "")})
                except Exception as e:
                    log(f"見張り（相場の商品）: スキップ {e}")
                try:   # 言葉で見つけた商品（ベイブレードX など）。相場の商品と同じJANは足さない
                    _have = {w_.get("jan") for w_ in wl if w_.get("jan")}
                    wl += [w_ for w_ in _kw if not (w_.get("jan") and w_["jan"] in _have)]
                except Exception as e:
                    log(f"見張り（言葉）: スキップ {e}")
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
