"""抽選結果（当選発表）の情報を拾う

・新しくXを読むことはしない。抽選を探すために読んだポスト（collect.py）の中から、
  「抽選結果を発表しました」「当選者の方へメールを送りました」のようなお店・公式の発表だけを選ぶ
・お店・個人・まとめアカウントのポストを参考に、AIで「お店・商品・結果が出た日（出る日）・確かめ方」だけを取り出す
  （本文の写し・他人のXやAmazonへのリンクはサイトに出さない）
・state/results.json に残す（30日分）。サイトの /kekka/ と results.json に出し、Xの予約作業が読む
"""
import json
import re
from datetime import timedelta

from common import load_json, save_json, now, normalize, parse_dt, log

KEEP_DAYS = 30

# 結果の発表らしい言葉
HIT = re.compile(r"(抽選結果|当選者|当選された|当選のお客様|当選番号|当選発表|当選メール|当選連絡|当選のご連絡|当選の方|当選者様|当選者さま)")
# 「発表した・送った」など、もう出たことを表す言葉
DONE = re.compile(r"(しました|いたしました|致しました|しております|お送り|送信|ご連絡|掲載|公開|発表です|発表中|出ました|きました|来ました|届い|確認できます|ご確認ください|下記|以下|こちら|予定|明日|発表日|出る)")
# 抽選の受付の告知（結果ではない）。個人の当選報告・発表予定はAIが読み分ける
NOT = re.compile(r"(受付期間|応募期間|受付中|応募方法|応募受付|応募はこちら|応募締切|締切)")
GAME_WORDS = {"pokemon": re.compile(r"(ポケカ|ポケモンカード|ポケモンセンター|ポケセン|MEGA|ハドウシーカー|30th)"),
              "onepiece": re.compile(r"(ワンピ|ONE ?PIECE|ヒロインズ|神の支配)", re.I)}


def is_result(body: str) -> bool:
    return bool(HIT.search(body) and DONE.search(body) and not NOT.search(body))


def _parse(text):
    """fetch_x.search の文（投稿者・日時・本文・リンク・ポストURL）を分ける"""
    m = re.match(r"投稿者: (.*?) \(@(\w+)\)\n日時: (.*?)\n(.*)\nリンク: (.*)\nポストURL: (\S+)", text, re.S)
    if not m:
        return None
    name, handle, at, body, links, url = m.groups()
    return {"author": name, "handle": handle, "at": at, "body": body.strip(),
            "links": [x for x in links.split() if x.startswith("http")], "post": url}


def _handle(u):
    m = re.search(r"x\.com/(\w+)/status/", u or "") or re.search(r"twitter\.com/(\w+)/status/", u or "")
    return m.group(1).lower() if m else None


def _is_store(author, store):
    """ポストしたアカウントの名前に、お店（またはチェーン）の名前が入っているか。
    抽選の告知を個人が紹介したポストもあるので、アカウントが一致するだけでは「お店本人」と決めない"""
    a = normalize(author or "").replace(" ", "")
    core = normalize(re.sub(r"[（(][^）)]*[）)]", "", store or "")).replace(" ", "")
    names = {core} | {w for w in re.split(r"[・/]", core) if len(w) >= 3}
    try:
        from sitegen import chain_of, CHAIN
        c = chain_of(store)
        if c:
            names.add(normalize(CHAIN[c][1]).replace(" ", ""))
    except Exception:
        pass
    return any(len(n) >= 3 and n in a for n in names)


def _match(p, game, lots):
    """どの抽選の結果か。締切が過ぎた（か近い）抽選から、アカウント → お店の名前 の順で探す"""
    t = now()
    cand = []
    for it in lots.values():
        if it.get("status") in ("duplicate", "rejected") or not it.get("store"):
            continue
        if game and it.get("game") != game:
            continue
        end = parse_dt(it.get("end"))
        if not end or not (t - timedelta(days=21) <= end <= t + timedelta(days=1)):
            continue
        cand.append(it)
    # お店本人のアカウント（その抽選を告知したアカウント）のポストだけを使う。
    # 個人の当選報告や、ほかのまとめアカウントのポストを「結果発表」として載せない
    h = p["handle"].lower()
    hit = [i for i in cand if _handle(i.get("x_post")) == h and _is_store(p["author"], i["store"])]
    if not hit:
        return []
    # 弾の名前がポストに出ていればそれに絞る
    ser = [i for i in hit if i.get("series") and normalize(i["series"]) in normalize(p["body"])]
    return ser or hit


RPROMPT = """あなたはトレカの抽選結果（当選発表）の情報を整理する係です。下のXのポスト（お店・個人・まとめアカウントのものが混ざる）を読んで、
「どのお店の、どの商品の抽選の結果が、いつ・どこで分かるか」だけを取り出してください。本文をそのまま写さないこと。

ルール:
- 対象はポケモンカード（pokemon）とワンピースカード（onepiece）の商品の抽選だけ。
- kind: すでに結果が出た・当選連絡が送られた＝"done"、これから発表される予定（「明日発表」など）＝"scheduled"。
- 個人の「当たった・外れた」報告でも、お店の結果が出たことが分かるなら "done" として使ってよい（個人名は書かない）。
- まとめアカウントの「明日の動き」のように複数のお店が並んでいれば、お店ごとに1件ずつ出す。店名が「ほか」「各店」で分からない分は出さない。
- store は「チェーン名＋支店名」（例: ときわ書房 本八幡スクエア店）。分からなければその件は出さない。
- series は弾・商品の名前だけ（例: Heroines Edition vol.2、30th CELEBRATION）。分からなければ null。
- date は結果が出た日・出る日（YYYY-MM-DD）。今日は {today}。書かれていなければ、done は今日、scheduled は null。
- check は結果の確かめ方を短く（例: 「メール」「アプリ」「Webのマイページ」「店頭の掲示」「お店のホームページ」）。分からなければ null。
- check_url は、お店・公式の結果確認ページのURLがポストのリンクにあればそれ。X・Amazon・楽天・アフィリエイト・短縮URL（t.co）・まとめブログは入れない。無ければ null。
- 結果発表と関係ないポストからは何も出さない。

出力はJSON配列だけ:
[{{"post": 番号, "kind": "done|scheduled", "game": "pokemon|onepiece", "store": "...", "series": "...", "date": "YYYY-MM-DD", "check": "...", "check_url": "..."}}]

ポスト:
{posts}"""

BAD_URL = re.compile(r"(x\.com|twitter\.com|t\.co/|amazon\.|amzn\.|rakuten\.|a8\.net|moshimo|valuecommerce|linksynergy|accesstrade|"
                     r"mikeco-room|cardchusen|nyuka-now|ameblo|hatenablog|livedoor)", re.I)


def _ask(posts):
    """結果発表らしいポストをまとめてAIに読ませ、お店・商品・日付・確かめ方だけを取り出す"""
    import os
    import requests
    from extract import API_URL, MODEL, _parse as _p0
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return []
    txt = "\n\n".join(f"[{n}] 投稿者: {p['author']}\n日時: {p['at']}\n{p['body']}\nリンク: {' '.join(p['links'])}" for n, p in enumerate(posts))
    r = requests.post(API_URL, timeout=90, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 3000,
                            "messages": [{"role": "user", "content": RPROMPT.format(today=now().date().isoformat(), posts=txt[:12000])}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}: {r.text[:200]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        out = json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        out = []
    return [o for o in out if isinstance(o, dict) and o.get("store") and o.get("game") in GAME_WORDS
            and o.get("kind") in ("done", "scheduled")]


def scan(posts, src, lots=None, ask=None):
    """collect.py で読んだXのポストから結果発表の情報を拾い、AIで「お店・商品・日付・確かめ方」だけにして results.json に足す。
    ポストの本文やリンク（他人のX・Amazonなど）はサイトに出さない。足した数を返す"""
    data = load_json("results.json", {})
    seen = set(data.get("_posts") or [])
    cand = []
    for text, _ in posts:
        p = _parse(text)
        if not p or p["post"] in seen or not is_result(p["body"]):
            continue
        cand.append(p)
    if not cand:
        return 0
    try:
        got = (ask or _ask)(cand[:10])
    except Exception as e:
        log(f"抽選結果の読み取り失敗: {e}")
        return 0
    added = 0
    items = data.setdefault("items", {})
    for o in got:
        d = str(o.get("date") or "")[:10] if re.match(r"\d{4}-\d\d-\d\d", str(o.get("date") or "")) else (
            now().date().isoformat() if o["kind"] == "done" else "")
        if not d:
            continue
        store = re.sub(r"\s+", " ", str(o["store"])).strip()[:40]
        series = (str(o.get("series") or "").strip() or None)
        k = f'{o["game"]}|{normalize(store)}|{normalize(series or "")}|{d}'
        old = items.get(k) or {}
        cu = o.get("check_url") or old.get("check_url")
        if cu and (not str(cu).startswith("http") or BAD_URL.search(str(cu))):
            cu = None
        items[k] = {"game": o["game"], "store": store, "series": series, "date": d,
                    "kind": "done" if "done" in (o["kind"], old.get("kind")) else "scheduled",
                    "check": o.get("check") or old.get("check"), "check_url": cu,
                    "found_at": old.get("found_at") or now().isoformat()}
        if not old:
            added += 1
            log(f"抽選結果: {store}（{series or o['game']}）{d} {'発表済み' if items[k]['kind'] == 'done' else '発表予定'}")
    seen |= {p["post"] for p in cand}
    data["_posts"] = sorted(seen)[-500:]
    cut = (now() - timedelta(days=KEEP_DAYS)).date().isoformat()
    data["items"] = {k: v for k, v in items.items() if v["date"] >= cut}
    save_json("results.json", data)
    return added


def load_manual_results():
    """config/manual.yaml の results:（自分で見つけた結果発表。ゲオのお知らせなど）"""
    try:
        import yaml
        from common import ROOT
        p = ROOT / "config" / "manual.yaml"
        rows = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("results") or [] if p.exists() else []
    except Exception as e:
        log(f"手動の抽選結果: 読めません {e}")
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("store") or r.get("game") not in GAME_WORDS or not r.get("date"):
            continue
        d = str(r["date"])[:10]
        cu = r.get("check_url")
        out.append({"game": r["game"], "store": str(r["store"]), "series": (str(r.get("series") or "").strip() or None),
                    "date": d, "kind": r.get("kind") if r.get("kind") in ("done", "scheduled") else "done",
                    "check": r.get("check"), "check_url": cu if cu and str(cu).startswith("http") else None,
                    "found_at": d + "T00:00:00+09:00", "manual": True})
    return out


def current():
    """サイトに出す結果発表の一覧（新しい日付順）
    ・Xで見つけた発表 ＋ manual.yaml の results:
    ・「発表予定」だった分も、その日を過ぎていれば「結果が出た」として扱う"""
    data = load_json("results.json", {})
    its = dict(data.get("items") if isinstance(data.get("items"), dict) else {})
    for r in load_manual_results():
        its[f'{r["game"]}|{normalize(r["store"])}|{normalize(r["series"] or "")}|{r["date"]}'] = r
    today = now().date().isoformat()
    out = []
    for v in its.values():
        if v.get("kind") == "scheduled" and v.get("date") and v["date"] < today:
            v = dict(v, kind="done")
        out.append(v)
    return sorted(out, key=lambda v: (v["date"], v.get("found_at") or ""), reverse=True)


def from_announce(lots=None, days=14):
    """お店の告知に書いてあった「当選発表日」を過ぎた抽選（Xで発表が見つからなくても、結果は出ているはず）。
    発表日が分かっている分だけ。今日の分は時間が分からないので入れない"""
    lots = lots if lots is not None else load_json("lotteries.json", {})
    t = now().date()
    lo, today = (t - timedelta(days=days)).isoformat(), t.isoformat()
    out = {}
    for it in lots.values():
        if it.get("status") in ("duplicate", "rejected") or it.get("game") not in GAME_WORDS:
            continue
        a = announce_date(it)
        if not a or not (lo <= a < today):
            continue
        ser = it.get("series")
        try:
            from sitegen import canon_series
            ser = (canon_series(it["game"], ser) or [ser])[0] if ser else None
        except Exception:
            pass
        k = (it["game"], normalize(it.get("store")), normalize(ser or ""), a)
        txt = str(it.get("announce") or "")
        m = re.search(r"[（(]([^）)]{2,30})[）)]", txt)
        out.setdefault(k, {"game": it["game"], "store": it.get("store"), "series": ser, "date": a, "kind": "done",
                           "check": m.group(1) if m else None, "check_url": None,
                           "found_at": a + "T00:00:00+09:00", "est": True})
    return list(out.values())


def scheduled_today(lots=None):
    """今日が「当選発表日」になっている抽選（お店の告知に書いてあった発表日）"""
    lots = lots if lots is not None else load_json("lotteries.json", {})
    today = now().date().isoformat()
    out = {}
    for it in lots.values():
        if it.get("status") in ("duplicate", "rejected") or announce_date(it) != today:
            continue
        k = (it["game"], normalize(it.get("store")))
        out.setdefault(k, {"game": it["game"], "store": it.get("store"), "series": set()})
        if it.get("series"):
            try:
                from sitegen import canon_series  # サイトと同じ弾名に（「EB-05」→「ヒロインズエディション vol.2」など）
                out[k]["series"].update(canon_series(it["game"], it["series"]) or [it["series"]])
            except Exception:
                out[k]["series"].add(it["series"])
    return [dict(v, series=sorted(v["series"])) for v in out.values()]



def announce_date(it):
    """抽選の「当選発表」の書き方（「2026-11-04」「11/4(水)23時頃」「11月21日(土)〜店頭掲示」など）から日付（YYYY-MM-DD）を読む。
    年が書かれていなければ、締切（なければ見つけた日）の年。締切より前の月なら翌年。読めなければ None"""
    a = str(it.get("announce") or "")
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", a)
    if m:
        return m.group(0)
    if re.search(r"(、|／|/.*:.*/)", a) and len(re.findall(r"\d{1,2}\s*[/月]\s*\d{1,2}", a)) > 1:
        return None  # 商品ごとに発表日が違う書き方は使わない
    m = re.search(r"(\d{1,2})\s*[/月]\s*(\d{1,2})", a)
    if not m:
        return None
    base = parse_dt(it.get("end")) or parse_dt(it.get("found_at")) or now()
    from datetime import date
    try:
        d = date(base.year, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None
    if d < base.date() - timedelta(days=1):
        try:
            d = date(base.year + 1, d.month, d.day)
        except ValueError:
            return None
    return d.isoformat()
