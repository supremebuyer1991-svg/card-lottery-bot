"""新しい弾を公式サイトから自動で見つける（1日1回）

・ポケカ：公式の商品情報（resultAPI.php）から、拡張パック・構築デッキ・BOX商品の名前・発売日・希望小売価格
・ワンピースカード：公式の商品ページから、ブースターパック・エクストラブースター・スタートデッキ
・スニダン：発売前後の弾で、相場の対象がまだないものは、検索結果から「ボックス」の商品番号を探す
・結果は state/newsets.json。settings.yaml に手で書いた情報（series_info など）が常に優先
"""
import re
import time
from datetime import timedelta
from html import unescape

import requests

from common import load_json, save_json, now, log, normalize, load_settings

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
KEEP_PAST_DAYS = 60   # 発売から何日前までの商品を拾うか


def _iso(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def pokemon_products(sess):
    t = now()
    lo = t.date() - timedelta(days=KEEP_PAST_DAYS)
    base = ("https://www.pokemon-card.com/products/resultAPI.php?"
            f"dateLowerY={lo.year}&dateLowerM={lo.month}&dateLowerD={lo.day}"
            f"&dateUpperY={t.year + 1}&dateUpperM=12&dateUpperD=31&page=")
    out = []
    for page in range(1, 6):
        j = sess.get(base + str(page), timeout=30).json()
        for p in j.get("products") or []:
            out.append(p)
        if page >= int(j.get("maxPage") or 1):
            break
        time.sleep(1)
    res = {}
    for p in out:
        title = (p.get("productTitle") or "").strip()
        kind = p.get("productType") or ""
        if kind == "周辺グッズ":
            continue
        if kind == "構築デッキ" or (kind == "その他の商品" and not re.search(r"BOX|ボックス", title)):
            continue  # 抽選になりやすい拡張パックとBOX商品だけ
        m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", p.get("releaseDate") or "")
        if not m:
            continue
        q = re.search(r"「([^」]+)」", title)
        name = q.group(1).strip() if q else re.sub(r"^(ポケモンカードゲーム\s*)?(MEGA\s*)?", "", title).strip()
        typ = re.sub(r"[「」].*$", "", re.sub(r"^(ポケモンカードゲーム\s*)?(MEGA\s*)?", "", title)).strip() or kind
        img = (p.get("tumbsImg") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        slug = re.sub(r"[^a-z0-9]+", "-", img.lower()).strip("-")
        price = re.sub(r"<[^>]+>", " ", p.get("priceTxt") or "").strip()
        if kind == "拡張パック" and price:
            n = 10 if "ハイクラス" in title else 30  # 1BOXのパック数（ふつうの拡張パック30・ハイクラスパック10）
            pm = re.match(r"([\d,]+)円", price)
            price = "1パック" + price + (f"／1BOX（{n}パック）{int(pm.group(1).replace(',', '')) * n:,}円" if pm else "")
        res[name] = {"release": _iso(*m.groups()), "type": typ[:30], "price": price, "slug": slug}
    return res


def onepiece_products(sess, pages=(1, 2, 3), html=None):
    res = {}
    for page in pages:
        if html is None or page != pages[0]:
            html = sess.get(f"https://www.onepiece-cardgame.com/products/?page={page}&view=detail", timeout=30).text
        txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
        for m in re.finditer(r"(ブースター) ((?:ブースターパック|エクストラブースター|プレミアムブースター) "
                             r"[^発]{2,60}?) 発売日\s*(\d{4})\.(\d{2})\.(\d{2})\S*\s*メーカー希望小売価格\s*([\d,]+円)", txt):
            full = m.group(2).strip()
            code = (re.search(r"【([A-Z]{2,3}-\d{2})】", full) or [None, None])[1]
            name = re.sub(r"【[^】]+】", "", re.sub(r"^(ブースターパック|エクストラブースター|プレミアムブースター|スタートデッキ(EX)?)\s*", "", full)).strip()
            typ = re.sub(r"\s.*$", "", full) + (f"【{code}】" if code else "")
            price = m.group(6)
            if "ブースター" in typ:
                v = int(price.replace(",", "").replace("円", ""))
                price = "1パック" + price + f"（税込）／1BOX（24パック）{v * 24:,}円"
            else:
                price += "（税込）"
            slug = re.sub(r"[^a-z0-9]+", "", (code or "").lower())
            res[name] = {"release": _iso(*m.group(3, 4, 5)), "type": typ, "price": price, "slug": slug, "code": code}
        if len(pages) > 1:
            time.sleep(1)
        html = None
    return res


def find_snkr(sess, name):
    """スニダンの検索結果から、その弾の「ボックス」の商品番号を探す（見つからなければ None）"""
    html = sess.get("https://snkrdunk.com/search", params={"keywords": name}, timeout=30).text
    for m in re.finditer(r'href=\\?"https://snkrdunk\.com/apparels/(\d+)\\?"[^>]*aria-label=\\?"([^"\\]+)', html):
        aid, label = m.group(1), unescape(m.group(2))
        if name in label and re.search(r"ボックス|BOX", label) and not re.search(r"カートン|ケース|スリーブ|シングル|パック単品|英語版|海外版|韓国版|中国版|簡体|繁体|English", label):
            return int(aid)
    return None


def _pk_ex(sess, n):
    """ポケカ公式の弾の専用ページ（/ex/m8/ など）を見る。まだなければ None"""
    for suf in ("", "a"):
        r = sess.get(f"https://www.pokemon-card.com/ex/m{n}{suf}/", timeout=20, allow_redirects=False)
        if r.status_code != 200:
            continue
        html = r.text
        title = unescape((re.search(r"<title>(.*?)</title>", html, re.S) or [None, ""])[1])
        q = re.search(r"「([^」]+)」", title)
        if not q:
            continue
        txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
        rel = re.search(r"発売日\s*[:：]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", txt)
        pr = re.search(r"希望小売価格\s*[:：]\s*([\d,]+)円", txt)
        typ = re.sub(r"^.*?(拡張パック|強化拡張パック|ハイクラスパック|スペシャルデッキセット|構築デッキ)?「.*$", r"\1", title) or "拡張パック"
        price = ""
        if pr:
            v = int(pr.group(1).replace(",", ""))
            n_ = 10 if "ハイクラス" in title else 30
            price = f"1パック{v:,}円（税込）／1BOX（{n_}パック）{v * n_:,}円" if v < 1000 else f"{v:,}円（税込）"
        return q.group(1).strip(), {"release": _iso(*rel.groups()) if rel else "", "type": typ, "price": price,
                                    "slug": f"m{n}{suf}", "url_official": f"https://www.pokemon-card.com/ex/m{n}{suf}/"}
    return None


def quick_check(settings, sess=None):
    """新弾の発表をすぐ見つける（30分ごとの実行のたびに。公式ページを1〜3回見るだけ）
    ・ポケカ：専用ページの次の番号（/ex/m8/ など）ができたか
    ・ワンピースカード：公式の商品一覧の1ページ目に新しいブースターが増えたか
    見つけたら newsets.json に入れ、announce（Xの自動告知）の対象にする"""
    data = load_json("newsets.json", {})
    sess = sess or requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    today = now().date().isoformat()
    ser = data.setdefault("series", {})
    known = {g: {normalize(k) for k in m} for g, m in ser.items()}
    st = settings or load_settings()
    for g in ("pokemon", "onepiece"):
        known.setdefault(g, set()).update(normalize(k) for k in ((st.get("series_info") or {}).get(g) or {}))
        known[g].update(normalize(k) for k in ((st.get("series_aliases") or {}).get(g) or {}))
    for g, m in ser.items():  # 型番（OP-19 など）でも同じ弾と分かるように
        known.setdefault(g, set()).update(normalize(v.get("code")) for v in m.values() if isinstance(v, dict) and v.get("code"))
    first = not data.get("qc_ready")  # 初回は今ある商品を覚えるだけ（告知しない）
    found = []
    n = int(data.get("pk_ex_next") or 8)
    try:
        hit = _pk_ex(sess, n)
        if hit:
            name, v = hit
            data["pk_ex_next"] = n + 1
            if normalize(name) not in known["pokemon"]:
                ser.setdefault("pokemon", {})[name] = {"first_seen": today, "announce": "pending", **v}
                found.append(("pokemon", name))
    except Exception as e:
        log(f"新弾チェック: ポケカ 失敗 {e}")
    try:
        html = sess.get("https://www.onepiece-cardgame.com/products/?page=1&view=detail", timeout=20).text
        got = onepiece_products(sess, pages=(1,), html=html)
        for name, v in got.items():
            code = v.get("code") or ""
            if normalize(name) in known["onepiece"] or normalize(code) in known["onepiece"]:
                continue
            if str(v.get("release") or "") < today:
                continue  # 発売済みのものは新弾の告知にしない
            ser.setdefault("onepiece", {})[name] = {"first_seen": today, "announce": "skip" if first else "pending", **v}
            if not first:
                found.append(("onepiece", name))
        data["qc_ready"] = True
    except Exception as e:
        log(f"新弾チェック: ワンピースカード 失敗 {e}")
    if found:
        log(f"新弾チェック: 新しい弾を発見 {found}")
        _SER_reset()
    save_json("newsets.json", data)
    return found


def update_newsets(settings, sess=None, force=False):
    t = now()
    data = load_json("newsets.json", {})
    today = t.date().isoformat()
    if not force and (t.hour < settings.get("souba_hour", 7) or data.get("checked") == today):
        return 0
    data["checked"] = today
    sess = sess or requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    ser = data.setdefault("series", {})
    for g, fn in (("pokemon", pokemon_products), ("onepiece", onepiece_products)):
        try:
            got = fn(sess)
            cur = ser.setdefault(g, {})
            for k, v in got.items():
                cur[k] = {"first_seen": today, **cur.get(k, {}), **v}  # first_seen：初めて見つけた日（Xの告知に使う）
            log(f"新しい弾: {g} 公式から{len(got)}件")
        except Exception as e:
            log(f"新しい弾: {g} 取得失敗 {e}")
    # 古くなったもの（発売から60日より前）は消す
    cut = (t.date() - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    for g in ser:
        ser[g] = {k: v for k, v in ser[g].items() if str(v.get("release") or "") >= cut}
    # スニダンの商品番号（相場の対象がまだない、発売前〜発売後の弾だけ。1日に5件まで）
    import souba
    have = {(i["game"], i["series"]) for i in souba.items()}
    snkr = data.setdefault("snkr", {})
    from sitegen import _ser_cfg, canon_series
    _SER_reset()
    tries = 0
    for g, m in ser.items():
        for name, v in m.items():
            x = (canon_series(g, name) or [name])[0]
            key = f"{g}|{x}"
            if (g, x) in have or key in snkr or tries >= 5:
                continue
            if v.get("type") and not re.search(r"パック|ブースター|BOX", v["type"]):
                continue  # デッキなどは相場の対象にしない
            tries += 1
            try:
                aid = find_snkr(sess, x)
                if aid:
                    snkr[key] = aid
                    log(f"新しい弾: スニダン {x} → {aid}")
            except Exception as e:
                log(f"新しい弾: スニダン {x} 検索失敗 {e}")
            time.sleep(3)
    save_json("newsets.json", data)
    return 1


def _SER_reset():
    import sitegen
    sitegen._SER.clear()


def merged_info(settings=None):
    """弾の基本情報：自動で見つけたもの ＋ settings.yaml（手で書いたものが優先）"""
    st = settings or load_settings()
    auto = (load_json("newsets.json", {}).get("series") or {})
    man = st.get("series_info") or {}
    out = {}
    for g in set(auto) | set(man):
        al = {normalize(k): v for k, v in ((st.get("series_aliases") or {}).get(g) or {}).items()}
        d = {}
        for name, v in (auto.get(g) or {}).items():
            x = al.get(normalize(v.get("code") or "")) or al.get(normalize(name)) or name  # 品番・別名で手書きの弾名にそろえる
            if normalize(name) in al and not al[normalize(name)]:
                continue
            d[x] = {k: v[k] for k in ("release", "type", "price") if v.get(k)}
        for x, v in (man.get(g) or {}).items():
            d[x] = {**d.get(x, {}), **(v or {})}
        out[g] = d
    return out


def merged_slugs(settings=None):
    st = settings or load_settings()
    auto = (load_json("newsets.json", {}).get("series") or {})
    import souba
    past = souba.past_slugs()  # BOX相場の過去の弾（souba.yaml の slug）
    out = {}
    for g in set(auto) | set(st.get("series_slugs") or {}) | set(past):
        d = dict(past.get(g) or {})
        d.update({name: v["slug"] for name, v in (auto.get(g) or {}).items() if v.get("slug")})
        d.update((st.get("series_slugs") or {}).get(g) or {})
        out[g] = d
    return out


def merged_aliases(settings=None):
    """ワンピースの「OP-19」のような品番 → 弾名 も別名として足す"""
    st = settings or load_settings()
    auto = (load_json("newsets.json", {}).get("series") or {})
    out = {}
    for g in set(auto) | set(st.get("series_aliases") or {}):
        d = {v["code"]: name for name, v in (auto.get(g) or {}).items() if v.get("code")}
        d.update((st.get("series_aliases") or {}).get(g) or {})
        out[g] = d
    return out
