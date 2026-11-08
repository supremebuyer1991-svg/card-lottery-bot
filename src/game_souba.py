"""ゲーム・ホビー入荷速報：スニダンの相場（トレカ抽選ナビの相場と同じ読み方）

・対象は config/game/models.yaml の series_souba に書いた機種・モデルだけ（スニダンの商品番号 snkr・定価 teika）
・1日1回（souba_hour 時以降の最初の実行）。1件ずつ間をあけて読む。断られたらその日はあきらめる
・state/game/souba.json に {"<カテゴリ>|<モデル>": {"price": 直近の取引の平均, "date": その日, "avg7": 7日平均, "teika": 定価}} を残す
・サイトには「スニダン相場 ○円（定価比 +○%）」と、定価比からの目安（プレ値の目安）を出す。予想ではなく、目安と書く
"""
import time

import yaml

from common import ROOT, load_json, save_json, now, log

STATE = "souba.json"


def cfg():
    y = yaml.safe_load((ROOT / "config" / "game" / "models.yaml").read_text(encoding="utf-8")) or {}
    return y.get("series_souba") or {}


def update(settings, sess=None, sleep=time.sleep, daily=None):
    """daily(sess, snkr_id) → {日付: 値段}（テストでは偽物を渡す）"""
    c = cfg()
    if not c:
        return {}
    st = load_json(STATE, {})
    t = now()
    if t.hour < int(settings.get("souba_hour", 7)) or st.get("_checked", "")[:10] == t.date().isoformat():
        return st
    import souba
    if sess is None:
        import requests
        sess = requests.Session()
        sess.headers.update({"User-Agent": souba.UA, "Accept-Language": "ja"})
    daily = daily or souba._snkr_daily
    n = 0
    for game, models in c.items():
        for name, v in (models or {}).items():
            if not v or not v.get("snkr"):
                continue
            try:
                d = daily(sess, int(v["snkr"]))
            except Exception as e:
                log(f"相場（ゲーム）: {name} 取得失敗 {e}")
                if "403" in str(e) or "429" in str(e):
                    st["_checked"] = t.isoformat()
                    save_json(STATE, st)
                    return st
                continue
            days = sorted(d)
            if days:
                last7 = [d[k] for k in days[-7:]]
                st[f"{game}|{name}"] = {"price": d[days[-1]], "date": days[-1], "avg7": round(sum(last7) / len(last7)),
                                        "teika": v.get("teika"), "snkr": v["snkr"]}
                n += 1
            sleep(1.5)
    st["_checked"] = t.isoformat()
    save_json(STATE, st)
    log(f"相場（ゲーム）: {n}件を更新")
    return st


def label(rec):
    """{"text": "スニダン相場 59,800円（定価比 +0%）", "hint": "定価前後"} か None"""
    if not rec or not rec.get("price"):
        return None
    p = int(rec.get("avg7") or rec["price"])
    text = f"スニダン相場 {p:,}円"
    hint = ""
    if rec.get("teika"):
        r = p / int(rec["teika"])
        text += f"（定価比 {'+' if r >= 1 else ''}{round((r - 1) * 100)}%）"
        hint = "プレ値 高め" if r >= 1.3 else "プレ値 やや高め" if r >= 1.1 else "定価前後" if r >= 0.95 else "定価より安い"
    return {"text": text, "hint": hint}


def for_item(it, st=None):
    st = st if st is not None else load_json(STATE, {})
    return label(st.get(f"{it.get('game')}|{it.get('series')}"))
