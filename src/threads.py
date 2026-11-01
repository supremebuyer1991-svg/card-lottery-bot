"""Threads（@tcg-chusen）への自動投稿。Threads の公式API（無料）を使う

・GitHub の Secret「THREADS_ACCESS_TOKEN」にアクセストークンを入れると動く（無ければ何もしない）
・投稿するもの（Xと同じ流れ。ボットの実行は毎時17分なので、その時刻の回で出す）
    7時台  … 今日締切の抽選（ゲームごと）
    12時台 … 新着の抽選（前の日の17時以降に見つかった分）
    17時台 … 新着の抽選（お昼以降に見つかった分。3店以上たまった時だけ）
    20時台 … あと数時間で締切
    21時台 … Amazonの招待リクエスト受付中の商品（#PR・アソシエイトのリンク付き）
    いつでも … 新しく見つかった抽選を、お店ごとに1件ずつ速報（個別ページのリンク付き。1回15件まで）
    いつでも … 大手（⭐チェーン＋通販大手）の通販（発送）の抽選の速報（見つけて20分〜3時間のもの。チェーン×弾で1回）
・アクセストークンは約60日で切れるので、20日ごとに自動で延長する。延長したトークンは state に暗号化して保存する
  （うまくいかない時は Discord にお知らせ）
・Threads は1投稿500文字まで。ハッシュタグ（トピック）は1つだけ付く
"""
import base64
import hashlib
import json
import os
import re
import time
from datetime import timedelta

import requests

from common import load_json, save_json, log, now, parse_dt

API = "https://graph.threads.net/v1.0"
GAME = {"pokemon": ("ポケカ", "pokeka", "#ポケモンカード"), "onepiece": ("ワンピースカード", "onepiece", "#ワンピースカード")}
WEEK = "月火水木金土日"
FOLLOW = "🔔フォローで抽選の開始・締切のお知らせが届きます"
LIMIT = 500


# ---- トークン（延長したものを暗号化して保存）----
def _key():
    return hashlib.sha256(("tcg-threads|" + os.environ.get("THREADS_ACCESS_TOKEN", "")).encode()).digest()


def _xor(data: bytes) -> bytes:
    k = _key()
    stream = b"".join(hashlib.sha256(k + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return bytes(a ^ b for a, b in zip(data, stream))


def _token(meta):
    enc = meta.get("token_enc")
    if enc:
        try:
            t = _xor(base64.b64decode(enc)).decode()
            if t.isprintable() and len(t) > 20:
                return t
        except Exception:
            pass
    return os.environ.get("THREADS_ACCESS_TOKEN", "").strip()


def _refresh(meta, tok):
    """20日ごとにトークンを延長（作ってから24時間たっていないと延長できない）"""
    last = parse_dt(meta.get("refreshed_at"))
    if last and now() - last < timedelta(days=20):
        return tok
    if not last and not meta.get("first_seen"):
        meta["first_seen"] = now().isoformat()
        meta["refreshed_at"] = now().isoformat()  # 最初の回は延長しない（できたばかりのトークンは延長できない）
        return tok
    r = requests.get(f"{API.rsplit('/', 1)[0]}/refresh_access_token",
                     params={"grant_type": "th_refresh_token", "access_token": tok}, timeout=20)
    if r.status_code == 200 and r.json().get("access_token"):
        new = r.json()["access_token"]
        meta["token_enc"] = base64.b64encode(_xor(new.encode())).decode()
        meta["refreshed_at"] = now().isoformat()
        log("Threads: アクセストークンを延長しました")
        return new
    log(f"Threads: トークンの延長に失敗 {r.status_code} {r.text[:200]}")
    _alert(meta, "Threadsの鍵（アクセストークン）の延長に失敗しました。期限が切れる前に、Meta for Developers で新しいトークンを作って、GitHubの THREADS_ACCESS_TOKEN を入れ直してください。")
    return tok


def _alert(meta, msg):
    """Discord に1日1回だけお知らせ"""
    today = now().date().isoformat()
    if meta.get("alerted") == today:
        return
    hook = "".join(os.environ.get("DISCORD_WEBHOOK_URL", "").split())
    if hook:
        try:
            requests.post(hook, json={"content": "⚠️ " + msg, "username": "トレカ抽選ナビ"}, timeout=20)
        except Exception:
            pass
    meta["alerted"] = today


def publish(tok, text, _retry=True):
    """テキストを1件投稿（コンテナを作る → 公開）。投稿IDを返す。
    リンクのカードが作れなかった（Invalid Link Attachment）時は、少し待ってリンクを明示してもう1回"""
    try:
        return _publish(tok, text, None if _retry else re.search(r"https://\S+", text).group(0))
    except RuntimeError as e:
        if _retry and "4279047" in str(e) and re.search(r"https://\S+", text):
            time.sleep(15)
            return publish(tok, text, _retry=False)
        raise


def _publish(tok, text, link=None):
    data = {"media_type": "TEXT", "text": text[:LIMIT], "access_token": tok}
    if link:
        data["link_attachment"] = link
    r = requests.post(f"{API}/me/threads", data=data, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"作成 {r.status_code} {r.text[:200]}")
    cid = r.json()["id"]
    time.sleep(1.5)  # 作ってから少し待って公開（長く待つとGitHubの動く時間が増える）
    r = requests.post(f"{API}/me/threads_publish", data={"creation_id": cid, "access_token": tok}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"公開 {r.status_code} {r.text[:200]}")
    return r.json().get("id")


# ---- 投稿文 ----
def _name(i):
    from xdraft import _name as n
    return n(i)


def _hm(e):
    return f"{e:%H:%M}"


def _md(e):
    return f"{e.month}/{e.day}({WEEK[e.weekday()]})"


def _group(items):
    """同じお店はまとめる。同じチェーンの同じ商品は「ビックカメラ（8店舗）」のように1行に：[(代表の抽選, [商品名...])]"""
    from sitegen import chain_of, CHAIN
    out, seen = [], {}
    for i in items:
        c = chain_of(i.get("store"))
        k = f"c:{c}" if c else re.sub(r"\s", "", i.get("store") or "")
        if k in seen:
            if c and re.sub(r"\s", "", i.get("store") or "") not in seen[k][4]:
                seen[k][2] += 1
                seen[k][4].add(re.sub(r"\s", "", i.get("store") or ""))
            if _name(i) not in seen[k][1]:
                seen[k][1].append(_name(i))
            continue
        seen[k] = [i, [_name(i)], 1, CHAIN[c][1] if c else None, {re.sub(r"\s", "", i.get("store") or "")}]
        out.append(seen[k])
    res = []
    for i, names, n, cname, _ in out:
        if cname and n > 1:
            i = dict(i, store=f"{cname}（{n}店舗）")
        res.append((i, names))
    return res


def _fit(head, rows, tail):
    """500文字に入るだけお店を入れる。入らなかった分は「ほか〇店」"""
    body = []
    for n_, r in enumerate(rows):
        rest = len(rows) - n_ - 1
        cand = "\n".join([head, ""] + body + [r] + ([f"・ほか{rest}店"] if rest else []) + ["", tail])
        if len(cand) > LIMIT:
            body.append(f"・ほか{len(rows) - n_}店")
            break
        body.append(r)
    return "\n".join([head, ""] + body + ["", tail]) if body else ""


def _open_items(lots, game, t):
    from notify import _is_open
    return [i for i in lots.values() if i.get("game") == game and _is_open(i, t)]


def compose_today(game, lots, t):
    label, slug, tag = GAME[game]
    li = sorted([i for i in _open_items(lots, game, t) if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == t.date()
                 and parse_dt(i["end"]) > t + timedelta(hours=1)], key=lambda i: i["end"])
    rows = [f"・{i['store'].strip()}（{_hm(parse_dt(i['end']))}まで）\n　{n[0]}{f' ほか{len(n) - 1}種' if len(n) > 1 else ''}"
            for i, n in _group(li)]
    return _fit(f"☀️今日締切｜{label}の抽選（{_md(t)}）", rows,
                f"ほかのお店・応募方法はこちら👇\nhttps://tcg-chusen.com/{slug}/\n\n{FOLLOW}\n{tag}") if rows else ""


def compose_soon(game, lots, t):
    label, slug, tag = GAME[game]
    li = sorted([i for i in _open_items(lots, game, t) if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == t.date()
                 and parse_dt(i["end"]) > t + timedelta(minutes=50)], key=lambda i: i["end"])
    rows = []
    for i, n in _group(li):
        e = parse_dt(i["end"])
        rows.append(f"・{i['store'].strip()}（{_hm(e)}まで／あと約{max(1, round((e - t).total_seconds() / 3600))}時間）\n　{n[0]}{f' ほか{len(n) - 1}種' if len(n) > 1 else ''}")
    return _fit(f"⏰あと数時間で締切｜{label}の抽選", rows,
                f"まだの人は今のうちに👇\nhttps://tcg-chusen.com/{slug}/\n\n{FOLLOW}\n{tag}") if rows else ""


def compose_new(game, lots, t, since, min_stores=1, head_note=""):
    label, slug, tag = GAME[game]
    li = [i for i in _open_items(lots, game, t) if parse_dt(i.get("found_at")) and parse_dt(i["found_at"]) >= since
          and not re.search(r"amazon", i.get("store") or "", re.I)
          and (not parse_dt(i.get("end")) or parse_dt(i["end"]) > t + timedelta(hours=1))]
    li.sort(key=lambda i: i.get("found_at") or "", reverse=True)
    g = _group(li)
    if len(g) < min_stores:
        return ""
    rows = []
    for i, n in g:
        e = parse_dt(i.get("end"))
        rows.append(f"・{i['store'].strip()}（{(_md(e) + ' ' + _hm(e) + 'まで') if e else '締切は告知で確認'}）\n　{n[0]}{f' ほか{len(n) - 1}種' if len(n) > 1 else ''}")
    return _fit(f"🆕新着の抽選｜{label}{head_note}", rows,
                f"締切・応募方法はこちら👇\nhttps://tcg-chusen.com/{slug}/\n\n{FOLLOW}\n{tag}")


def compose_amazon(game, lots, t, settings):
    """Amazonの招待リクエスト受付中の商品（リンクは自分のアソシエイトのタグ付き。1投稿のリンクは5つまでなので商品は4つまで）"""
    from sitegen import amazon_invites
    tag = os.environ.get("AMAZON_TAG") or settings.get("amazon_tag")
    rows = amazon_invites(_open_items(lots, game, t), tag).get(game) or []
    rows = [r for r in rows if "/dp/" in (r.get("url") or "")][:4]
    if not rows:
        return ""
    label, slug, tagname = GAME[game]
    lines = [f"📦Amazon 招待リクエスト受付中｜{label}（{_md(t)}）", ""]
    for r in rows:
        lines += [f"・{r['name']}", r["url"]]
    lines += ["", "⚠️人によっては、招待メールが届いていないのに招待されている場合があります。当選しているのに購入が漏れないよう、商品ページを定期的に確認するのがおすすめです",
              "", f"ほかの抽選はこちら👇\nhttps://tcg-chusen.com/{slug}/", f"{tagname} #PR"]
    text = "\n".join(lines)
    while len(text) > LIMIT and len(rows) > 1:  # 長すぎたら商品を減らす
        i = lines.index(rows[-1]["url"])
        del lines[i - 1:i + 1]
        rows = rows[:-1]
        text = "\n".join(lines)
    return text


def _big_posts(lots, t, done):
    """大手の通販の抽選の速報（Xの post_big と同じ選び方）"""
    from xpost import big_chain, short_product, fmt_dt
    from detail import lottery_path
    from sitegen import series_path
    groups = {}
    for i in lots.values():
        if i.get("status") not in ("approved", "listed", "posted") or i.get("game") not in GAME or i.get("channel") == "store":
            continue
        f, e = parse_dt(i.get("found_at")), parse_dt(i.get("end"))
        if not f or not (timedelta(minutes=20) <= t - f <= timedelta(hours=3)) or (e and e < t + timedelta(hours=1)):
            continue
        bc = big_chain(i.get("store"))
        if bc:
            groups.setdefault((bc[0], bc[1], i["game"], i.get("series") or short_product(i)), []).append(i)
    out = []
    for (slug, name, game, series), items in groups.items():
        key = f"big|{slug}|{game}|{series}"
        if key in done:
            continue
        items.sort(key=lambda i: i.get("end") or "9")
        first = items[0]
        link = f"https://tcg-chusen.com/{lottery_path(first)}" if len(items) == 1 else f"https://tcg-chusen.com/{series_path(game, series)}"
        end = f"⏰{fmt_dt(first.get('end'))} 締切" if first.get("end") else "⏰締切はお店の告知で確認"
        text = "\n".join([f"🚨抽選速報｜{GAME[game][0]}", "", f"{name}で「{series}」の抽選", "",
                          f"📍{first['store']}（通販・発送）", end, "", "応募条件・方法はこちら👇", link, "", FOLLOW, GAME[game][2]])
        out.append((key, text))
    return out


def _each_posts(lots, t, done):
    """新しく見つかった抽選を、お店ごとに1件ずつ速報（大手の通販は _big_posts で出すので除く）。
    サイトの個別ページが公開されてから出す（見つけて20分〜6時間のもの）"""
    from notify import _is_open, _sig
    from xpost import big_chain, fmt_dt
    from detail import lottery_path
    groups = {}
    for i in lots.values():
        if i.get("game") not in GAME or not _is_open(i, t):
            continue
        f = parse_dt(i.get("found_at"))
        if not f or not (timedelta(minutes=20) <= t - f <= timedelta(hours=6)):
            continue
        e = parse_dt(i.get("end"))
        if e and e < t + timedelta(hours=1):
            continue
        if i.get("channel") != "store" and big_chain(i.get("store")):
            continue
        k = f"each|{_sig(i)}"
        if k not in done:
            groups.setdefault(k, i)
    out = []
    for k, i in sorted(groups.items(), key=lambda kv: kv[1].get("found_at") or ""):
        label = GAME[i["game"]][0]
        store = (i.get("store") or "").strip()
        where = (f"{i['area']}・店頭受取" if i.get("area") else "店頭受取") if i.get("channel") == "store" else "通販・発送"
        need = []
        if i.get("id_check") is True:
            need.append("本人確認")
        if i.get("member") == "card":
            need.append("会員カード")
        elif i.get("member") == "account":
            need.append("会員登録")
        end = f"⏰{fmt_dt(i.get('end'))} 締切" if i.get("end") else "⏰締切はお店の告知で確認"
        lines = [f"🚨抽選速報｜{label}", "", f"「{_name(i)}」", f"📍{store}（{where}）", end]
        if need:
            lines.append("📝必要：" + "・".join(need))
        lines += ["", "応募条件・方法はこちら👇", f"https://tcg-chusen.com/{lottery_path(i)}", "", FOLLOW, GAME[i["game"]][2]]
        out.append((k, "\n".join(lines)))
    return out


def run(settings):
    if not os.environ.get("THREADS_ACCESS_TOKEN") or not settings.get("threads_post", True):
        return
    meta = load_json("threads_meta.json", {})
    t = now()
    today = t.date().isoformat()
    done = meta.setdefault("done", {})
    for k in [k for k, v in done.items() if parse_dt(v) and t - parse_dt(v) > timedelta(days=3)]:
        done.pop(k)
    tok = _token(meta)
    try:
        tok = _refresh(meta, tok)
    except Exception as e:
        log(f"Threads: トークン延長でエラー {e}")
    if meta.get("checked") != today:  # 1日1回、鍵が使えるか（どのアカウントか）を確かめてログに出す
        try:
            r = requests.get(f"{API}/me", params={"fields": "username", "access_token": tok}, timeout=20)
            log(f"Threads: 鍵の確認 {r.status_code} {r.json().get('username') if r.status_code == 200 else r.text[:150]}")
            if r.status_code == 200:
                meta["checked"] = today
            else:
                _alert(meta, "Threadsの鍵（アクセストークン）が使えません。Meta for Developers で新しいトークンを作って、GitHubの THREADS_ACCESS_TOKEN を入れ直してください。")
        except Exception as e:
            log(f"Threads: 鍵の確認でエラー {e}")
    lots = load_json("lotteries.json", {})
    posts = []
    h = t.hour
    yday = (t - timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
    noon = t.replace(hour=11, minute=45, second=0, microsecond=0)
    for game in GAME:
        if h == 7:
            posts.append((f"{today}|today|{game}", compose_today(game, lots, t)))
        elif h == 12:
            posts.append((f"{today}|new12|{game}", compose_new(game, lots, t, yday)))
        elif h == 17:
            posts.append((f"{today}|new17|{game}", compose_new(game, lots, t, noon, min_stores=3, head_note="（お昼から）")))
        elif h == 20:
            posts.append((f"{today}|soon|{game}", compose_soon(game, lots, t)))
        elif h == 21:  # 夜、人が見やすい時間に1日1回（ユーザーの依頼）
            posts.append((f"{today}|amazon|{game}", compose_amazon(game, lots, t, settings)))
    posts += _big_posts(lots, t, done)
    if settings.get("threads_each", True):
        posts += _each_posts(lots, t, done)[:settings.get("threads_each_per_run", 15)]
    sent = 0
    for key, text in posts:
        if not text or key in done:
            continue
        if settings.get("dry_run"):
            log("DRY_RUN Threads:\n" + text)
            continue
        try:
            publish(tok, text)
        except Exception as e:
            log(f"Threads: 投稿失敗 {e}")
            if '"code":190' in str(e) or " 401 " in str(e):
                _alert(meta, "Threadsに投稿できませんでした（鍵が切れているかもしれません）。Meta for Developers で新しいトークンを作って、GitHubの THREADS_ACCESS_TOKEN を入れ直してください。")
            break
        done[key] = t.isoformat()
        sent += 1
        time.sleep(1)
    if sent:
        log(f"Threads: {sent}件投稿")
    save_json("threads_meta.json", meta)
