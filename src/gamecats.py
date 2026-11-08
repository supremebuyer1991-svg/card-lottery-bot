"""ゲーム・ホビー入荷速報のカテゴリ（config/game/categories.yaml）を読む

カテゴリを増やすときは YAML に1ブロック足すだけで、
  ・設定の game_names（AIの指示・ページ）
  ・ページのアドレス（slug）・短い名前・色・ハッシュタグ
  ・商品名からカテゴリを見分ける手がかり（hints）
  ・重複をまとめるときに無視する言葉（strip_words）
が全部ここから組み立てられる。
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "config" / "game" / "categories.yaml"

# 種類（kind）の表示名。release は「発売日・再販日」（お店ではなくメーカーの予定）
KINDS = {"lottery": "抽選", "invite": "招待", "preorder": "予約", "restock": "再入荷",
         "first_come": "先着", "fukubukuro": "福袋", "release": "発売・再販"}
# 受付の締切がない種類（再入荷・先着・発売日）は、締切ではなく見つけた日で区別する
NO_DEADLINE_KINDS = ("restock", "first_come", "release")

_CACHE = {}


def load(path=None):
    """{"groups": {...}, "categories": [...]}（enabled の無いものは true 扱い）"""
    p = Path(path) if path else PATH
    mt = p.stat().st_mtime if p.exists() else None
    if _CACHE.get("p") != str(p) or _CACHE.get("mt") != mt:
        y = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
        cats = []
        for c in (y or {}).get("categories") or []:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            c = dict(c)
            c.setdefault("enabled", True)
            c.setdefault("slug", c["id"].replace("_", "-"))
            c.setdefault("short", c.get("name") or c["id"])
            c.setdefault("group", "hobby")
            c.setdefault("kinds", list(KINDS))
            cats.append(c)
        _CACHE.update(p=str(p), mt=mt, v={"groups": dict((y or {}).get("groups") or {}), "categories": cats})
    return _CACHE["v"]


def categories(enabled_only=True):
    return [c for c in load()["categories"] if c["enabled"] or not enabled_only]


def by_id(enabled_only=True):
    return {c["id"]: c for c in categories(enabled_only)}


def groups():
    return load()["groups"]


def hints():
    """{カテゴリid: 正規表現}（有効なカテゴリだけ）"""
    out = {}
    for c in categories():
        if c.get("hints"):
            out[c["id"]] = re.compile(c["hints"], re.I)
    return out


def strip_words():
    """重複をまとめる時に無視する言葉（全カテゴリ分をまとめた正規表現の文字列）"""
    parts = [c["strip_words"] for c in categories() if c.get("strip_words")]
    return "|".join(parts)


def apply(s):
    """load_settings() の結果にカテゴリ由来の設定を足す（settings.yaml に同じ項目が書いてあればそちらを優先）"""
    cats = categories()
    s.setdefault("game_names", {})
    for c in cats:
        s["game_names"].setdefault(c["id"], c.get("name") or c["id"])
    # settings.yaml の game_names に、categories.yaml に無い（または無効の）カテゴリが残っていたら外す
    ids = {c["id"] for c in cats}
    s["game_names"] = {k: v for k, v in s["game_names"].items() if k in ids}
    s.setdefault("hashtags", {})
    for c in cats:
        if c.get("hashtags"):
            s["hashtags"].setdefault(c["id"], c["hashtags"])
    s["categories"] = cats
    s["category_groups"] = groups()
    return s
