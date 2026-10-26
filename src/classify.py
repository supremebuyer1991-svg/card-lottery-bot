"""ネット抽選／店頭抽選の振り分けと、店頭抽選の都道府県の補完（AI）

基準（サイトの表示と同じ）:
  ネット抽選 = 当選した商品が自宅に「発送」される
  店頭抽選   = 商品の受け取り・購入が「店頭のみ」（応募がWeb・アプリ・SNSでも、受け取りが店頭なら店頭抽選）

cardchusen の「オンライン」は応募方法のことで、受け取り方法ではないため、ここで判定し直す。
判定済みの印（cls）を各抽選に付け、内容が変わらない限り二度と判定しない（費用をかけない）。
"""
import json
import os
import re

import requests

from common import load_json, save_json, sha, log
from extract import API_URL, MODEL

PREFS = ("北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 "
         "石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 "
         "岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県").split()
ACTIVE = ("new", "pending", "approved", "posted", "listed")
VERSION = 1  # 判定ルールを変えたら上げる（全件を判定し直す）

PROMPT = """トレカ抽選情報サイトの振り分け係です。各抽選について次の2つを判定してください。

1. channel
  - "online": 当選した商品が自宅に発送される（通販サイト・ECショップ・オンラインストアの抽選。Amazon、楽天、ヨドバシ.com、ポケモンセンターオンライン、〇〇通販、BASE店 など）
  - "store": 商品の受け取り・購入が店頭のみ（実店舗の支店名がある抽選。応募がWeb・アプリ・X・LINEでも、当選後に来店して購入・受け取りするものは store。「購入券」「購入権」「当選者は店頭で購入」「来店」も store）
  - 支店名（〇〇店、〇〇駅前、〇〇モール店 など）がある実店舗で、発送・配送と書かれていなければ store
2. area（channel が store のときだけ）
  - 店名・支店名・カッコ内の地名・商業施設名から都道府県を判定（例: シーガル名取店→宮城県、ホビーショップタムタム神戸三宮店→兵庫県、ブックオフ横浜中山店→神奈川県、ジャスティス（大阪）→大阪府）
  - 複数の都道府県にまたがる「各店」や、地名が無く判断できないものは null。推測に自信がなければ null

出力は JSON 配列のみ: [{{"id": 番号, "channel": "online または store", "area": "都道府県 or null"}}]

--- 抽選一覧 ---
{rows}
"""


def _fingerprint(it):
    return sha(json.dumps([VERSION, it.get("store"), it.get("product"), it.get("method"), it.get("conditions")],
                          ensure_ascii=False))[:12]


def _ask(rows):
    key = os.environ.get("ANTHROPIC_API_KEY")
    r = requests.post(API_URL, timeout=120, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": PROMPT.format(rows=rows)}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}: {r.text[:200]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\[.*\]", raw, re.S)
    return json.loads(m.group(0)) if m else []


def classify(settings, ask=None, batch=40, max_batches=6):
    """未判定の抽選だけをAIで判定して lotteries.json に書き戻す。戻り値: 変更した件数"""
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        ask = _ask
    lots = load_json("lotteries.json", {})
    todo = [it for it in lots.values() if it.get("status") in ACTIVE and it.get("cls") != _fingerprint(it)]
    changed = 0
    for b in range(min(max_batches, (len(todo) + batch - 1) // batch)):
        chunk = todo[b * batch:(b + 1) * batch]
        rows = "\n".join(
            f"{n}. 店舗: {it.get('store')} ／ 商品: {(it.get('product') or '')[:80]} ／ 応募方法: {it.get('method') or '-'}"
            f" ／ 条件: {(it.get('conditions') or '-')[:80]} ／ いまの判定: {it.get('channel') or '-'}"
            for n, it in enumerate(chunk))
        try:
            res = ask(rows)
        except Exception as e:
            log(f"振り分け: スキップ {e}")
            break
        for r in res:
            try:
                it = chunk[int(r["id"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            ch = r.get("channel")
            if ch in ("online", "store") and ch != it.get("channel"):
                log(f"振り分け: {it.get('store')} {it.get('channel')} → {ch}")
                it["channel"] = ch
                changed += 1
            if it.get("channel") == "store" and not it.get("area") and r.get("area") in PREFS:
                it["area"] = r["area"]
                changed += 1
            if it.get("channel") == "online":
                it["area"] = None
            it["cls"] = _fingerprint(it)
    if changed or todo:
        save_json("lotteries.json", lots)
    if todo:
        log(f"振り分け: 判定 {min(len(todo), max_batches * batch)}件 / 変更 {changed}件")
    return changed
