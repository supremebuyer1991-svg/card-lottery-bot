"""1日1回、リンクなしの「反応してもらう」投稿（バズ狙い）

・Xはリンク付きの投稿を表示されにくくするので、あえてリンクを付けない（プロフィールのサイトへ誘導）
・内容はいま受付中の抽選の実際の数字から作る（ランキング・質問・数字・地域・あるある）
・型は日ごとに順番に変える。数字が足りない型は飛ばして次の型にする
・buzz_hour 時〜その3時間後のあいだに1回だけ（取りこぼしたら、その日は出さない）
"""
import os
import re
from collections import Counter

from common import load_json, save_json, parse_dt, now, log
from xpost import x_len, _client

ACTIVE = ("approved", "posted", "listed")
SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピカード", "dragonball": "フュージョンワールド"}

ARUARU = [
    ["締切の5分前に気づく", "会員カードが必要で詰む", "当選メールが迷惑メールに入ってる"],
    ["応募したこと自体を忘れる", "当選してから受け取り期限に焦る", "近所の店だけ抽選がない"],
    ["本人確認書類を家に忘れる", "落選メールだけ届くのが早い", "家族全員で応募して全滅"],
    ["アプリのログインで手間取る", "整理券に並んだのに抽選", "当たった時だけ予定が合わない"],
]


def _active(lots):
    t = now()
    return [i for i in lots.values() if i.get("status") in ACTIVE
            and not (parse_dt(i.get("end")) and parse_dt(i["end"]) < t)]


def _store_key(i):
    return re.sub(r"\s", "", i.get("store") or "")


def _series_rank(items, game):
    c = Counter()
    seen = set()
    for i in items:
        if i.get("game") != game or not i.get("series"):
            continue
        k = (i["series"], _store_key(i))
        if k not in seen:
            seen.add(k)
            c[i["series"]] += 1
    return c.most_common(3)


def _ranking(items, day, tags):
    g = ["pokemon", "onepiece"][day % 2]
    top = _series_rank(items, g)
    if len(top) < 3:
        return None
    medals = ["🥇", "🥈", "🥉"]
    body = "\n".join(f"{medals[n]}{s}｜{c}店舗" for n, (s, c) in enumerate(top))
    return f"いま抽選している店舗が多い弾（{SHORT[g]}）\n\n{body}\n\n1位はさすがに強い\n\n{tags[g]}"


def _question(items, day, tags):
    g = ["onepiece", "pokemon"][day % 2]
    top = _series_rank(items, g)
    if not top or top[0][1] < 3:
        return None
    s, c = top[0]
    return (f"「{s}」の抽選\n\n"
            f"いま分かってるだけで{c}店舗が受付中。\n\n"
            f"ここまで多いと、どれか1つは当たってほしい🙏\n\n{tags[g]}")


def _numbers(items, day, tags):
    t = now()
    today = [i for i in items if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == t.date()]
    if len(items) < 10:
        return None
    net = sum(1 for i in items if i.get("channel") == "online")
    lines = [f"今日の時点で、トレカの抽選は全国で{len(items)}件受付中。", "",
             f"・家から応募できるネット抽選：{net}件", f"・お店で受け取る店頭抽選：{len(items) - net}件"]
    if today:
        lines += ["", f"そのうち今日締切が{len(today)}件⏰"]
    lines += ["", "締切は思ってるより早く来る", "", "#ポケカ抽選 #ワンピカード抽選"]
    return "\n".join(lines)


def _prefecture(items, day, tags):
    c = Counter(i["area"] for i in items if i.get("channel") == "store" and i.get("area"))
    top = c.most_common(3)
    if len(top) < 3:
        return None
    body = "\n".join(f"{n + 1}位 {p}｜{k}件" for n, (p, k) in enumerate(top))
    return (f"店頭抽選がいちばん多い都道府県は…\n\n{body}\n\n"
            f"近くに店がない人は、ネット抽選のほうが狙い目\n\n#ポケカ抽選 #ワンピカード抽選")


def _aruaru(items, day, tags):
    a = ARUARU[(day // 5) % len(ARUARU)]
    return "トレカ抽選あるある\n\n" + "\n".join("・" + x for x in a) + "\n\n全部やったことある😂\n\n#ポケカ #ワンピカード"


TYPES = [_ranking, _question, _numbers, _prefecture, _aruaru]


def compose_buzz(lots, settings, day=None):
    items = _active(lots)
    day = now().toordinal() if day is None else day
    tags = settings.get("hashtags", {})
    for k in range(len(TYPES)):
        f = TYPES[(day + k) % len(TYPES)]
        text = f(items, day, tags)
        if text and x_len(text) <= 280:
            return f.__name__.strip("_"), text
    return None, None


def post_buzz(settings, client=None):
    hour = settings.get("buzz_hour")
    if hour is None:  # 未設定＝オフ
        return
    t = now()
    if not (hour <= t.hour < hour + 3):
        return
    meta = load_json("x_meta.json", {})
    today = t.date().isoformat()
    if meta.get("buzz_date") == today:
        return
    kind, text = compose_buzz(load_json("lotteries.json", {}), settings)
    if not text:
        return
    dry = settings.get("dry_run") or (client is None and not os.environ.get("X_API_KEY"))
    if dry:
        log("DRY_RUN バズ投稿:\n" + text)
        return
    if client is None:
        client = _client()
    try:
        client.create_tweet(text=text)
    except Exception as e:
        log(f"バズ投稿失敗: {e}")
        if "duplicate" not in str(e).lower():
            return  # 失敗（重複以外）は次の実行でもう一度
    else:
        log(f"バズ投稿OK（{kind}）")
    meta["buzz_date"] = today
    meta["buzz_last"] = {"kind": kind, "text": text}
    save_json("x_meta.json", meta)
