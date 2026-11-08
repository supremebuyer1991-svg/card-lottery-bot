"""Claude APIで、ページ本文から抽選情報を構造化して取り出す"""
import json
import os
import re

import requests

from common import fix_game
from common import now, log

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

# AIへの指示（トレカ：src/prompts/tcg_extract.txt ／ ゲーム・ホビー：src/prompts/game_extract.txt）
from pathlib import Path as _P
from common import SITE as _SITE
PROMPT = (_P(__file__).with_name("prompts") / f"{_SITE}_extract.txt").read_text(encoding="utf-8")


def _parse(raw: str) -> list:
    """AIの返事からJSONを取り出す。途中で切れていても、完成している分は救出する"""
    m = re.search(r"\[.*\]", raw, re.S)
    data = None
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, list):
        data, dec, i = [], json.JSONDecoder(), 0
        while True:
            i = raw.find("{", i)
            if i < 0:
                break
            try:
                obj, end = dec.raw_decode(raw, i)
                data.append(obj)
                i = end
            except json.JSONDecodeError:
                i += 1
    out = []
    for d in data:
        if not isinstance(d, dict) or not d.get("store"):
            continue
        if not d.get("product") and d.get("series"):
            d["product"] = d["series"]  # 商品名が無ければ弾名で代用
        if d.get("product"):
            out.append(d)
    return out


def valid_games():
    """抽選データの game に入れてよい値。トレカは3つ固定、ゲーム・ホビーは categories.yaml の有効なカテゴリ"""
    if _SITE == "game":
        import gamecats
        return tuple(gamecats.by_id())
    return ("pokemon", "onepiece", "dragonball")


def _category_list():
    """ゲーム・ホビー版の指示に入れるカテゴリの一覧（id＝名前）。トレカの指示には無い項目なので空"""
    if _SITE != "game":
        return ""
    import gamecats
    return "、".join(f"{c['id']}（{c.get('name') or c['id']}）" for c in gamecats.categories())


def extract(text: str, game: str, game_name: str, source_name: str, source_url: str) -> list:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定です")
    prompt = PROMPT.format(game_name=game_name, today=now().date().isoformat(), nowtime=now().strftime("%Y-%m-%d %H:%M"),
                           source_name=source_name, source_url=source_url, text=text[:15000], category_list=_category_list())
    r = requests.post(API_URL, timeout=90, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": MODEL, "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}: {r.text[:300]}")
    res = r.json()
    raw = "".join(b.get("text", "") for b in res.get("content", []))
    items = _parse(raw)
    if not items:
        log(f"  ※AIの返事（先頭）: {raw[:150]!r}")
    if res.get("stop_reason") == "max_tokens":
        log(f"  ※AIの返事が長すぎて途中で切れました（救出 {len(items)}件）")
    valid = valid_games()
    for it in items:
        # Xの検索は別のゲームの投稿も混ざるので、投稿の中身からAIが判定したゲームを優先する
        from_x = source_name.startswith("X")
        if it.get("game") not in valid or (game != "auto" and not from_x):
            it["game"] = game
        if it["game"] not in valid:
            continue
        fix_game(it)  # 商品名がはっきり別のゲームなら直す
        it["source"] = source_name
        it["source_url"] = source_url
        it["url"] = it.get("url") or it.get("x_post") or source_url
    if _SITE == "game":
        from gamecats import KINDS
        for it in items:
            if it.get("kind") not in KINDS:
                it["kind"] = "lottery"
    return [i for i in items if i["game"] in valid]
