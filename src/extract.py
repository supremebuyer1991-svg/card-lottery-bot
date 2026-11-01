"""Claude APIで、ページ本文から抽選情報を構造化して取り出す"""
import json
import os
import re

import requests

from common import fix_game
from common import now, log

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

PROMPT = """あなたはトレカ抽選情報の抽出係です。以下のテキストから「現在受付中、またはこれから受付が始まる、{game_name}の商品の抽選販売・抽選予約」だけを抜き出してください。

ルール:
- 大会・イベント参加の抽選、プレゼントキャンペーン、受付終了済みのものは除外
- テキストに書かれていない情報は推測せず null にする（日付を作らない）
- 日時はISO 8601形式（例 2026-11-02T23:59:00+09:00）。年が省略されていれば今日（{today}）基準で補う
- 「今日 20:59」「明日 23:59」「残り15時間」のような書き方は、現在時刻（{nowtime}）を基準に日時へ直す
- url は応募ページか店舗の告知ページ（[関連リンク]に店舗のURLがあれば必ずそれを使う）。無ければ記事URL
- 「=====」で区切られた各ブロックは別々の抽選。応募URL があればそれを url にする。「商品:」の行があればそれが商品名
- まとめ記事の場合、記事内の「抽選」の項目を店舗ごとに1件ずつ出す。「在庫あり」「先着販売」「再販」は抽選ではないので除外
- テキストがXのポストの場合、店舗や公式アカウント本人の告知を優先し、個人の伝聞・噂は confidence を低く。x_post にはそのポストURLを入れる
- 実店舗の抽選も対象。channel は受け取り方法で決める：当選品が自宅に発送されるなら "online"、受け取り・購入が店頭のみなら "store"（応募がWeb・アプリ・SNSでも店頭受け取りなら store）。store は「チェーン名＋支店名」（例: イオン〇〇店）、area は店名や地名から分かる都道府県
- confidence は 0〜1。店舗名・商品名・締切がそろって明記されていれば高く

出力は次のJSON配列のみ（該当なしなら []）:
[{{"store":"店舗名","product":"商品名","series":"弾・商品シリーズ名だけ（例: 拡張パック「〇〇」BOX → 〇〇。分からなければ null）","start":"受付開始 or null","end":"受付締切 or null","announce":"当選発表 or null","method":"アプリ/Web/店頭 など or null","conditions":"会員限定など応募条件の要約 or null","url":"URL or null","x_post":"告知ポストのURL or null","game":"pokemon / onepiece / dragonball のどれか","channel":"online または store","area":"実店舗の都道府県 or null","id_check":"本人確認が必要なら true、不要と明記なら false、書かれていなければ null","member":"会員カード提示が必要なら card、会員登録（アカウント）が必要なら account、不要と明記なら none、書かれていなければ null","tags":["応募に必要なものを次から選ぶ: 会員, アプリ, 本人確認, 購入履歴, レシート, 店舗クレカ（そのお店のクレジットカードを持っていることが条件。支払い方法がクレカなだけなら入れない）, SNS応募, 整理券"],"confidence":0.0}}]

出典: {source_name} ({source_url})
--- テキスト ---
{text}
"""


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


def extract(text: str, game: str, game_name: str, source_name: str, source_url: str) -> list:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定です")
    prompt = PROMPT.format(game_name=game_name, today=now().date().isoformat(), nowtime=now().strftime("%Y-%m-%d %H:%M"),
                           source_name=source_name, source_url=source_url, text=text[:15000])
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
    valid = ("pokemon", "onepiece", "dragonball")
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
    return [i for i in items if i["game"] in valid]
