"""新弾の発表を見つけたら、すぐXに自動でポストする（サイトの公開のあとに動く）

・newsets.json の announce が "pending" の弾だけ。ポストしたら "posted" にする（二度ポストしない）
・ほかのポストはブラウザの予約で出しているので、APIでのポストはこれだけ（リンク付き1件 約0.2ドル）
"""
import os
import sys

from common import load_json, save_json, load_settings, log

GAME = {"pokemon": ("ポケモンカード", "#ポケカ #ポケカ抽選"),
        "onepiece": ("ワンピースカード", "#ワンピースカード #ワンピースカード抽選")}


def jdate(d):
    try:
        y, m, dd = d.split("-")
        import datetime
        w = "月火水木金土日"[datetime.date(int(y), int(m), int(dd)).weekday()]
        return f"{int(y)}年{int(m)}月{int(dd)}日（{w}）"
    except Exception:
        return ""


def compose(game, name, v, url):
    gname, tags = GAME[game]
    import re
    typ = v.get("type") or ""
    code = (re.search(r"【[^】]+】", typ) or [""])[0]
    lines = [f"🆕{gname} 新弾発売決定！", "", f"{typ.replace(code, '')}「{name}」{code}".strip()]
    if v.get("release"):
        lines.append(f"📅発売日：{jdate(v['release'])}")
    if v.get("price"):
        lines.append(f"💴定価：{v['price']}")
    lines += ["", "続報・抽選情報が出たらすぐお知らせします📣", "フォロー＆通知オン🔔でお待ちください！", "", url, "", tags]
    text = "\n".join(lines)
    # 280字（全角は2字）を超えたら、タグを1つ → 定価のBOXの部分 の順に削る
    from xpost import x_len
    if x_len(text) > 280:
        text = text.replace(tags, tags.split()[0])
    if x_len(text) > 280 and "／" in (v.get("price") or ""):
        text = text.replace(v["price"], v["price"].split("／")[0])
    return text


def main():
    s = load_settings()
    data = load_json("newsets.json", {})
    site = (s.get("site_public_url") or "").rstrip("/")
    todo = [(g, n, v) for g, m in (data.get("series") or {}).items() for n, v in m.items() if v.get("announce") == "pending"]
    if not todo:
        return 0
    sys.path.insert(0, os.path.dirname(__file__))
    from sitegen import series_path, canon_series
    import xpost
    client = None
    for g, n, v in todo:
        x = (canon_series(g, n) or [n])[0]
        text = compose(g, x, v, f"{site}/{series_path(g, x)}")
        if s.get("dry_run") or not os.environ.get("X_API_KEY"):
            log("新弾の告知（ためし・ポストしない）:\n" + text)
            continue
        try:
            client = client or xpost._client()
            try:
                res = client.create_tweet(text=text)
            except Exception as e1:  # 長すぎるなどで断られたら、定価のBOXの部分とタグを短くしてもう1回
                log(f"新弾の告知: 1回目失敗 {e1} → 短くしてもう1回")
                short = dict(v, price=(v.get("price") or "").split("／")[0])
                text = compose(g, x, short, f"{site}/{series_path(g, x)}").replace(GAME[g][1], GAME[g][1].split()[0])
                res = client.create_tweet(text=text)
            v["announce"] = "posted"
            v["tweet_id"] = str((getattr(res, "data", None) or {}).get("id", ""))
            log(f"新弾の告知をポストしました: {x}")
        except Exception as e:
            log(f"新弾の告知: ポスト失敗 {x} {e}")
            v["announce"] = "failed"  # 何度も失敗ポストしない（手で確認）
    save_json("newsets.json", data)
    return 1


if __name__ == "__main__":
    main()
