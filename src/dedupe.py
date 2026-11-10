"""同じ抽選の重複をまとめる（別々の情報元から同じ抽選を拾った時）

同じゲーム・同じ店（チェーン名の表記ゆれをそろえる）・同じ弾・同じ締切日なら同じ抽選とみなし、
一番くわしいもの（応募ページがある・cardchusen由来・承認済み）を残して、ほかは status=duplicate にする。
"""
import re
import unicodedata

from common import load_json, save_json, log, load_settings, SITE

ACTIVE = ("new", "pending", "approved", "posted", "listed")
# ゲーム・ホビー版：締切という考えのない種類（再入荷・先着・発売日）は「締切なし同士をまとめる」の対象にしない
NO_DEADLINE_KINDS = ("restock", "first_come", "release")


def _extra_strip():
    """ゲーム・ホビー版：カテゴリ設定（categories.yaml の strip_words）にある共通の言葉も無視する"""
    if SITE != "game":
        return ""
    try:
        import gamecats
        return gamecats.strip_words()
    except Exception:
        return ""
STORE_ALIAS = {"電機": "デンキ", "ヤマダ電器": "ヤマダデンキ", "ビックカメラ": "ビックカメラ", "ヨドバシカメラ": "ヨドバシ",
               "トイザらス": "トイザラス", "ツタヤ": "TSUTAYA", "ふるいち": "古本市場",
               "JUMP SHOP": "ジャンプショップ", "JUMPSHOP": "ジャンプショップ", "Jump Shop": "ジャンプショップ", "ドラスタ": "ドラゴンスター",
               "BOOKOFF": "ブックオフ", "Bookoff": "ブックオフ", "SUPER BAZAAR": "スーパーバザー",
               "プレミアムバンダイ": "プレバン", "PREMIUM BANDAI": "プレバン", "p-bandai": "プレバン", "ポケモンセンターオンライン": "ポケモンセンター"}


def norm_store(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[（(][^）)]*[）)]", "", s)  # カッコ内（アプリ名・地名など）は無視
    for a, b in STORE_ALIAS.items():
        s = s.replace(a, b)
    s = re.sub(r"[\s・\-]", "", s).lower()
    s = re.sub(r"(各店舗|各店|全店舗|全店|全国)$", "", s)   # 「古本市場 各店」＝「古本市場」
    return re.sub(r"(.{3,}?)\1+", r"\1", s)              # 「古本市場・ふるいち」→「古本市場古本市場」→「古本市場」


def norm_product(s):
    """商品名そのもの（カッコの中も見る。「御三家（フシギダネ）」と「御三家（チコリータ）」は別物）"""
    s = re.sub(r"\b1/(144|100|60|48|550)\b", "", unicodedata.normalize("NFKC", s or ""))   # ガンプラの縮尺（「HG 1/144 〇〇」＝「HG 〇〇」）
    return re.sub(r"[\s・「」]", "", s).lower()


def norm_series(s, aliases):
    """弾・商品名の「核」だけ残す（カッコの補足・「1BOX」「拡張パック」などの共通の言葉は無視）
    例：「ピカピカボックス2027（5,500円税込・お1人様1回まで）」＝「ピカピカボックス2027」、「30th CELEBRATION 1BOX」＝「30th CELEBRATION」"""
    s = (aliases.get(s) or s or "")
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[(\[【][^)\]】]*[)\]】]", "", s)
    s = re.sub(r"ポケモンカードゲーム|ポケモンカード|one ?piece ?カードゲーム|mega|強化拡張パック|拡張パック|ブースターパック|"
               r"エクストラブースター|\d+ ?box|box|ボックス|抽選販売|抽選|販売|予約", "", s)
    ex = _extra_strip()
    if ex:
        s = re.sub(ex, "", s, flags=re.I)
    return re.sub(r"[\s・「」『』\-/]", "", s)


def _url_key(u):
    """応募ページのURLをそろえる。?code=… のように抽選を区別する部分は残し、utm_ など追跡用だけ外す
    （抽選ロトボックスなどは ?code= が違うだけで全部別の抽選）"""
    from urllib.parse import urlsplit, parse_qsl, urlencode
    if not u:
        return ""
    p = urlsplit(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not re.match(r"^(utm_|fbclid|gclid|s$|t$|ref$|a$)", k)]
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/") + ("?" + urlencode(sorted(q)) if q else ""))


def _skey(it):
    x = it.get("series") or it.get("product")
    if SITE == "game":  # ゲーム・ホビー版は弾のまとめ（sitegen の設定）を使わない
        return norm_series(x, {})
    try:
        from sitegen import item_series
        x = "/".join(sorted(item_series(it.get("game"), x, it.get("product")) or [x]))  # 2つの弾をまとめた抽選は、両方の名前で比べる
    except Exception:
        pass
    return norm_series(x, {})


XURL = re.compile(r"//(www\.|mobile\.)?(x|twitter)\.com/")


def _rank(it):
    """残す優先度（大きいほど残す）"""
    return (bool(it.get("manual")),                                          # 自分で追加した抽選（個別ページのURLを変えないため）
            bool(it.get("url")) and not re.search(r"//(www\.|mobile\.)?(x|twitter)\.com/", it.get("url") or ""),   # 店の応募ページがある
            str(it.get("source", "")).startswith("カード抽選"),              # 整理済みのデータ
            it.get("status") in ("approved", "posted", "listed"),
            len(it.get("conditions") or ""))


def _different_item(a, b):
    """1つの応募ページで別々の商品を受け付けている（例：あみあみの「BOX」と「デッキセット」）なら True。
    両方に弾名があり、弾名が違い、どちらの商品名にも相手の弾名が入っていない時だけ"""
    if not (a.get("series") and b.get("series")) or _skey(a) == _skey(b):
        return False
    for x, y in ((a, b), (b, a)):
        core = norm_series(x.get("series"), {})
        if not core:
            continue  # 「MEGA」のように共通の言葉だけの弾名は比べられない
        if core in norm_series(y.get("product"), {}) or core in norm_series(y.get("series"), {}):
            return False
    return True


def dedupe(settings=None):
    s = settings or load_settings()
    # 弾名はサイトと同じ名前にそろえてから比べる（楽天用の別名は使わない：vol.2 と vol.1 が同じになってしまうため）
    lots = load_json("lotteries.json", {})
    # 以前「同じ応募ページ」というだけで別の商品にまとめてしまった抽選を元に戻す
    for k, it in lots.items():
        t = lots.get(it.get("duplicate_of") or "")
        if (it.get("status") == "duplicate" and t and t.get("status") in ACTIVE and not it.get("manual")
                and it.get("url") and _url_key(it.get("url")) == _url_key(t.get("url"))
                and not re.search(r"amazon|amzn", it.get("url") or "", re.I)
                and _different_item(it, t)
                and norm_store(it.get("store")) == norm_store(t.get("store"))
                and (it.get("end") or "")[:10] == (t.get("end") or "")[:10]
                and not (it.get("end") and it["end"] < __import__("datetime").datetime.now().astimezone().isoformat())):
            it["status"] = t["status"] if t["status"] in ("approved", "listed", "posted") else "approved"
            it.pop("duplicate_of", None)
            log(f"重複を戻しました: {it.get('store')} / {it.get('product')}")
    # まとめた抽選の空欄（発表日など）を、まとめられた側から補う（前は補っていなかった）
    filled = 0
    for k, it in lots.items():
        t = lots.get(it.get("duplicate_of") or "")
        if it.get("status") == "duplicate" and t:
            for f in ("announce", "buy", "conditions", "address"):
                if not t.get(f) and it.get(f):
                    t[f] = it[f]
                    filled += 1
            # ほかの情報元（Xの誰かのポストなど）で本人確認・会員の有無が分かっていれば、それで埋める
            for f in ("id_check", "member"):
                if t.get(f) is None and it.get(f) is not None:
                    t[f] = it[f]
                    filled += 1
            tg = list(t.get("tags") or [])
            for x in it.get("tags") or []:
                if x in ("本人確認", "会員", "アプリ", "購入履歴", "レシート", "店舗クレカ") and x not in tg:
                    tg.append(x)
                    filled += 1
            t["tags"] = tg
    # 11/10：応募先が他人のXのポストになっている抽選は、同じ抽選（同じ店・弾・締切日）の別の記録に
    # お店の応募ページがあれば、そちらに差し替える（はじかれた記録も見る。Xのポストは x_post に残す）
    official = {}
    for k, it in lots.items():
        u = it.get("url") or ""
        if it.get("end") and u.startswith("http") and not XURL.search(u):
            official.setdefault((it.get("game"), norm_store(it.get("store")), _skey(it), it["end"][:10]), u)
    fixed = 0
    for k, it in lots.items():
        if it.get("status") in ACTIVE and it.get("end") and XURL.search(it.get("url") or ""):
            u = official.get((it.get("game"), norm_store(it.get("store")), _skey(it), it["end"][:10]))
            if u:
                it["x_post"] = it.get("x_post") or it["url"]
                it["url"] = u
                fixed += 1
    if fixed:
        log(f"重複: 応募先がXのポストだった{fixed}件を、お店の応募ページに差し替え")
    groups = {}
    for k, it in lots.items():
        if it.get("status") not in ACTIVE or not it.get("end"):
            continue
        g = (it.get("game"), norm_store(it.get("store")), _skey(it), it["end"][:10], it.get("kind") if SITE == "game" else None)
        groups.setdefault(g, []).append(k)
    n = 0

    def merge(keep_k, k):
        nonlocal n
        keep, d = lots[keep_k], lots[k]
        if XURL.search(keep.get("url") or "") and d.get("url") and not XURL.search(d["url"]):
            keep["x_post"] = keep.get("x_post") or keep["url"]
            keep["url"] = d["url"]  # お店の応募ページを優先
        for f in ("area", "conditions", "url", "x_post", "image", "end", "apply_url",
                  "announce", "buy", "start", "method", "address"):  # 残す方の空欄を補う（発表日も：結果ページの「今日発表」に使う）
            if not keep.get(f) and d.get(f):
                keep[f] = d[f]
        for f in ("id_check", "member"):
            if keep.get(f) is None and d.get(f) is not None:
                keep[f] = d[f]
        tg = list(keep.get("tags") or [])
        for x in d.get("tags") or []:
            if x in ("本人確認", "会員", "アプリ", "購入履歴", "レシート", "店舗クレカ") and x not in tg:
                tg.append(x)
        keep["tags"] = tg
        d["status"], d["duplicate_of"] = "duplicate", keep_k
        n += 1

    for keys in groups.values():
        if len(keys) < 2:
            continue
        man = [k for k in keys if lots[k].get("manual")]
        if man:  # 自分で追加した抽選があれば、ほかはそこにまとめる（個別ページのURLを変えないため）
            for k in keys:
                if k != man[0]:
                    merge(man[0], k)
            continue
        # cardchusen の抽選は1件ずつ別の抽選（同じ店・同じ弾・同じ日でも、セット違い・会員限定などがある）。
        # 商品名まで同じものだけまとめる
        cc = [k for k in keys if str(lots[k].get("source", "")).startswith("カード抽選")]
        others = [k for k in keys if k not in cc]
        by_prod = {}
        for k in sorted(cc, key=lambda k: _rank(lots[k]), reverse=True):
            p = norm_product(lots[k].get("product"))
            if p in by_prod:
                merge(by_prod[p], k)
            else:
                by_prod[p] = k
        # X・入荷Nowなどから拾った同じ抽選は、cardchusen の方（無ければ一番くわしいもの）にまとめる
        others.sort(key=lambda k: _rank(lots[k]), reverse=True)
        target = (sorted(by_prod.values(), key=lambda k: _rank(lots[k]), reverse=True) or others)[0]
        for k in others:
            if k != target:
                merge(target, k)
    # 締切が分からないまま拾った抽選（Xなど）は、同じ店・同じ弾の抽選があればそちらにまとめる
    # （まとめ先が無ければ、締切なし同士で1件に）
    full = {}
    for k, it in lots.items():
        if it.get("status") in ACTIVE:
            full.setdefault((it.get("game"), norm_store(it.get("store")), _skey(it), it.get("kind") if SITE == "game" else None), []).append(k)
    for keys in full.values():
        if len(keys) < 2:
            continue
        noend = [k for k in keys if not lots[k].get("end") and not str(lots[k].get("source", "")).startswith("カード抽選")
                 and not re.search(r"amazon|amzn", (lots[k].get("url") or "") + (lots[k].get("store") or ""), re.I)
                 and lots[k].get("kind") not in NO_DEADLINE_KINDS]
        if not noend:
            continue
        rest = [k for k in keys if k not in noend]
        target = sorted(rest or noend, key=lambda k: (bool(lots[k].get("end")), _rank(lots[k])), reverse=True)[0]
        for k in noend:
            if k != target and lots[k].get("status") != "duplicate":
                merge(target, k)

    # Amazon は同じ弾を1件に（一番上の招待の券にまとめて出すので、何件あっても同じ）。商品ページ（/dp/）のあるものを残す
    amz = {}
    for k, it in lots.items():
        if it.get("status") in ACTIVE and re.search(r"amazon|amzn", (it.get("url") or "") + (it.get("store") or ""), re.I):
            amz.setdefault((it.get("game"), norm_product(it.get("product"))), []).append(k)
    for keys in amz.values():
        keys.sort(key=lambda k: ("/dp/" in (lots[k].get("url") or ""), _rank(lots[k])), reverse=True)
        for k in keys[1:]:
            merge(keys[0], k)

    # 同じ応募ページ（LivePocket・フォームなど）から別々に拾った抽選は、カード抽選まとめの方にまとめる
    # （Xから拾った方は店名が「朝霞」のように短かったり締切が空だったりするので、店名・締切ではまとまらない）
    by_url = {}
    for k, it in lots.items():
        u = _url_key(it.get("url"))
        if it.get("status") in ACTIVE and u and not re.search(r"(^|[/.])(x|twitter)\.com/|amazon\.|amzn\.", u):
            by_url.setdefault((it.get("game"), u), []).append(k)
    for keys in by_url.values():
        keys = [k for k in keys if lots[k].get("status") in ACTIVE]
        man = [k for k in keys if lots[k].get("manual")]
        if man:
            for k in keys:
                if k != man[0]:
                    merge(man[0], k)
            continue
        cc = [k for k in keys if str(lots[k].get("source", "")).startswith("カード抽選")]
        others = [k for k in keys if k not in cc]
        if not cc and len(others) > 1:  # どちらもXなどから拾った時は、弾ごとに一番くわしい方に
            others.sort(key=lambda k: (bool(lots[k].get("end")), _rank(lots[k])), reverse=True)
            cc = []
            for k in others:
                if not cc or all(_different_item(lots[k], lots[c]) for c in cc):
                    cc.append(k)
            others = [k for k in others if k not in cc]
        if not cc or not others:
            continue
        for k in others:
            sk = _skey(lots[k])
            same = [c for c in cc if _skey(lots[c]) == sk]
            if not same and all(_different_item(lots[k], lots[c]) for c in cc):
                continue  # 1つのフォームで別々の商品を受け付ける抽選（例：あみあみの「BOX」と「デッキセット」）は別の抽選
            merge(sorted(same or cc, key=lambda c: _rank(lots[c]), reverse=True)[0], k)
    if n or filled or fixed:
        save_json("lotteries.json", lots)
        log(f"重複: {n}件をまとめました")
    return n
