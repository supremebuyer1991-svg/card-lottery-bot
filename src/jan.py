"""弾ごとの BOX の JANコード（11/11 ユーザー依頼：弾ページに JANコードを載せる）

・Amazon の商品情報（メーカー公式の BOX の出品）の EAN＝JAN を使う。Worker（rakuten-watch）の /jan 経由（Amazon の鍵は Worker にある）
・まちがった番号を載せないよう、次をすべて満たすときだけ採用する
  - 商品名に弾の名前と「BOX」が入っている（カートン・セット・まとめ・バラ・〇個 などは除く）
  - ブランドが ポケモン／バンダイ
  - JAN が 1つだけで、45・49 で始まる13けた
・手で書いたもの（settings.yaml の series_info の jan_box）があればそちらが優先
・結果は state/jan.json。見つからなかった弾は3日おきにやり直す。1回の実行で最大15件だけ調べる
"""
import json
import re
import time
import unicodedata
import urllib.parse
from datetime import timedelta

import requests

from common import load_json, save_json, log, now, parse_dt

URL = "https://rakuten-watch.supreme-buyer-1991.workers.dev/jan?q="
NG = re.compile(r"カートン|セット|まとめ|ばら|バラ|\d+\s*(個|箱|BOX|パック)|×|x\d|中古|未開封品|シュリンク|予約販売|特典")
BRAND = {"pokemon": re.compile(r"ポケモン|Pokemon|Pokémon|株式会社ポケモン", re.I), "onepiece": re.compile(r"バンダイ|BANDAI", re.I)}
HEAD = {"pokemon": "ポケモンカードゲーム", "onepiece": "ONE PIECEカードゲーム"}


def _n(s):
    return re.sub(r"[\s・ー－\-「」『』【】()（）]", "", unicodedata.normalize("NFKC", s or "")).lower()


def pick(game, series, items):
    """候補から、その弾の BOX の JAN を1つ選ぶ（決められなければ None）"""
    want = _n(series)
    hit = []
    for it in items or []:
        t = it.get("title") or ""
        if want not in _n(t) or not re.search(r"BOX|ボックス", t, re.I) or NG.search(t.replace(series, "")):
            continue
        if not BRAND[game].search((it.get("brand") or "") + t[:12]):
            continue
        js = [j for j in it.get("jan") or [] if re.fullmatch(r"4[59]\d{11}", j)]
        if len(js) == 1:
            hit.append((js[0], it))
    codes = {j for j, _ in hit}
    if len(codes) != 1:   # 0件、または候補が割れている（ちがう番号が2つ以上）ときは載せない
        return None
    j, it = hit[0]
    return {"jan": j, "asin": it.get("asin"), "title": it.get("title")}


def update(series_by_game, budget=15, sleep=1.2):
    data = load_json("jan.json", {})
    t = now()
    called = 0
    for g, names in series_by_game.items():
        for x in names:
            k = f"{g}|{x}"
            c = data.get(k) or {}
            if c.get("jan"):
                continue
            last = parse_dt(c.get("checked"))
            if last and t - last < timedelta(days=3):
                continue
            if called >= budget:
                break
            if called:
                time.sleep(sleep)
            called += 1
            try:
                r = requests.get(URL + urllib.parse.quote(f"{HEAD[g]} {x} BOX"), timeout=25)
                j = r.json()
            except Exception as e:
                log(f"JAN: {x} 取得失敗 {e}")
                continue
            if j.get("error"):
                log(f"JAN: {x} {j['error']}")
                if "401" in j["error"] or "403" in j["error"]:
                    break
                continue
            p = pick(g, x, j.get("items"))
            data[k] = dict(p or {}, checked=t.isoformat())
            log(f"JAN: {x} → {p['jan'] if p else '見つからず'}")
    if called:
        save_json("jan.json", data)
    return data


def series_names(sitegen):
    """弾ページを作る弾（基本情報のある弾＋相場のある弾）"""
    info = sitegen._ser_cfg()["info"]
    souba = load_json("souba.json", {})
    keys = souba.get("items") if isinstance(souba, dict) else {}
    out = {}
    for g in ("pokemon", "onepiece"):
        names = list((info.get(g) or {}).keys())
        names += [k.split("|", 1)[1] for k in (keys if isinstance(keys, dict) else {}) if k.startswith(g + "|")]
        out[g] = list(dict.fromkeys(n for n in names if n and "|" not in n))
    return out


def jan_of(game, series, info=None):
    """弾ページに出す BOX の JAN（手書き優先）"""
    m = str((info or {}).get("jan_box") or "").strip()
    if re.fullmatch(r"\d{13}", m):
        return {"jan": m, "src": "manual"}
    d = load_json("jan.json", {}).get(f"{game}|{series}") or {}
    return {"jan": d["jan"], "src": "amazon", "asin": d.get("asin")} if d.get("jan") else None


if __name__ == "__main__":
    import sitegen
    print(json.dumps(series_names(sitegen), ensure_ascii=False)[:500])
