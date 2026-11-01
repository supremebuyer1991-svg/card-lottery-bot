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
  はじめ → 5位〜1位を1つの弾につき1ページ（横にスライド）→ まとめの棒グラフ → おわり
  ページの中は動く：順位がポンと出る・30日のチャートの線が伸びる（値札が線の先についていく）・％が数えあがる・
  1位は紙吹雪（上昇）／画面がゆれる（下落）。1コマずつ絵を描いて ffmpeg に流しこむ

使い方: python src/boxrank.py 出力フォルダ [week|day] [--send]
"""
import io
import math
import os
import random
import subprocess
import sys
from datetime import date, timedelta
from functools import lru_cache
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


import vidkit as V
from vidkit import FB, FD, eo, back, prog, put, text_layer, band_layer, layer


def _md(s):
    d = date.fromisoformat(s)
    return f"{d.month}/{d.day}"


def _foot(span):
    return ["毎日の相場は「トレカ抽選ナビ」で", "スニダンで成立した取引（1BOX）の1日の平均から",
            "直近数日と1週間前ごろの値段（中央値）を比べています" if span == "week" else "前の3日の値段（中央値）と比べています"]


class Ctx:
    """1本の動画で共通のもの（見た目・電光掲示板・写真）"""
    def __init__(self, th, kind, span, game, rows, all_rows, rk, today):
        self.th, self.kind, self.span, self.game, self.rows, self.today = th, kind, span, game, rows, today
        self.col = th.up if kind == "up" else th.down
        self.word, self.arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
        self.sj = "今週" if span == "week" else "今日"
        self.gname = GN[game]
        self.rk, self.cache = rk, {}
        items = [(f"{GN[game]}相場", th.accent if th.name != "light" else (255, 255, 255))]
        for pct, name, price, *_ in all_rows:
            items.append((f"{name} ¥{price:,} {'▲' if pct > 0 else '▼'}{abs(pct):.1f}%", th.up if pct > 0 else th.down))
        self.strip = V.ticker_strip(th, items) if th.ticker else None

    def photo(self, key, size):
        return _photo(key, self.rk, self.cache, size)

    def base(self, t, dots=None, foot=True):
        im, _ = V.canvas(self.th)
        V.header(im, self.th, dots)
        if foot:
            V.footer(im, self.th, _foot(self.span))
        return im

    def tick(self, im, t):
        V.draw_ticker(im, self.strip, t + self.t0)


class Hook:
    """最初の1.8秒：1位をぼかしてチラ見せ"""
    transition = "fade"

    def __init__(self, c):
        self.c, self.dur = c, 1.9
        self.events = [(0.0, "riser"), (1.2, "pop")]
        th = c.th
        self.bg = c.base(0)
        pct, name, price, base, key, _ = c.rows[0]
        ph = c.photo(key, 520)
        card, cd = layer(560, 560)
        cd.rounded_rectangle((0, 0, 559, 559), 30, fill=th.card + (255,))
        if ph:
            card.alpha_composite(ph, (20, 20))
        card = V.blur(card, 22)
        cd = ImageDraw.Draw(card)
        cd.text((280, 280), "？", font=FD(260), fill=c.col + (255,), anchor="mm")
        self.card = card
        self.l1 = text_layer(f"{c.sj}の{c.word}1位は", FB(84), th.pink)
        self.l2 = text_layer("まさかの…？", FD(120), c.col)
        self.l3 = band_layer(f"{c.gname} BOX相場ランキング", 50, c.col)
        self.l4 = text_layer("最後まで見てね👀".replace("👀", ""), FB(48, "Bold"), th.pink2)

    def frame(self, t):
        im = self.bg.copy()
        self.c.tick(im, t)
        put(im, self.l3, V.VW / 2, 300, scale=back(prog(t, 0, 0.3)))
        put(im, self.l1, V.VW / 2, 440, alpha=prog(t, 0.1, 0.35))
        put(im, self.card, V.VW / 2, 860, scale=1.0 + 0.06 * t)
        put(im, self.l2, V.VW / 2, 1270, scale=back(prog(t, 0.45, 0.8)))
        put(im, self.l4, V.VW / 2, 1420, alpha=prog(t, 0.9, 1.2))
        return im


class Intro:
    def __init__(self, c):
        self.c, self.dur = c, 2.2
        self.events = [(0.0, "hit"), (0.5, "pop")]
        th = c.th
        self.bg = c.base(0)
        self.pts = [q for _, q in c.rows[0][5]]
        self.l_game = text_layer(c.gname, FD(120 if c.game == "pokemon" else 92), th.pink)
        self.l_title = text_layer(f"{c.sj}のBOX相場", FB(110), th.pink)
        self.l_band = band_layer(f"{c.word}ランキング{c.arrow}", 100, c.col)
        n = len(c.rows)
        self.l_sub = text_layer(f"TOP{n}を{n}位から発表", FB(60), th.pink2)
        td = c.today
        self.l_date = text_layer(f"{td.month}/{td.day}({X.WEEK[td.weekday()]})時点", FB(48, "Bold"), th.pink2)

    def frame(self, t):
        im = self.bg.copy()
        self.c.tick(im, t)
        v = self.pts
        if len(v) > 1:
            lay, _ = layer(V.VW, V.VH)
            V.line_chart(lay, (40, 1240, V.VW - 40, 1600), v, eo(prog(t, 0, 2.0)), self.c.col, self.c.th)
            lay.putalpha(lay.getchannel("A").point(lambda a: a // 3))
            im.alpha_composite(lay)
        put(im, self.l_game, V.VW / 2, 440 - 120 * (1 - eo(prog(t, 0, 0.35))), alpha=prog(t, 0, 0.25))
        put(im, self.l_title, V.VW / 2, 610, alpha=eo(prog(t, 0.2, 0.5)))
        put(im, self.l_band, V.VW / 2, 810, scale=back(prog(t, 0.5, 0.85)))
        put(im, self.l_sub, V.VW / 2, 1000, alpha=prog(t, 0.9, 1.2))
        put(im, self.l_date, V.VW / 2, 1100, alpha=prog(t, 1.0, 1.3))
        return im


class BoxPage:
    def __init__(self, c, r):
        self.c, self.r, self.dur = c, r, 3.6
        th = c.th
        pct, name, price, base, key, pts = c.rows[r]
        self.pct, self.price, self.base = pct, price, base
        self.prev_l = "先週" if c.span == "week" else "前"
        n = len(c.rows)
        self.bg = c.base(0, dots=(n, r + 1))
        put(self.bg, band_layer(f"{c.gname} {c.sj}の{c.word}ランキング", 42, c.col), V.VW / 2, 268)
        d = ImageDraw.Draw(self.bg)
        d.text((V.VW / 2, 965), V.fit(d, name, FB(60), V.VW - 100), font=FB(60), fill=th.pink, anchor="mm")
        self.cb = (50, 1215, V.VW - 50, V.VH - 250)
        x0, y0, x1, y1 = self.cb
        d.rounded_rectangle(self.cb, 22, fill=th.card, outline=th.rule if th.name == "dark" else None, width=2)
        d.text((x0 + 26, y0 + 16), "30日の値段の動き", font=FB(28, "Bold"), fill=th.cink2)
        self.v = [q for _, q in pts]
        self.dates = [dd for dd, _ in pts]
        self.plot = (x0 + 40, y0 + 76, x1 - 130, y1 - 54)
        if self.dates:
            d.text((self.plot[0], y1 - 18), _md(self.dates[0]), font=FB(24, "Medium"), fill=th.cink2, anchor="ls")
            d.text((self.plot[2], y1 - 18), _md(self.dates[-1]), font=FB(24, "Medium"), fill=th.cink2, anchor="rs")
        medal = X.MEDAL[r] if r < 3 else th.pink2
        if th.name == "game" and sum(th.paper) > 500:
            medal = th.pink  # 黄色の背景では金色が見えにくいので紺に
        self.l_rank = text_layer(f"第{r + 1}位", FD(110), medal, stroke=4 if th.name == "game" else 0,
                                 stroke_fill=(255, 255, 255) if th.name == "game" else None)
        ph = c.photo(key, 420)
        self.l_photo = None
        if ph:
            card, cd = layer(460, 460)
            cd.rounded_rectangle((0, 0, 459, 459), 26, fill=(255, 255, 255, 255))
            card.alpha_composite(ph, (20, 20))
            self.l_photo = card
        self.l_prices = text_layer(f"{self.prev_l} ¥{base:,}  →  直近 ¥{price:,}", FB(44), th.pink)
        rnd = random.Random(r * 7 + 3)
        self.conf = [(rnd.uniform(0, V.VW), rnd.uniform(-700, -20), rnd.uniform(-60, 60), rnd.uniform(500, 900),
                      rnd.uniform(0, 6.28), rnd.choice([th.up, (214, 165, 33), (40, 120, 220), (0, 170, 110), (240, 140, 0)]))
                     for _ in range(120)]
        self.events = [(0.05, "pop")] + [(0.5 + 0.1 * k, "tick") for k in range(15)]
        if r == 0:
            self.events = [(0.05, "pop"), (0.3, "drumroll"), (2.0, "crash" if c.kind == "up" else "boom")]
        else:
            self.events.append((2.0, "hit"))

    def frame(self, t):
        c, th = self.c, self.c.th
        im = self.bg.copy()
        c.tick(im, t)
        put(im, self.l_rank, V.VW / 2, 385, scale=back(prog(t, 0, 0.35)))
        if self.l_photo:
            put(im, self.l_photo, V.VW / 2, 685, scale=0.85 + 0.15 * eo(prog(t, 0.05, 0.45)), alpha=prog(t, 0.05, 0.35))
        x0, y0, x1, y1 = self.cb
        lay, _ = layer(x1 - x0, y1 - y0)
        V.line_chart(lay, self.plot, self.v, eo(prog(t, 0.4, 2.0)), c.col, th, base=self.base,
                     base_label=f"{self.prev_l}\n¥{self.base:,}", ox=x0, oy=y0)
        im.alpha_composite(lay, (x0, y0))
        q = eo(prog(t, 0.5, 2.0))
        pulse = 1 + 0.18 * math.sin(math.pi * prog(t, 2.0, 2.3))
        put(im, text_layer(f"{c.arrow}{abs(self.pct) * q:.1f}%", FB(130), c.col), V.VW / 2, 1075, scale=pulse, alpha=prog(t, 0.45, 0.6))
        put(im, self.l_prices, V.VW / 2, 1168, alpha=prog(t, 2.0, 2.3))
        if self.r == 0 and t > 2.0:
            tt = t - 2.0
            if c.kind == "up":
                lay, d = layer(V.VW, V.VH)
                for x, y, vx, vy, rot, cc in self.conf:
                    cx, cy = x + vx * tt, y + vy * tt
                    if 0 < cy < V.VH:
                        w = 10 + 8 * abs(math.sin(rot + tt * 8))
                        d.rectangle((cx - w / 2, cy - 7, cx + w / 2, cy + 7), fill=cc + (255,))
                im.alpha_composite(lay)
            elif tt < 0.7:
                amp = 24 * (1 - tt / 0.7)
                dx, dy = int(amp * math.sin(tt * 70)), int(amp * 0.6 * math.cos(tt * 55))
                sh = Image.new("RGBA", (V.VW, V.VH), th.paper + (255,))
                sh.alpha_composite(im, (max(0, dx), max(0, dy)), (max(0, -dx), max(0, -dy)))
                im = sh
        return im


class Summary:
    transition = "fade"

    def __init__(self, c):
        self.c, self.dur = c, 4.8
        th = c.th
        self.bg = c.base(0)
        put(self.bg, band_layer(f"まとめ｜{c.gname} {c.sj}の{c.word}TOP{len(c.rows)}", 48, c.col), V.VW / 2, 290)
        self.mx = max(abs(r[0]) for r in c.rows) or 1
        self.cards = []
        for r, (pct, name, price, base, key, _) in enumerate(c.rows):
            card, d = layer(V.VW - 80, 200)
            d.rounded_rectangle((0, 0, V.VW - 81, 199), 22, fill=th.card + (255,), outline=th.rule + (255,), width=2)
            medal = X.MEDAL[r] if r < 3 else th.cink2
            d.ellipse((16, 58, 100, 142), fill=medal + (255,))
            d.text((58, 100), str(r + 1), font=FB(50), fill=(255, 255, 255, 255), anchor="mm")
            ph = c.photo(key, 150)
            if ph:
                card.alpha_composite(ph, (118, 25))
            d.text((290, 30), V.fit(d, name, FB(40), V.VW - 80 - 290 - 190), font=FB(40), fill=th.cink + (255,))
            d.text((V.VW - 80 - 24, 34), f"¥{price:,}", font=FB(36), fill=th.cink + (255,), anchor="ra")
            self.cards.append(card)
        self.l_save = text_layer("保存して相場チェック！", FB(54), th.pink)
        self.events = [(0.15 + r * 0.22 + 0.3, "ding") for r in range(len(c.rows))]

    def frame(self, t):
        c = self.c
        im = self.bg.copy()
        c.tick(im, t)
        for r, card in enumerate(self.cards):
            st = 0.15 + r * 0.22
            p = eo(prog(t, st, st + 0.4))
            if p <= 0:
                continue
            y = 390 + r * 218
            x = 40 + int((1 - p) * V.VW)
            if x < V.VW:
                im.alpha_composite(card, (x, y), (0, 0, min(card.width, V.VW - x), card.height))
            b = eo(prog(t, st + 0.3, st + 1.2))
            pct = abs(c.rows[r][0])
            full = 470 * pct / self.mx
            d = ImageDraw.Draw(im)
            bx0, by0 = x + 290, y + 100
            if b > 0:
                d.rounded_rectangle((bx0, by0, bx0 + max(16, full * b), by0 + 62), 12, fill=c.col)
                d.text((bx0 + max(16, full * b) + 14, by0 + 31), f"{c.arrow}{pct * b:.1f}%", font=FB(46), fill=c.col, anchor="lm")
        n = len(c.rows)
        pulse = 1 + 0.08 * math.sin(math.pi * 2 * max(0.0, t - 2.4) / 0.8) if t > 2.4 else 1
        put(im, self.l_save, V.VW / 2, 390 + n * 218 + 50, scale=pulse, alpha=prog(t, 2.2, 2.5))
        return im


class Outro:
    transition = "fade"

    def __init__(self, c):
        self.c, self.dur = c, 2.8
        th = c.th
        self.bg = c.base(0, foot=False)
        self.ls = [(text_layer("BOXの相場グラフ・", FB(76), th.pink), 560, 0.0),
                   (text_layer("抽選の締切は", FB(76), th.pink), 660, 0.1),
                   (text_layer("トレカ抽選ナビ", FD(110), th.accent), 830, 0.3),
                   (text_layer("tcg-chusen.com", FB(60, "Bold"), th.pink2), 960, 0.5),
                   (text_layer("フォローで相場ランキングが届きます", FB(48, "Bold"), th.pink), 1310, 0.9)]
        self.band = band_layer("プロフィールのリンクから", 60, th.accent, (255, 255, 255) if th.accent != (255, 196, 37) else (13, 30, 66))
        self.events = [(0.6, "pop")]

    def frame(self, t):
        im = self.bg.copy()
        self.c.tick(im, t)
        for l, y, st in self.ls:
            put(im, l, V.VW / 2, y + 40 * (1 - eo(prog(t, st, st + 0.35))), alpha=prog(t, st, st + 0.3))
        put(im, self.band, V.VW / 2, 1140, scale=back(prog(t, 0.6, 0.95)) * (1 + 0.06 * math.sin(max(0.0, t - 1.0) * 7)))
        return im


def _rk():
    """BOXの写真：楽天から自動で選んだもの＋手で決めたもの（settings の rakuten_fixed が優先）"""
    from common import load_settings
    rk = dict(load_json("rakuten.json", {}))
    for k, v in (load_settings().get("rakuten_fixed") or {}).items():
        rk[k] = dict(rk.get(k) or {}, **v)
    return rk


def make(out_dir, kind, span, game, rows, today=None, theme="dark", all_rows=None, hook=True, music=True):
    """動画を1本つくってパスを返す。ランキングが空なら None"""
    today = today or now().date()
    if not rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    th = V.theme(theme, game)
    c = Ctx(th, kind, span, game, rows, all_rows or rows, _rk(), today)
    sc = ([Hook(c)] if hook else []) + [Intro(c)] + [BoxPage(c, r) for r in range(len(rows) - 1, -1, -1)] + [Summary(c), Outro(c)]
    t0 = 0.0
    for s_ in sc:  # 電光掲示板は動画全体で流れ続ける
        s_.c.t0 = t0
        s_.t0 = t0
        t0 += s_.dur
    for s_ in sc:
        s_.frame = _bind_t0(s_)
    mp4 = out_dir / f"box_{game}_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_{theme}_{today:%m%d}.mp4"
    return V.render(sc, mp4, th, music=music)


def _bind_t0(s_):
    f = s_.frame
    def g(t):
        s_.c.t0 = s_.t0
        return f(t)
    return g


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


def yt_meta(kind, span, game, rows, today):
    """YouTube のタイトル・説明・タグ"""
    word = "上昇" if kind == "up" else "下落"
    sj = "今週" if span == "week" else "今日"
    gs = "ポケカ" if game == "pokemon" else "ワンピカード"
    title = f"【{gs}相場】{sj}のBOX{word}ランキングTOP{len(rows)}｜1位はまさかの…？（{today.month}/{today.day}）#shorts"
    desc = (caption(kind, span, game, rows) + "\n\n"
            "▼BOXの相場グラフ・抽選の締切はこちら\nトレカ抽選ナビ https://tcg-chusen.com/souba/\n\n"
            "※値段はスニダンで成立した取引（1BOX）の1日の平均から、直近数日と1週間前ごろの中央値を比べています。"
            "値上がり・値下がりを約束するものではありません。\n#shorts")
    tags = (["ポケカ", "ポケモンカード", "ポケカ相場", "BOX相場", "トレカ", "相場ランキング"] if game == "pokemon"
            else ["ワンピースカード", "ワンピカード", "ワンピース相場", "BOX相場", "トレカ", "相場ランキング"])
    return title, desc, tags


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "video"
    span = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("week", "day") else "week"
    themes = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--theme=")), ["light"])
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), [])  # 例: pokemon-up,onepiece-up
    today = now().date()
    rk_all = rankings(span, today)
    # YouTube は1本ずつ時間をずらして予約公開（今日の18時・19時・20時・21時）
    from datetime import datetime, timezone
    slots = {"pokemon-up": 18, "onepiece-up": 19, "pokemon-down": 20, "onepiece-down": 21}
    for th in themes:
        for game in GN:
            all_rows = (rk_all["up"].get(game) or []) + (rk_all["down"].get(game) or [])
            for kind in ("up", "down"):
                if only and f"{game}-{kind}" not in only:
                    continue
                rows = rk_all[kind].get(game) or []
                p = make(out, kind, span, game, rows, today, theme=th, all_rows=all_rows)
                print(th, game, kind, p, [(round(x[0], 1), x[1]) for x in rows])
                if not p:
                    continue
                note = ""
                if "--youtube" in sys.argv:
                    import youtube
                    title, desc, tags = yt_meta(kind, span, game, rows, today)
                    hh = slots[f"{game}-{kind}"]
                    at = datetime(today.year, today.month, today.day, hh, 0, tzinfo=now().tzinfo)
                    at_s = at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if at > now() else None
                    try:
                        test = "--yt-private" in sys.argv  # テスト：非公開で上げるだけ
                        vid = youtube.upload(p, ("【テスト】" if test else "") + title, desc, tags, publish_at=None if test else at_s,
                                             key=None if test else f"{today}|{game}|{kind}|{span}", private=test)
                        if vid:
                            note = f"\n▶YouTube：https://youtube.com/shorts/{vid}" + ("（非公開のテスト）" if test else f"（{hh}時に公開）" if at_s else "")
                    except Exception as e:
                        log(f"YouTube: 失敗 {e}")
                        note = f"\n⚠YouTubeへの投稿に失敗：{str(e)[:150]}"
                if "--send" in sys.argv:
                    send(p, "🎬ランキング動画（TikTokなどに手で投稿する用）" + note + "\n\n" + caption(kind, span, game, rows))
