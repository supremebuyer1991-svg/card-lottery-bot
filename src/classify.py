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
VERSION = 3  # 判定ルールを変えたら上げる（全件を判定し直す）

PROMPT = """トレカ抽選情報サイトの振り分け係です。各抽選について次の2つを判定してください。

1. channel
  - "online": 当選した商品が自宅に発送される（通販サイト・ECショップ・オンラインストアの抽選。Amazon、楽天、ヨドバシ.com、ポケモンセンターオンライン、〇〇通販、BASE店 など）
  - "store": 商品の受け取り・購入が店頭のみ（実店舗の支店名がある抽選。応募がWeb・アプリ・X・LINEでも、当選後に来店して購入・受け取りするものは store。「購入券」「購入権」「当選者は店頭で購入」「来店」も store）
  - 支店名（〇〇店、〇〇駅前、〇〇モール店 など）がある実店舗で、発送・配送と書かれていなければ store
2. area（channel が store のときだけ）
  - 店名・支店名・カッコ内の地名・駅名・市区町村名・商業施設名（ららぽーと〇〇、イオンモール〇〇 など）から都道府県を判定する。
    一般的に知られている地名・施設なら積極的に判定してよい（例: シーガル名取店→宮城県、タムタム神戸三宮店→兵庫県、ブックオフ横浜中山店→神奈川県、
    ジャスティス（大阪）→大阪府、キデイランド富士見／ららぽーと富士見店→埼玉県、ビックカメラ名古屋駅西店→愛知県、宝島岐阜本店→岐阜県）
  - 一覧の中に同じ店の別表記で都道府県が分かるものがあれば、それに合わせる
  - 複数の都道府県にまたがる「各店」や、地名がまったく無いものだけ null
3. multi（channel が store のときだけ）
  - 1つの抽選が複数の店舗で行われる（「〇〇各店」「A店・B店」「全店」など）なら true、1店舗なら false

出力は JSON 配列のみ: [{{"id": 番号, "channel": "online または store", "area": "都道府県 or null", "multi": true}}]（multi は true か false）

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
    # 1件ずつ取り出す（JSON全体が少し崩れていても、読める行は使う）
    out, dec, i = [], json.JSONDecoder(), 0
    while True:
        i = raw.find("{", i)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(raw, i)
            if isinstance(obj, dict) and "id" in obj:
                out.append(obj)
            i = end
        except json.JSONDecodeError:
            i += 1
    if not out:
        log(f"振り分け: AIの返事を読めませんでした {raw[:120]!r}")
    return out


def load_overrides():
    """config/channel_overrides.yaml：人が確認した決まり（店名 → online / store）"""
    import yaml
    from common import ROOT
    p = ROOT / "config" / "channel_overrides.yaml"
    if not p.exists():
        return {}
    y = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = {}
    for ch in ("online", "store"):
        for name in y.get(ch) or []:
            out[str(name).strip()] = ch
    return out


def load_area_overrides():
    """config/area_overrides.yaml：店名 → 都道府県"""
    import yaml
    from common import ROOT
    p = ROOT / "config" / "area_overrides.yaml"
    return {str(k).strip(): v for k, v in ((yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}).items() if v in PREFS}


def apply_overrides(lots, ov):
    n = 0
    areas = load_area_overrides()
    from common import fix_game
    for it in lots.values():
        if fix_game(it):  # ポケカに入ったワンピースの商品などを直す
            n += 1
        # 都道府県の書き方をそろえる（東京→東京都、大阪→大阪府 など）。都道府県でない値は消す
        ar = (it.get("area") or "").strip()
        if ar and ar not in PREFS:
            fixed = next((p for p in PREFS if p.rstrip("都府県") == ar.rstrip("都府県") and ar.rstrip("都府県")), None)
            it["area"] = fixed
            n += 1
        a = areas.get((it.get("store") or "").strip())
        if a and it.get("area") != a:
            it["area"] = a
            if it.get("channel") != "online":
                it["channel"] = "store"
            n += 1
        ch = ov.get((it.get("store") or "").strip())
        if ch and it.get("channel") != ch:
            it["channel"] = ch
            if ch == "online":
                it["area"] = None
            n += 1
    return n


def classify(settings, ask=None, batch=40, max_batches=20):
    """未判定の抽選だけをAIで判定して lotteries.json に書き戻す。戻り値: 変更した件数"""
    lots = load_json("lotteries.json", {})
    ov = load_overrides()
    changed = apply_overrides(lots, ov)  # 人が確認した決まりが最優先
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            if changed:
                save_json("lotteries.json", lots)
            return changed
        ask = _ask
    todo = [it for it in lots.values() if it.get("status") in ACTIVE and it.get("cls") != _fingerprint(it)]
    for b in range(min(max_batches, (len(todo) + batch - 1) // batch)):
        chunk = todo[b * batch:(b + 1) * batch]
        rows = "\n".join(
            f"{n}. 店舗: {it.get('store')} ／ 商品: {(it.get('product') or '')[:80]} ／ 応募方法: {it.get('method') or '-'}"
            f" ／ 条件: {(it.get('conditions') or '-')[:80]} ／ いまの判定: {it.get('channel') or '-'}"
            for n, it in enumerate(chunk))
        try:
            res = ask(rows)
        except Exception as e:
            log(f"振り分け: この{len(chunk)}件はスキップ {e}")
            if "401" in str(e) or "403" in str(e) or "credit" in str(e).lower():
                break  # 鍵や残高の問題なら、その回はやめる
            continue
        for r in res:
            try:
                it = chunk[int(r["id"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            ch = r.get("channel")
            if (it.get("store") or "").strip() in ov:
                ch = ov[(it.get("store") or "").strip()]  # 決まりがある店はAIの判定を使わない
            if ch in ("online", "store") and ch != it.get("channel"):
                log(f"振り分け: {it.get('store')} {it.get('channel')} → {ch}")
                it["channel"] = ch
                changed += 1
            if it.get("channel") == "store" and not it.get("area") and r.get("area") in PREFS:
                it["area"] = r["area"]
                changed += 1
            if it.get("channel") == "store" and isinstance(r.get("multi"), bool):
                it["multi"] = r["multi"]
            if it.get("channel") == "online":
                it["area"] = None
            it["cls"] = _fingerprint(it)
    # 同じ店（表記ゆれを除いて同名）で都道府県が分かっているものから補う
    norm = lambda s: re.sub(r"[\s　・()（）「」【】-]", "", s or "")
    known = {norm(i.get("store")): i["area"] for i in lots.values() if i.get("area") and i.get("channel") == "store"}
    for it in lots.values():
        if it.get("channel") == "store" and not it.get("area") and known.get(norm(it.get("store"))):
            it["area"] = known[norm(it.get("store"))]
            changed += 1
    if changed or todo:
        save_json("lotteries.json", lots)
    if todo:
        log(f"振り分け: 判定 {min(len(todo), max_batches * batch)}件 / 変更 {changed}件")
    return changed
