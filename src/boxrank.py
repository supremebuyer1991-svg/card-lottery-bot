"""BOX相場の上昇・下落ランキングの縦長動画（TikTok・YouTubeショート用・1080×1920・音なし）

・値段はスニダンで成立した取引の1日の平均（state/souba.json）
・1日だけの値段だと取引が少ない商品で大きくぶれるので、何日かの平均どうしで比べる
    今週（week）：直近4日 と 1週間前ごろ（5〜11日前）の、日ごとの値段の真ん中の値（中央値）
    今日（day） ：いちばん新しい日 と その前の3日の中央値
  中央値なので、たまたま安い・高い取引が1日あってもランキングが崩れにくい
  それぞれ2日以上の値段がない商品（取引が少ない）と、3日以上取引がない商品は入れない
・BOXの写真は楽天の商品の写真（state/rakuten.json）
・できた動画は Discord（DISCORD_WEBHOOK_URL）に送る。投稿は手作業

使い方: python src/boxrank.py 出力フォルダ [week|day] [--send]
"""
import io
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from common import load_json, now, log
import souba
import ximage as X

VW, VH = 1080, 1920
UP, DOWN = (200, 16, 46), (0, 128, 96)  # 上がった＝赤、下がった＝緑（日本の株価の色）
GN = {"pokemon": "ポケカ", "onepiece": "ワンピースカード"}
TOP = 5


def _mid(v):
    """中央値"""
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if v else None


def rankings(span="week", today=None, data=None):
    """{"up": {game: [(変化%, 名前, 今の平均, 前の平均, 楽天のキー)]}, "down": {...}}"""
    today = today or now().date()
    data = data if data is not None else load_json("souba.json", {})
    out = {"up": {}, "down": {}}
    for k, v in (data.get("items") or {}).items():
        g = k.split("|")[0]
        if g not in GN:
            continue
        s = souba.summary(v, today.isoformat())
        if not s:
            continue
        d0 = date.fromisoformat(s["date"])
        if d0 < today - timedelta(days=3):
            continue  # しばらく取引がない
        pts = [(date.fromisoformat(d), p) for d, p in s["points"] if p]
        if span == "week":
            now_v = [p for d, p in pts if d0 - timedelta(days=3) <= d <= d0]
            old_v = [p for d, p in pts if d0 - timedelta(days=11) <= d <= d0 - timedelta(days=5)]
        else:
            now_v = [p for d, p in pts if d == d0]
            old_v = [p for d, p in pts if d0 - timedelta(days=3) <= d < d0]
            if len(now_v) == 1:
                now_v = now_v * 2  # 今日は1日分しかないので数だけそろえる
        if len(now_v) < 2 or len(old_v) < 2:
            continue  # 取引が少なくて平均が出せない
        a, b = _mid(now_v), _mid(old_v)
        pct = (a - b) / b * 100
        if abs(pct) < 0.5:
            continue
        row = (pct, (v.get("name") or k.split("|")[1]).replace(" BOX", "").strip(), round(a), round(b),
               f"{g}|{v.get('series') or k.split('|')[1]}")
        out["up" if pct > 0 else "down"].setdefault(g, []).append(row)
    for kind in out:
        for g in out[kind]:
            out[kind][g].sort(key=lambda x: -abs(x[0]))
            out[kind][g] = out[kind][g][:TOP]
    return out


def _photo(key, rk, cache):
    """楽天の商品の写真（正方形・白背景）。読めなければ None"""
    if key in cache:
        return cache[key]
    url = (rk.get(key) or {}).get("image") or ""
    im = None
    if url:
        try:
            url = url.split("?")[0] + "?_ex=400x400"
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            src = Image.open(io.BytesIO(r.content)).convert("RGBA")
            src.thumbnail((170, 170))
            im = Image.new("RGBA", (170, 170), (255, 255, 255, 255))
            im.alpha_composite(src, ((170 - src.width) // 2, (170 - src.height) // 2))
        except Exception as e:  # noqa: BLE001
            log(f"ランキング動画: 写真が読めない {key} {e}")
    cache[key] = im
    return im


def _canvas():
    im = Image.new("RGBA", (VW, VH), X.PAPER + (255,))
    return im, ImageDraw.Draw(im)


def _band(d, txt, y, size, fill):
    f = X.F(size, "Black")
    tw = d.textlength(txt, font=f)
    d.rounded_rectangle(((VW - tw) / 2 - 30, y - size * 0.75, (VW + tw) / 2 + 30, y + size * 0.75), 20, fill=fill)
    d.text((VW / 2, y), txt, font=f, fill=(255, 255, 255), anchor="mm")


def _header(d):
    d.rectangle((0, 0, VW, 170), fill=X.CARD)
    d.text((VW / 2, 92), "トレカ抽選ナビ", font=X.DELA(56), fill=X.INK, anchor="mm")


def _footer(d, span):
    d.rectangle((0, VH - 260, VW, VH), fill=X.CARD)
    d.text((VW / 2, VH - 170), "毎日の相場は「トレカ抽選ナビ」で", font=X.F(44, "Black"), fill=X.INK, anchor="mm")
    note = "直近数日と1週間前ごろの値段（中央値）を比べています" if span == "week" else "前の3日の値段（中央値）と比べています"
    d.text((VW / 2, VH - 108), "スニダンで成立した取引（1BOX）の1日の平均から", font=X.F(30, "Medium"), fill=X.INK2, anchor="mm")
    d.text((VW / 2, VH - 64), note, font=X.F(28, "Medium"), fill=X.INK2, anchor="mm")


def frames(kind, span, ranks, rk, today):
    col = UP if kind == "up" else DOWN
    word, arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
    sj = "今週" if span == "week" else "今日"
    cache, out = {}, []
    # はじめ
    im, d = _canvas()
    _header(d)
    d.text((VW / 2, 470), f"{sj}の", font=X.F(90, "Black"), fill=X.INK, anchor="mm")
    d.text((VW / 2, 610), "BOX相場", font=X.DELA(150), fill=X.INK, anchor="mm")
    _band(d, f"{word}ランキング{arrow}", 800, 100, col)
    d.text((VW / 2, 1000), " ／ ".join(GN[g] for g in GN if ranks.get(g)), font=X.F(60, "Black"), fill=X.INK2, anchor="mm")
    d.text((VW / 2, 1100), f"{today.month}/{today.day}({X.WEEK[today.weekday()]})時点", font=X.F(48, "Bold"), fill=X.INK2, anchor="mm")
    _footer(d, span)
    out.append((im, 2.5))
    # ゲームごと：5位から順に出す
    for g in GN:
        rows = ranks.get(g) or []
        if not rows:
            continue
        n = len(rows)
        for shown in range(n + 1):
            im, d = _canvas()
            _header(d)
            _band(d, f"{GN[g]}  {sj}の{word}TOP{n}", 290, 58, col)
            y0, rh, gap = 400, 205, 22
            for r in range(n):  # r=0 が1位
                if r < n - shown:
                    continue
                pct, name, price, base, key = rows[r]
                y = y0 + r * (rh + gap)
                X._ticket(im, (40, y, VW - 40, y + rh), stub=40 + 130)
                d = ImageDraw.Draw(im)
                medal = X.MEDAL[r] if r < 3 else X.INK2
                d.ellipse((40 + 20, y + rh / 2 - 45, 40 + 110, y + rh / 2 + 45), fill=medal)
                d.text((40 + 65, y + rh / 2), str(r + 1), font=X.F(54, "Black"), fill=(255, 255, 255), anchor="mm")
                ph = _photo(key, rk, cache)
                tx = 40 + 130 + 24
                if ph:
                    im.alpha_composite(ph, (tx, y + (rh - 170) // 2))
                    d = ImageDraw.Draw(im)
                    tx += 170 + 22
                d.text((tx, y + 26), X._fit(d, name, X.F(42, "Black"), VW - 40 - 26 - tx), font=X.F(42, "Black"), fill=X.INK)
                d.text((tx, y + 96), f"{arrow}{abs(pct):.1f}%", font=X.F(60, "Black"), fill=col)
                d.text((VW - 40 - 26, y + 104), f"¥{price:,}", font=X.F(40, "Black"), fill=X.INK, anchor="ra")
                d.text((VW - 40 - 26, y + 156), ("先週 " if span == "week" else "前 ") + f"¥{base:,}", font=X.F(26, "Medium"), fill=X.INK2, anchor="ra")
            _footer(d, span)
            out.append((im, 3.2 if shown == n else (1.0 if shown else 0.6)))
    # おわり
    im, d = _canvas()
    _header(d)
    d.text((VW / 2, 560), "BOXの相場グラフ・", font=X.F(76, "Black"), fill=X.INK, anchor="mm")
    d.text((VW / 2, 660), "抽選の締切は", font=X.F(76, "Black"), fill=X.INK, anchor="mm")
    d.text((VW / 2, 830), "トレカ抽選ナビ", font=X.DELA(110), fill=X.RED, anchor="mm")
    d.text((VW / 2, 960), "tcg-chusen.com", font=X.F(60, "Bold"), fill=X.INK2, anchor="mm")
    _band(d, "プロフィールのリンクから", 1140, 60, X.RED)
    d.text((VW / 2, 1310), "フォローで相場ランキングが届きます", font=X.F(48, "Bold"), fill=X.INK, anchor="mm")
    out.append((im, 3.0))
    return out


def make(out_dir, kind, span="week", ranks=None, today=None):
    """動画を1本つくってパスを返す。ランキングが空なら None"""
    today = today or now().date()
    ranks = ranks if ranks is not None else rankings(span, today)[kind]
    if not any(ranks.values()):
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fr = frames(kind, span, ranks, load_json("rakuten.json", {}), today)
    lst = []
    for n, (f, dur) in enumerate(fr):
        p = out_dir / f"_{kind}{span}_{n:02d}.png"
        f.convert("RGB").save(p)
        lst.append(f"file '{p.resolve()}'\nduration {dur}")
    lst.append(f"file '{(out_dir / f'_{kind}{span}_{len(fr) - 1:02d}.png').resolve()}'")
    (out_dir / f"_{kind}{span}.txt").write_text("\n".join(lst) + "\n", encoding="utf-8")
    total = sum(x[1] for x in fr)
    mp4 = out_dir / f"box_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_{today:%m%d}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(out_dir / f"_{kind}{span}.txt"),
                    "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    for p in out_dir.glob(f"_{kind}{span}*"):
        p.unlink()
    return mp4


def caption(kind, span, ranks):
    """投稿のときに貼る文（Discord に一緒に送る）"""
    word = "上昇" if kind == "up" else "下落"
    sj = "今週" if span == "week" else "今日"
    lines = [f"📈{sj}のBOX相場 {word}ランキング" if kind == "up" else f"📉{sj}のBOX相場 {word}ランキング"]
    for g in GN:
        for r, (pct, name, price, base, _) in enumerate(ranks.get(g) or []):
            if r == 0:
                lines.append(f"\n【{GN[g]}】")
            lines.append(f"{r + 1}位 {name} {pct:+.1f}%（¥{price:,}）")
    lines.append("\nBOXの相場・抽選の締切はプロフィールのリンクから")
    lines.append("#ポケカ #ワンピースカード #ポケカ相場 #トレカ")
    return "\n".join(lines)


def send(path, text):
    hook = "".join(os.environ.get("DISCORD_WEBHOOK_URL", "").split())
    if not hook:
        log("ランキング動画: DISCORD_WEBHOOK_URL が無いので送らない")
        return False
    with open(path, "rb") as f:
        r = requests.post(hook, data={"content": text[:1900]}, files={"file": (Path(path).name, f, "video/mp4")}, timeout=60)
    log(f"ランキング動画: Discordへ {r.status_code}")
    return r.ok


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "video"
    span = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("week", "day") else "week"
    today = now().date()
    rk_all = rankings(span, today)
    for kind in ("up", "down"):
        p = make(out, kind, span, rk_all[kind], today)
        print(kind, p, {g: [(round(x[0], 1), x[1]) for x in v] for g, v in rk_all[kind].items()})
        if p and "--send" in sys.argv:
            send(p, "🎬ランキング動画（音はアプリで追加してください）\n\n" + caption(kind, span, rk_all[kind]))
