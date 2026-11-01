"""BOX相場の上昇・下落ランキングの縦長動画（TikTok・YouTubeショート用・1080×1920・音なし）

・値段はスニダンで成立した取引の1日の平均（state/souba.json）
・1日だけの値段だと取引が少ない商品で大きくぶれるので、何日かの平均どうしで比べる
    今週（week）：直近4日 と 1週間前ごろ（5〜11日前）の、日ごとの値段の真ん中の値（中央値）
    今日（day） ：いちばん新しい日 と その前の3日の中央値
  中央値なので、たまたま安い・高い取引が1日あってもランキングが崩れにくい
  それぞれ2日以上の値段がない商品（取引が少ない）と、3日以上取引がない商品は入れない
・BOXの写真は楽天の商品の写真（state/rakuten.json）
・できた動画は Discord（DISCORD_WEBHOOK_URL）に送る。投稿は手作業

動画はゲームごと・上昇／下落ごとに1本（ポケカ上昇・ポケカ下落・ワンピ上昇・ワンピ下落）
  はじめ → 5位〜1位を1つの弾につき1ページ（横にスライド）→ まとめの表 → おわり

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
    """{"up": {game: [(変化%, 名前, 今の値, 前の値, 楽天のキー, 30日分の値段)]}, "down": {...}}"""
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
               f"{g}|{v.get('series') or k.split('|')[1]}", [(d.isoformat(), p) for d, p in pts])
        out["up" if pct > 0 else "down"].setdefault(g, []).append(row)
    for kind in out:
        for g in out[kind]:
            out[kind][g].sort(key=lambda x: -abs(x[0]))
            out[kind][g] = out[kind][g][:TOP]
    return out


def _photo(key, rk, cache, size):
    """楽天の商品の写真（正方形・白背景）。読めなければ None"""
    if key not in cache:
        url = (rk.get(key) or {}).get("image") or ""
        cache[key] = None
        if url:
            try:
                r = requests.get(url.split("?")[0] + "?_ex=600x600", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                cache[key] = Image.open(io.BytesIO(r.content)).convert("RGBA")
            except Exception as e:  # noqa: BLE001
                log(f"ランキング動画: 写真が読めない {key} {e}")
    src = cache[key]
    if src is None:
        return None
    sc = min(size / src.width, size / src.height)
    sm = src.resize((max(1, int(src.width * sc)), max(1, int(src.height * sc))), Image.LANCZOS)
    im = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    im.alpha_composite(sm, ((size - sm.width) // 2, (size - sm.height) // 2))
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
    d.rectangle((0, VH - 230, VW, VH), fill=X.CARD)
    d.text((VW / 2, VH - 150), "毎日の相場は「トレカ抽選ナビ」で", font=X.F(44, "Black"), fill=X.INK, anchor="mm")
    note = "直近数日と1週間前ごろの値段（中央値）を比べています" if span == "week" else "前の3日の値段（中央値）と比べています"
    d.text((VW / 2, VH - 92), "スニダンで成立した取引（1BOX）の1日の平均から", font=X.F(28, "Medium"), fill=X.INK2, anchor="mm")
    d.text((VW / 2, VH - 52), note, font=X.F(26, "Medium"), fill=X.INK2, anchor="mm")


def _chart(im, box, pts, col):
    """30日分の値段の線（いちばん新しい点に丸）"""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, 18, fill=X.CARD)
    d.text((x0 + 24, y0 + 16), "30日の値段の動き", font=X.F(26, "Bold"), fill=X.INK2)
    v = [p for _, p in pts]
    if len(v) < 2:
        return
    lo, hi = min(v), max(v)
    hi = hi if hi > lo else lo + 1
    px0, px1, py0, py1 = x0 + 40, x1 - 40, y0 + 66, y1 - 24
    xy = [(px0 + (px1 - px0) * k / (len(v) - 1), py1 - (py1 - py0) * (p - lo) / (hi - lo)) for k, p in enumerate(v)]
    d.line(xy, fill=col, width=7, joint="curve")
    ex, ey = xy[-1]
    d.ellipse((ex - 12, ey - 12, ex + 12, ey + 12), fill=col)


def frames(kind, span, game, rows, rk, today):
    """[(画像, 秒, つぎへの切りかえ)]"""
    col = UP if kind == "up" else DOWN
    word, arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
    sj = "今週" if span == "week" else "今日"
    gname = GN[game]
    cache, out = {}, []
    n = len(rows)
    # はじめ
    im, d = _canvas()
    _header(d)
    d.text((VW / 2, 430), gname, font=X.DELA(120 if game == "pokemon" else 92), fill=X.INK, anchor="mm")
    d.text((VW / 2, 600), f"{sj}のBOX相場", font=X.F(110, "Black"), fill=X.INK, anchor="mm")
    _band(d, f"{word}ランキング{arrow}", 800, 100, col)
    d.text((VW / 2, 990), f"TOP{n}を5位から発表", font=X.F(60, "Black"), fill=X.INK2, anchor="mm")
    d.text((VW / 2, 1090), f"{today.month}/{today.day}({X.WEEK[today.weekday()]})時点", font=X.F(48, "Bold"), fill=X.INK2, anchor="mm")
    _footer(d, span)
    out.append((im, 2.2, "slideleft"))
    # 1つの弾につき1ページ（5位→1位）
    for r in range(n - 1, -1, -1):
        pct, name, price, base, key, pts = rows[r]
        im, d = _canvas()
        _header(d)
        _band(d, f"{gname} {sj}の{word}ランキング", 250, 44, col)
        medal = X.MEDAL[r] if r < 3 else X.INK2
        d.text((VW / 2, 380), f"第{r + 1}位", font=X.DELA(110), fill=medal, anchor="mm")
        ph = _photo(key, rk, cache, 560)
        y = 470
        if ph:
            d.rounded_rectangle((VW / 2 - 300, y - 20, VW / 2 + 300, y + 580), 28, fill=(255, 255, 255))
            im.alpha_composite(ph, (VW // 2 - 280, y))
            d = ImageDraw.Draw(im)
            y += 620
        else:
            y += 120
        d.text((VW / 2, y + 30), X._fit(d, name, X.F(64, "Black"), VW - 100), font=X.F(64, "Black"), fill=X.INK, anchor="mm")
        d.text((VW / 2, y + 160), f"{arrow}{abs(pct):.1f}%", font=X.F(140, "Black"), fill=col, anchor="mm")
        prev_l = "先週" if span == "week" else "前"
        d.text((VW / 2, y + 285), f"¥{base:,}  →  ¥{price:,}", font=X.F(56, "Black"), fill=X.INK, anchor="mm")
        d.text((VW / 2, y + 345), f"（{prev_l} → いま）", font=X.F(30, "Medium"), fill=X.INK2, anchor="mm")
        if ph and y + 560 < VH - 250:
            _chart(im, (60, y + 390, VW - 60, VH - 250), pts, col)
        _footer(d, span)
        out.append((im, 2.8, "slideleft"))
    # まとめの表
    im, d = _canvas()
    _header(d)
    _band(d, f"まとめ｜{gname} {sj}の{word}TOP{n}", 270, 50, col)
    y, rh, gap = 380, 190, 20
    for r, (pct, name, price, base, key, _) in enumerate(rows):
        X._ticket(im, (40, y, VW - 40, y + rh), stub=40 + 120)
        d = ImageDraw.Draw(im)
        medal = X.MEDAL[r] if r < 3 else X.INK2
        d.ellipse((40 + 18, y + rh / 2 - 42, 40 + 102, y + rh / 2 + 42), fill=medal)
        d.text((40 + 60, y + rh / 2), str(r + 1), font=X.F(50, "Black"), fill=(255, 255, 255), anchor="mm")
        tx = 40 + 120 + 22
        ph = _photo(key, rk, cache, 150)
        if ph:
            im.alpha_composite(ph, (tx, y + (rh - 150) // 2))
            d = ImageDraw.Draw(im)
            tx += 150 + 20
        d.text((tx, y + 24), X._fit(d, name, X.F(40, "Black"), VW - 40 - 24 - tx), font=X.F(40, "Black"), fill=X.INK)
        d.text((tx, y + 90), f"{arrow}{abs(pct):.1f}%", font=X.F(56, "Black"), fill=col)
        d.text((VW - 40 - 24, y + 96), f"¥{price:,}", font=X.F(38, "Black"), fill=X.INK, anchor="ra")
        d.text((VW - 40 - 24, y + 144), ("先週 " if span == "week" else "前 ") + f"¥{base:,}", font=X.F(25, "Medium"), fill=X.INK2, anchor="ra")
        y += rh + gap
    d.text((VW / 2, y + 40), "保存して相場チェック！", font=X.F(50, "Black"), fill=X.INK, anchor="mm")
    _footer(d, span)
    out.append((im, 4.0, "fade"))
    # おわり
    im, d = _canvas()
    _header(d)
    d.text((VW / 2, 560), "BOXの相場グラフ・", font=X.F(76, "Black"), fill=X.INK, anchor="mm")
    d.text((VW / 2, 660), "抽選の締切は", font=X.F(76, "Black"), fill=X.INK, anchor="mm")
    d.text((VW / 2, 830), "トレカ抽選ナビ", font=X.DELA(110), fill=X.RED, anchor="mm")
    d.text((VW / 2, 960), "tcg-chusen.com", font=X.F(60, "Bold"), fill=X.INK2, anchor="mm")
    _band(d, "プロフィールのリンクから", 1140, 60, X.RED)
    d.text((VW / 2, 1310), "フォローで相場ランキングが届きます", font=X.F(48, "Bold"), fill=X.INK, anchor="mm")
    out.append((im, 2.6, None))
    return out


def make(out_dir, kind, span, game, rows, today=None):
    """動画を1本つくってパスを返す。ランキングが空なら None"""
    today = today or now().date()
    if not rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fr = frames(kind, span, game, rows, load_json("rakuten.json", {}), today)
    tag = f"{game}{kind}{span}"
    inp, flt, XD = [], [], 0.4
    for n, (f, dur, _) in enumerate(fr):
        p = out_dir / f"_{tag}_{n:02d}.png"
        f.convert("RGB").save(p)
        inp += ["-loop", "1", "-framerate", "30", "-t", f"{dur + XD:.2f}", "-i", str(p)]
        flt.append(f"[{n}:v]fps=30,format=yuv420p,setsar=1[v{n}]")
    cur, off = "v0", 0.0
    for n in range(1, len(fr)):
        off += fr[n - 1][1]
        flt.append(f"[{cur}][v{n}]xfade=transition={fr[n - 1][2] or 'fade'}:duration={XD}:offset={off:.2f}[x{n}]")
        cur = f"x{n}"
    total = sum(x[1] for x in fr) + XD
    mp4 = out_dir / f"box_{game}_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_{today:%m%d}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inp +
                   ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", ";".join(flt), "-map", f"[{cur}]", "-map", f"{len(fr)}:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    for p in out_dir.glob(f"_{tag}_*"):
        p.unlink()
    return mp4


def caption(kind, span, game, rows):
    """投稿のときに貼る文（Discord に一緒に送る）"""
    word = "上昇" if kind == "up" else "下落"
    sj = "今週" if span == "week" else "今日"
    lines = [("📈" if kind == "up" else "📉") + f"{GN[game]}｜{sj}のBOX相場 {word}ランキング", ""]
    for r, (pct, name, price, base, *_) in enumerate(rows):
        lines.append(f"{r + 1}位 {name} {pct:+.1f}%（¥{price:,}）")
    lines.append("\nBOXの相場・抽選の締切はプロフィールのリンクから")
    lines.append("#ポケカ #ポケカ相場 #ポケモンカード #トレカ" if game == "pokemon" else "#ワンピースカード #ワンピカード #ワンピース相場 #トレカ")
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
    for game in GN:
        for kind in ("up", "down"):
            rows = rk_all[kind].get(game) or []
            p = make(out, kind, span, game, rows, today)
            print(game, kind, p, [(round(x[0], 1), x[1]) for x in rows])
            if p and "--send" in sys.argv:
                send(p, "🎬ランキング動画（音はアプリで追加してください）\n\n" + caption(kind, span, game, rows))
