"""サイトに載せるBOXの相場を1日2回読む（config/souba.yaml の商品だけ）

・朝（souba_hour・7時ごろ）：前日までの取引を読む
・夜（souba_eve_hour・21時ごろ）：その日の21時ごろまでの取引を読み、その日の値もサイトに出す
  （22:00・22:30のXの相場投稿と数字をそろえるため）

・スニダン：その日の「1個」の取引の平均（スニダンの相場グラフと同じ数字）。日本時間の日付ごと
・TCGplayer：アメリカの取引の相場（marketPrice・ドル）。アメリカ時間の日付ごと
・1件ずつ間をあけて読む。断られたら（403など）その日はあきらめる
・state/souba.json に日付ごとの値段を残す（60日分）
"""
import re
import time
from datetime import datetime, timedelta, timezone

import requests
import yaml

from common import ROOT, load_json, save_json, now, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
JST = timezone(timedelta(hours=9))
WAIT = 1.5  # 1件ずつの間（スニダンに負担をかけない範囲で短め。GitHubの使用時間を減らすため）
KEEP_DAYS = 400  # 1年前比のために400日分残す（40日より前は1週に1日だけにして軽くする）
DAILY_DAYS = 40


def _thin(d, today):
    """日付ごとの値段を軽くする：40日以内は毎日、それより前（400日まで）は1週間に1日（その週のいちばん新しい日）だけ"""
    from datetime import date
    t = date.fromisoformat(today)
    cut, daily = (t - timedelta(days=KEEP_DAYS)).isoformat(), (t - timedelta(days=DAILY_DAYS)).isoformat()
    out, weeks = {}, {}
    for k, v in sorted(d.items()):
        if k < cut:
            continue
        if k >= daily:
            out[k] = v
        else:
            weeks[date.fromisoformat(k).isocalendar()[:2]] = (k, v)
    out.update(dict(weeks.values()))
    return dict(sorted(out.items()))


def _ago(done, d0, days, slack=10):
    """d0 の days 日前（以前でいちばん近い日）の (日付, 値段)。データがそこまで無い・離れすぎなら None"""
    tgt = (datetime.fromisoformat(d0) - timedelta(days=days)).date()
    x = next((x for x in reversed(done) if x[0] <= tgt.isoformat()), None)
    if x and (tgt - datetime.fromisoformat(x[0]).date()).days > slack:
        return None
    return x
PAST_PER_RUN = 15  # 過去の弾は1回の実行で15件まで（朝7時すぎから1時間ごとに少しずつ読む）


def _cfg():
    p = ROOT / "config" / "souba.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}


def past_slugs():
    """過去の弾のページのアドレス（souba.yaml の slug）→ {ゲーム: {弾名: slug}}"""
    out = {}
    for g, lst in (_cfg().get("past") or {}).items():
        for x in lst or []:
            if x.get("slug"):
                out.setdefault(g, {})[x["series"]] = x["slug"]
    return out


def items(past=True):
    d = _cfg()
    out = []
    for g, lst in (d.get("items") or {}).items():
        for x in lst or []:
            out.append(dict(x, game=g))
    # 公式サイト・スニダンの検索から自動で見つけた新しい弾
    have = {(i["game"], i["series"]) for i in out}
    for k, aid in (load_json("newsets.json", {}).get("snkr") or {}).items():
        g, x = k.split("|", 1)
        if (g, x) not in have:
            out.append({"game": g, "series": x, "name": f"{x} BOX", "snkr": aid, "teika": _teika(g, x)})
            have.add((g, x))
    # 過去の弾（1日1回・少しずつ）
    if past:
        for g, lst in (d.get("past") or {}).items():
            for x in lst or []:
                if (g, x["series"]) not in have:
                    out.append(dict(x, game=g, past=True))
    return out


def _teika(g, x):
    """自動で見つけた弾の定価（BOX）。希望小売価格の「1BOX（30パック）6,000円」から。分からなければ None"""
    try:
        import newsets
        p = (newsets.merged_info().get(g) or {}).get(x, {}).get("price") or ""
    except Exception:
        return None
    m = re.search(r"1BOX[^0-9]*\d*[^0-9]*?([\d,]{4,})円", p)
    return int(m.group(1).replace(",", "")) if m else None


def _snkr_daily(sess, aid):
    """スニダンの商品番号 → {日付(YYYY-MM-DD): その日の1個の取引の平均}"""
    h = sess.get(f"https://snkrdunk.com/apparels/{aid}", timeout=30)
    h.raise_for_status()
    m = re.search(r'\\?"productId\\?":(\d+)', h.text)
    if not m:
        raise ValueError("productId が見つからない")
    pid = m.group(1)
    j = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all", timeout=30)
    j.raise_for_status()
    j = j.json()
    opt = next((o for o in ((j.get("filters") or {}).get("variants") or {}).get("options") or []
                if re.match(r"^1(個|パック|BOX|ボックス)", o.get("name") or "")), None)
    if opt:
        time.sleep(1)
        r = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all&variant_id={opt['id']}", timeout=30)
        r.raise_for_status()
        j = r.json()
    day = {}
    for p in (((j.get("chart") or {}).get("lines") or [{}])[0].get("points") or []):
        ts = p.get("timestamp")
        if ts is None or p.get("price") is None:
            continue
        ts = ts / 1000 if ts > 1e11 else ts
        day[datetime.fromtimestamp(ts, JST).date().isoformat()] = int(p["price"])
    return day


def _tcg_daily(sess, tid):
    """TCGplayerの商品番号 → {アメリカの日付: marketPrice(ドル)}。いちばん新しい日はまだ途中なので外す"""
    r = sess.get(f"https://infinite-api.tcgplayer.com/price/history/{tid}?range=month", timeout=30)
    r.raise_for_status()
    res = r.json().get("result") or []
    out = {}
    for d in res[1:]:
        v = (d.get("variants") or [{}])[0].get("marketPrice")
        if d.get("date") and v not in (None, ""):
            out[d["date"][:10]] = round(float(v), 2)
    return out


def _fx(sess):
    try:
        return round(float(sess.get("https://open.er-api.com/v6/latest/USD", timeout=20).json()["rates"]["JPY"]), 1)
    except Exception:
        return None


def update_souba(settings, sess=None, sleep=time.sleep, force=False):
    hour = settings.get("souba_hour", 7)
    eve_hour = settings.get("souba_eve_hour", 21)
    t = now()
    data = load_json("souba.json", {})
    today = t.date().isoformat()
    eve = t.hour >= eve_hour  # 夜の回：その日の21時ごろまでの値もサイトに出す
    store = data.setdefault("items", {})
    allit = items()
    main_due = force or (t.hour >= hour and (data.get("checked") != today or (eve and data.get("checked_eve") != today)))
    # 過去の弾：その日まだ読んでいないものを15件ずつ（朝7時すぎから）
    past = [it for it in allit if it.get("past") and it.get("snkr")
            and (store.get(f"{it['game']}|{it['series']}") or {}).get("day") != today] if t.hour >= hour else []
    past = past[:PAST_PER_RUN]
    if not main_due and not past:
        return 0
    if main_due:
        data["checked"] = today
        if eve:
            data["checked_eve"] = today
    sess = sess or requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    got = blocked = 0
    todo = ([it for it in allit if not it.get("past")] if main_due else []) + past
    for k, it in enumerate(todo):
        key = f"{it['game']}|{it['series']}"
        rec = store.setdefault(key, {})
        rec.update(name=it["name"], game=it["game"], series=it["series"], teika=it.get("teika"), snkr=it.get("snkr"))
        if it.get("past"):
            rec["past"] = True
        else:
            rec.pop("past", None)
        if it.get("snkr") and not blocked:
            if k:
                sleep(WAIT)
            try:
                rec["jp"] = {**(rec.get("jp") or {}), **_snkr_daily(sess, it["snkr"])}
                # 夜に読めた商品だけ、その日の値（21時ごろまで）をサイトに出す。朝の回・過去の弾は前日まで
                rec["thru"] = today if eve and not it.get("past") else (t.date() - timedelta(days=1)).isoformat()
                rec["day"] = today
                got += 1
            except requests.HTTPError as e:
                log(f"相場（スニダン）: {it['name']} 取得できず {e} → 今日はここまで")
                blocked = 1  # 断られたら続けない
            except Exception as e:
                log(f"相場（スニダン）: {it['name']} 取得失敗 {e}")
                if it.get("past"):
                    rec["day"] = today  # 過去の弾は読めなくても今日はもう試さない（ほかの弾を先に）
        if it.get("tcg") and main_due:
            try:
                rec["us"] = {**(rec.get("us") or {}), **_tcg_daily(sess, it["tcg"])}
            except Exception as e:
                log(f"相場（TCGplayer）: {it['name']} 取得失敗 {e}")
        for f in ("jp", "us"):
            if rec.get(f):
                rec[f] = _thin(rec[f], today)
    fx = _fx(sess)
    if fx:
        data["fx"] = fx
    if got:
        data["updated"] = t.isoformat()  # サイトの「相場の更新」の日時（数字が1つでも読めた時だけ進める）
    save_json("souba.json", data)
    log(f"相場（{'夜' if eve else '朝'}）: スニダン {got}/{sum(1 for i in todo if i.get('snkr'))}件"
        + (f"（過去の弾 {len(past)}件を含む）" if past else "") + (f"・1ドル={fx}円" if fx else ""))
    return got


def summary(rec, today=None):
    """サイトに出す数字：いちばん新しい日の相場・その前の日との差・7日前との差・定価との差・30日分の点"""
    jp = sorted((rec.get("jp") or {}).items())
    if not jp:
        return None
    today = today or now().date().isoformat()
    # 今日の分はまだ途中なので昨日までの値を使う。夜（21時ごろ）に読めた商品だけは今日の値まで使う
    upto = today if rec.get("thru") == today else None
    done = [x for x in jp if x[0] < today or x[0] == upto] or jp
    d0, v0 = done[-1]
    prev = done[-2] if len(done) > 1 else None
    wk = _ago(done, d0, 7, slack=3)
    pts = [(d, v) for d, v in done if d >= (datetime.fromisoformat(d0) - timedelta(days=30)).date().isoformat()]
    us = sorted((rec.get("us") or {}).items())
    out = {"date": d0, "price": v0, "teika": rec.get("teika"), "prev": prev, "week": wk,
           "month": _ago(done, d0, 30, slack=5), "year": _ago(done, d0, 365), "points": pts, "snkr": rec.get("snkr")}
    if len(us) >= 1:
        out["us"] = us[-1]
        out["us_prev"] = us[-2] if len(us) > 1 else None
        out["us_points"] = [(d, u) for d, u in us if pts and d >= pts[0][0]]  # グラフに重ねる海外の値（日本の線と同じ期間）
    return out


# ---------------- 主要シングルカードの相場（スニダン・状態A＝未鑑定の美品・1枚の取引の、その日の平均） ----------------
# config/souba_cards.yaml の弾ごとのカード（高いカードを数枚）を、朝7時すぎから1時間ごとに少しずつ、1日1回読む
# 写真とリンクは楽天の商品検索API（アフィリエイトのリンク）。メルカリは検索へのリンクだけ（写真は使わない）
CARD_REQ_PER_RUN = 60  # 1回の実行でスニダンを読む回数の上限（初めてのカードは4回、2回目からは状態AとPSA10で2回）。298枚×2回を1日（実際の実行は1日16回ほど）で回り切るため
COND_A = "trading_card_single_nearly_unused"
COND_PSA10 = "trading_card_single_psa10"  # 鑑定品 PSA10（取引が少ないので、いちばん新しい取引の日の値を出す）


def card_cfg():
    p = ROOT / "config" / "souba_cards.yaml"
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}
    return {k: [c for c in (v or []) if c.get("snkr")] for k, v in d.items()}


def _card_daily(sess, aid, rec, cond=COND_A):
    """カード1枚 → {日付: 状態Aの1枚の取引のその日の平均}。商品番号・1枚の番号は覚えておく（2回目からは1回読むだけ）"""
    if not rec.get("pid"):
        h = sess.get(f"https://snkrdunk.com/apparels/{aid}", timeout=30)
        h.raise_for_status()
        m = re.search(r'\\?"productId\\?":(\d+)', h.text)
        if not m:
            raise ValueError("productId が見つからない")
        rec["pid"] = int(m.group(1))
        time.sleep(1)
    pid = rec["pid"]
    if not rec.get("vid"):
        j = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all", timeout=30)
        j.raise_for_status()
        opt = next((o for o in ((j.json().get("filters") or {}).get("variants") or {}).get("options") or []
                    if re.match(r"^1(枚|個)$", o.get("name") or "")), None)
        rec["vid"] = opt["id"] if opt else 0
        time.sleep(1)
    q = f"&variant_id={rec['vid']}" if rec["vid"] else ""
    r = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all{q}&condition_code={cond}", timeout=30)
    r.raise_for_status()
    day = {}
    for p in (((r.json().get("chart") or {}).get("lines") or [{}])[0].get("points") or []):
        ts = p.get("timestamp")
        if ts is None or p.get("price") is None:
            continue
        ts = ts / 1000 if ts > 1e11 else ts
        day[datetime.fromtimestamp(ts, JST).date().isoformat()] = int(p["price"])
    return day


def _rakuten_card(settings, c, sess=None):
    """楽天でそのカードの商品を探す（写真・アフィリエイトリンク）。カード名と番号が両方合う商品だけ"""
    import os
    import rakuten
    name = re.sub(r"\s*[(:（].*$", "", c["label"]).strip()  # 「シャンクス SEC-SP (コミパラ)」→「シャンクス SEC-SP」
    num = (re.search(r"([A-Z]{2,4}\d{0,2}-\d{3}|\d{3}/\d{3})", c.get("num") or "") or [None, ""])[1]
    base = re.sub(r"\s+\S+$", "", name) if " " in name else name  # レアリティを外したカード名
    lab = c["label"]
    kinds = [  # (カード名にある印, 楽天の商品名に必要な言葉, 探すときに足す言葉)
        (r"SPC", r"スペシャル|SPC", "スペシャル"),
        (r"RSP|レッドコミパラ", r"レッド", "パラレル"),
        (r"GSP", r"ゴールド|GSP", ""),
        (r"コミパラ|SP\b|SP[ )]|スーパーパラレル", r"スーパーパラレル|コミパラ|コミックパラレル", "パラレル"),
        (r"-P\b|パラレル", r"パラレル", "パラレル"),
    ]
    kind = next((k for k in kinds if re.search(k[0], lab)), None)
    par = kind[2] if kind else ""
    q = " ".join(x for x in (base, num, par) if x)  # 楽天は言葉を全部ふくむ商品を探すので、レアリティの書き方の違いで外れないよう名前と番号だけ
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    if not num:  # 番号のないカード（ミュウ ブルー/レッド/グリーンなど）は名前だけでは別のカードの写真になるので、検索へのリンクだけ
        q2 = " ".join([name] + re.findall(r"[(（]([^)）]+)[)）]", lab))
        return {"image": "", "url": rakuten.search_link(q2, aff), "search": True, "fetched": now().date().isoformat()}
    items = rakuten.search(q, dict(settings, _genre=None, _sort="standard"))  # 30件
    # パラレル違い・ミラー違いを取り違えない（ワンピースは同じ番号でふつうのカードとパラレルがある）
    need, ng = [], []
    if kind:
        need.append(kind[1])
    elif c.get("num") and re.match(r"[A-Z]{2,4}\d{0,2}-\d{3}", c["num"]):
        ng.append(r"パラレル")
    for w in ("マスターボールミラー", "モンスターボールミラー"):
        if w in lab:
            need.append(w)
    if re.search(r"ミラー", lab) is None and re.search(r"ミラー", base) is None:
        ng.append(r"ボールミラー")
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    nb, nn = rakuten._norm(base), rakuten._norm(num)
    for it in items:
        nm = it.get("itemName") or ""
        n = rakuten._norm(nm)
        if nb not in n or (nn and nn not in n) or not it.get("mediumImageUrls"):
            continue
        if re.search(r"オリパ|英語版|韓国|中国|まとめ|セット売|ランダム|福袋|スリーブ|ローダー", nm):
            continue
        if any(not re.search(w, nm) for w in need) or any(re.search(w, nm) for w in ng):
            continue
        return {"image": rakuten._first_image(it), "url": rakuten.item_link(it.get("itemUrl") or it.get("affiliateUrl"), aff),
                "price": it.get("itemPrice"), "fetched": now().date().isoformat()}
    # 合う商品がないときも、楽天の検索結果（安い順）へのリンクを付ける（写真はなし）
    return {"image": "", "url": rakuten.search_link(q, aff), "search": True, "fetched": now().date().isoformat()}


def update_cards(settings, sess=None, sleep=time.sleep, budget=CARD_REQ_PER_RUN, rk_budget=60):
    """主要カードの相場を少しずつ読む（1日1回）。楽天の写真は7日ごとに取り直す"""
    import os
    t = now()
    today = t.date().isoformat()
    if t.hour < settings.get("souba_hour", 7):
        return 0
    cfg = card_cfg()
    data = load_json("souba_cards.json", {})
    # GitHubの使用時間を減らすため：状態Aは2日に1回、PSA10（取引が少ない）は7日に1回だけ読む
    due_a = (t.date() - timedelta(days=settings.get("card_every_days", 2) - 1)).isoformat()
    due_psa = (t.date() - timedelta(days=settings.get("card_psa_every_days", 7) - 1)).isoformat()
    todo, used, waiting = [], 0, 0
    for k, cs in cfg.items():
        for c in cs:
            r_ = data.get(str(c["snkr"])) or {}
            if (r_.get("day") or "") >= due_a:
                continue
            psa = (r_.get("psa_day") or "") < due_psa
            cost = 1 + psa + (not r_.get("pid")) + (not r_.get("vid") and r_.get("vid") != 0)
            if used + cost <= budget:
                todo.append((k, c, psa))
                used += cost
            else:
                waiting += 1
    rk_on = bool(os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY"))
    got = 0
    if todo:
        sess = sess or requests.Session()
        sess.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    for n, (k, c, psa) in enumerate(todo):
        rec = data.setdefault(str(c["snkr"]), {})
        rec.update(key=k, label=c["label"], num=c.get("num"))
        if n:
            sleep(WAIT)
        try:
            rec["jp"] = {**(rec.get("jp") or {}), **_card_daily(sess, c["snkr"], rec)}
            rec["jp"] = _thin(rec["jp"], today)
            if psa:
                try:  # PSA10（同じ商品の、鑑定品PSA10の1枚の取引）
                    sleep(WAIT)
                    rec["psa"] = _thin({**(rec.get("psa") or {}), **_card_daily(sess, c["snkr"], rec, COND_PSA10)}, today)
                    rec["psa_day"] = today
                except requests.HTTPError:
                    raise
                except Exception as e:
                    log(f"カード相場（PSA10）: {c['label']} 取得失敗 {e}")
            rec["day"] = today
            got += 1
        except requests.HTTPError as e:
            log(f"カード相場: {c['label']} 取得できず {e} → 今回はここまで")
            break
        except Exception as e:
            log(f"カード相場: {c['label']} 取得失敗 {e}")
            rec["day"] = today
    # 楽天の写真とリンク（7日ごと・1回60件まで＝全部のカードに数時間で付く）
    if rk_on:
        old = (t.date() - timedelta(days=7)).isoformat()
        for k, cs in cfg.items():
            for c in cs:
                if rk_budget <= 0:
                    break
                rec = data.setdefault(str(c["snkr"]), {"key": k, "label": c["label"], "num": c.get("num")})
                if (rec.get("rk") or {}).get("fetched", "") > old:
                    continue
                rk_budget -= 1
                try:
                    rec["rk"] = _rakuten_card(settings, c)
                except Exception as e:
                    log(f"カード相場（楽天）: {c['label']} 取得失敗 {e}")
                    if "401" in str(e) or "403" in str(e):
                        rk_budget = 0
                time.sleep(1.1)
    if todo or rk_on:
        save_json("souba_cards.json", data)
    if todo:
        log(f"カード相場: {got}/{len(todo)}件（残り{waiting}件は次の回）")
        if not waiting:  # その日の分を読み終えた回だけサイトを出し直す（毎回作り直さない）
            data_s = load_json("souba.json", {})
            data_s["cards_updated"] = t.isoformat()
            save_json("souba.json", data_s)
    return got


def card_summary(rec, today=None):
    """カード1枚の、いちばん新しい日（今日は途中なので昨日まで）の相場・前日比・7日前比・30日の点"""
    jp = sorted((rec.get("jp") or {}).items())
    today = today or now().date().isoformat()
    done = [x for x in jp if x[0] < today]
    if not done:
        return None
    d0, v0 = done[-1]
    prev = done[-2] if len(done) > 1 else None
    pts = [(d, v) for d, v in done if d >= (datetime.fromisoformat(d0) - timedelta(days=30)).date().isoformat()]
    psa = sorted(x for x in (rec.get("psa") or {}).items() if x[0] < today)
    psa = psa[-1] if psa and psa[-1][0] >= (datetime.fromisoformat(d0) - timedelta(days=90)).date().isoformat() else None  # 90日以内のいちばん新しい取引
    return {"date": d0, "price": v0, "psa": psa, "prev": prev, "week": _ago(done, d0, 7, slack=3),
            "month": _ago(done, d0, 30, slack=5), "year": _ago(done, d0, 365), "points": pts}
