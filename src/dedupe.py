"""同じ抽選の重複をまとめる（別々の情報元から同じ抽選を拾った時）

同じゲーム・同じ店（チェーン名の表記ゆれをそろえる）・同じ弾・同じ締切日なら同じ抽選とみなし、
一番くわしいもの（応募ページがある・cardchusen由来・承認済み）を残して、ほかは status=duplicate にする。
"""
import re
import unicodedata

from common import load_json, save_json, log, load_settings

ACTIVE = ("new", "pending", "approved", "posted", "listed")
STORE_ALIAS = {"電機": "デンキ", "ヤマダ電器": "ヤマダデンキ", "ビックカメラ": "ビックカメラ", "ヨドバシカメラ": "ヨドバシ",
               "トイザらス": "トイザラス", "ツタヤ": "TSUTAYA", "ふるいち": "古本市場"}


def norm_store(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[（(][^）)]*[）)]", "", s)  # カッコ内（アプリ名・地名など）は無視
    for a, b in STORE_ALIAS.items():
        s = s.replace(a, b)
    return re.sub(r"[\s・\-]", "", s).lower()


def norm_product(s):
    """商品名そのもの（カッコの中も見る。「御三家（フシギダネ）」と「御三家（チコリータ）」は別物）"""
    return re.sub(r"[\s・「」]", "", unicodedata.normalize("NFKC", s or "")).lower()


def norm_series(s, aliases):
    """弾・商品名の「核」だけ残す（カッコの補足・「1BOX」「拡張パック」などの共通の言葉は無視）
    例：「ピカピカボックス2027（5,500円税込・お1人様1回まで）」＝「ピカピカボックス2027」、「30th CELEBRATION 1BOX」＝「30th CELEBRATION」"""
    s = (aliases.get(s) or s or "")
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[(\[【][^)\]】]*[)\]】]", "", s)
    s = re.sub(r"ポケモンカードゲーム|ポケモンカード|one ?piece ?カードゲーム|mega|強化拡張パック|拡張パック|ブースターパック|"
               r"エクストラブースター|\d+ ?box|box|ボックス|抽選販売|抽選|販売|予約", "", s)
    return re.sub(r"[\s・「」『』\-/]", "", s)


def _rank(it):
    """残す優先度（大きいほど残す）"""
    return (bool(it.get("manual")),                                          # 自分で追加した抽選（個別ページのURLを変えないため）
            bool(it.get("url")) and "x.com" not in (it.get("url") or ""),   # 店の応募ページがある
            str(it.get("source", "")).startswith("カード抽選"),              # 整理済みのデータ
            it.get("status") in ("approved", "posted", "listed"),
            len(it.get("conditions") or ""))


def dedupe(settings=None):
    s = settings or load_settings()
    aliases = s.get("rakuten_aliases") or {}
    lots = load_json("lotteries.json", {})
    groups = {}
    for k, it in lots.items():
        if it.get("status") not in ACTIVE or not it.get("end"):
            continue
        g = (it.get("game"), norm_store(it.get("store")), norm_series(it.get("series") or it.get("product"), aliases), it["end"][:10])
        groups.setdefault(g, []).append(k)
    n = 0

    def merge(keep_k, k):
        nonlocal n
        keep, d = lots[keep_k], lots[k]
        for f in ("area", "conditions", "url", "x_post", "image", "end", "apply_url"):  # 残す方の空欄を補う
            if not keep.get(f) and d.get(f):
                keep[f] = d[f]
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
            full.setdefault((it.get("game"), norm_store(it.get("store")), norm_series(it.get("series") or it.get("product"), aliases)), []).append(k)
    for keys in full.values():
        if len(keys) < 2:
            continue
        noend = [k for k in keys if not lots[k].get("end") and not str(lots[k].get("source", "")).startswith("カード抽選")
                 and not re.search(r"amazon|amzn", (lots[k].get("url") or "") + (lots[k].get("store") or ""), re.I)]
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
        u = (it.get("url") or "").split("?")[0].rstrip("/")
        if it.get("status") in ACTIVE and u and not re.search(r"(x|twitter)\.com/|amazon\.|amzn\.", u):
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
        if not cc and len(others) > 1:  # どちらもXなどから拾った時は、一番くわしい方に
            others.sort(key=lambda k: (bool(lots[k].get("end")), _rank(lots[k])), reverse=True)
            cc, others = others[:1], others[1:]
        if not cc or not others:
            continue
        for k in others:
            sk = norm_series(lots[k].get("series") or lots[k].get("product"), aliases)
            same = [c for c in cc if norm_series(lots[c].get("series") or lots[c].get("product"), aliases) == sk]
            merge(sorted(same or cc, key=lambda c: _rank(lots[c]), reverse=True)[0], k)
    if n:
        save_json("lotteries.json", lots)
        log(f"重複: {n}件をまとめました")
    return n
