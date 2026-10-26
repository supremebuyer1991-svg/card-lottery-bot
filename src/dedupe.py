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


def norm_series(s, aliases):
    s = (aliases.get(s) or s or "")
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s・「」]", "", s).lower()


def _rank(it):
    """残す優先度（大きいほど残す）"""
    return (bool(it.get("url")) and "x.com" not in (it.get("url") or ""),   # 店の応募ページがある
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
        for f in ("area", "conditions", "url", "x_post", "image"):  # 残す方の空欄を補う
            if not keep.get(f) and d.get(f):
                keep[f] = d[f]
        d["status"], d["duplicate_of"] = "duplicate", keep_k
        n += 1

    for keys in groups.values():
        if len(keys) < 2:
            continue
        # cardchusen の抽選は1件ずつ別の抽選（同じ店・同じ弾・同じ日でも、セット違い・会員限定などがある）。
        # 商品名まで同じものだけまとめる
        cc = [k for k in keys if str(lots[k].get("source", "")).startswith("カード抽選")]
        others = [k for k in keys if k not in cc]
        by_prod = {}
        for k in sorted(cc, key=lambda k: _rank(lots[k]), reverse=True):
            p = norm_series(lots[k].get("product"), {})
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
    if n:
        save_json("lotteries.json", lots)
        log(f"重複: {n}件をまとめました")
    return n
