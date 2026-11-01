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


FPS = 30


@lru_cache(maxsize=None)
def FB(size, w="Black"):
    return X.F(size, w)


@lru_cache(maxsize=None)
def FD(size):
    return X.DELA(size)


def _eo(x):
    """だんだんゆっくり止まる（0〜1）"""
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _back(x):
    """少し大きくなってから戻る（ポンと出る）"""
    x = max(0.0, min(1.0, x))
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _prog(t, a, b):
    return max(0.0, min(1.0, (t - a) / (b - a))) if b > a else float(t >= a)


def _canvas():
    im = Image.new("RGBA", (VW, VH), X.PAPER + (255,))
    return im, ImageDraw.Draw(im)


def _layer(w, h):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _text_layer(txt, font, fill, pad=10):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), txt, font=font)
    im, d = _layer(r - l + pad * 2, b - t + pad * 2)
    d.text((pad - l, pad - t), txt, font=font, fill=fill)
    return im


def _band_layer(txt, size, fill):
    f = FB(size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = tmp.textlength(txt, font=f)
    w, h = int(tw + 60), int(size * 1.5)
    im, d = _layer(w, h)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 20, fill=fill)
    d.text((w / 2, h / 2), txt, font=f, fill=(255, 255, 255), anchor="mm")
    return im


def _put(base, layer, cx, cy, scale=1.0, alpha=1.0):
    """layer を中心 (cx, cy) に、大きさ scale・濃さ alpha で重ねる"""
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.BILINEAR)
    if alpha < 0.999:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    x, y = int(cx - layer.width / 2), int(cy - layer.height / 2)
    base.alpha_composite(layer, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))


def _header(d):
    d.rectangle((0, 0, VW, 170), fill=X.CARD)
    d.text((VW / 2, 92), "トレカ抽選ナビ", font=FD(56), fill=X.INK, anchor="mm")


def _footer(d, span):
    d.rectangle((0, VH - 230, VW, VH), fill=X.CARD)
    d.text((VW / 2, VH - 150), "毎日の相場は「トレカ抽選ナビ」で", font=FB(44), fill=X.INK, anchor="mm")
    note = "直近数日と1週間前ごろの値段（中央値）を比べています" if span == "week" else "前の3日の値段（中央値）と比べています"
    d.text((VW / 2, VH - 92), "スニダンで成立した取引（1BOX）の1日の平均から", font=FB(28, "Medium"), fill=X.INK2, anchor="mm")
    d.text((VW / 2, VH - 52), note, font=FB(26, "Medium"), fill=X.INK2, anchor="mm")


def _md(s):
    d = date.fromisoformat(s)
    return f"{d.month}/{d.day}"


# ---------------- 場面ごとの絵（t 秒目の1コマ） ----------------

class Intro:
    def __init__(self, kind, span, game, rows, today):
        self.dur = 2.6
        col = UP if kind == "up" else DOWN
        word, arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
        sj = "今週" if span == "week" else "今日"
        self.bg, d = _canvas()
        _header(d)
        _footer(d, span)
        self.col = col
        self.pts = [p for _, p in (rows[0][5] if rows else [])]
        self.l_game = _text_layer(GN[game], FD(120 if game == "pokemon" else 92), X.INK)
        self.l_title = _text_layer(f"{sj}のBOX相場", FB(110), X.INK)
        self.l_band = _band_layer(f"{word}ランキング{arrow}", 100, col)
        self.l_sub = _text_layer(f"TOP{len(rows)}を{len(rows)}位から発表", FB(60), X.INK2)
        self.l_date = _text_layer(f"{today.month}/{today.day}({X.WEEK[today.weekday()]})時点", FB(48, "Bold"), X.INK2)

    def frame(self, t):
        im = self.bg.copy()
        # うしろで大きなチャートの線が伸びていく（うすく）
        v = self.pts
        if len(v) > 1:
            lo, hi = min(v), max(v) or 1
            hi = hi if hi > lo else lo + 1
            p = _eo(_prog(t, 0, 2.0))
            n = max(2, int(len(v) * p))
            xy = [(40 + (VW - 80) * k / (len(v) - 1), 1560 - 260 * (q - lo) / (hi - lo)) for k, q in enumerate(v[:n])]
            lay, d = _layer(VW, VH)
            d.line(xy, fill=self.col + (60,), width=14, joint="curve")
            im.alpha_composite(lay)
        _put(im, self.l_game, VW / 2, 430 - 120 * (1 - _eo(_prog(t, 0, 0.35))), alpha=_prog(t, 0, 0.25))
        _put(im, self.l_title, VW / 2, 600, alpha=_eo(_prog(t, 0.2, 0.5)))
        _put(im, self.l_band, VW / 2, 800, scale=_back(_prog(t, 0.5, 0.85)))
        _put(im, self.l_sub, VW / 2, 990, alpha=_prog(t, 1.0, 1.3))
        _put(im, self.l_date, VW / 2, 1090, alpha=_prog(t, 1.1, 1.4))
        return im


class BoxPage:
    def __init__(self, kind, span, game, rows, r, rk, cache):
        self.dur = 3.6
        self.kind, self.r = kind, r
        pct, name, price, base, key, pts = rows[r]
        self.pct, self.price, self.base = pct, price, base
        self.col = col = UP if kind == "up" else DOWN
        word, self.arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
        sj = "今週" if span == "week" else "今日"
        self.prev_l = "先週" if span == "week" else "前"
        self.bg, d = _canvas()
        _header(d)
        _footer(d, span)
        _put(self.bg, _band_layer(f"{GN[game]} {sj}の{word}ランキング", 44, col), VW / 2, 250)
        d = ImageDraw.Draw(self.bg)
        d.text((VW / 2, 935), X._fit(d, name, FB(60), VW - 100), font=FB(60), fill=X.INK, anchor="mm")
        # チャートの枠・目盛り
        self.cb = (50, 1190, VW - 50, VH - 250)
        x0, y0, x1, y1 = self.cb
        d.rounded_rectangle(self.cb, 22, fill=X.CARD)
        d.text((x0 + 26, y0 + 18), "30日の値段の動き", font=FB(28, "Bold"), fill=X.INK2)
        self.v = [q for _, q in pts]
        self.dates = [dd for dd, _ in pts]
        lo, hi = min(self.v + [base]), max(self.v + [base])
        padv = max(1, (hi - lo) * 0.12)
        self.lo, self.hi = lo - padv, hi + padv
        self.px0, self.px1, self.py0, self.py1 = x0 + 40, x1 - 130, y0 + 80, y1 - 56
        if self.dates:
            d.text((self.px0, y1 - 22), _md(self.dates[0]), font=FB(24, "Medium"), fill=X.INK2, anchor="ls")
            d.text((self.px1, y1 - 22), _md(self.dates[-1]), font=FB(24, "Medium"), fill=X.INK2, anchor="rs")
        medal = X.MEDAL[r] if r < 3 else X.INK2
        self.l_rank = _text_layer(f"第{r + 1}位", FD(110), medal)
        ph = _photo(key, rk, cache, 420)
        self.l_photo = None
        if ph:
            card, cd = _layer(460, 460)
            cd.rounded_rectangle((0, 0, 459, 459), 26, fill=(255, 255, 255, 255))
            card.alpha_composite(ph, (20, 20))
            self.l_photo = card
        self.l_prices = _text_layer(f"{self.prev_l} ¥{base:,}  →  直近 ¥{price:,}", FB(44), X.INK)
        rnd = random.Random(r * 7 + 3)
        self.conf = [(rnd.uniform(0, VW), rnd.uniform(-600, -20), rnd.uniform(-60, 60), rnd.uniform(500, 900),
                      rnd.uniform(0, 6.28), rnd.choice([UP, (214, 165, 33), (40, 120, 220), (0, 150, 100), (240, 140, 0)]))
                     for _ in range(110)]

    def _y(self, q):
        return self.py1 - (self.py1 - self.py0) * (q - self.lo) / (self.hi - self.lo)

    def frame(self, t):
        im = self.bg.copy()
        col = self.col
        # 順位がポン・写真がふわっと
        _put(im, self.l_rank, VW / 2, 360, scale=_back(_prog(t, 0, 0.35)))
        if self.l_photo:
            _put(im, self.l_photo, VW / 2, 650, scale=0.85 + 0.15 * _eo(_prog(t, 0.05, 0.45)), alpha=_prog(t, 0.05, 0.35))
        # チャート：先週の値段の点線と、30日の線が伸びていく
        x0, y0, x1, y1 = self.cb
        lay, d = _layer(x1 - x0, y1 - y0)
        ox, oy = x0, y0
        if _prog(t, 0.3, 0.6) > 0:
            a = int(255 * _prog(t, 0.3, 0.6))
            by = self._y(self.base) - oy
            xx = self.px0 - ox
            while xx < self.px1 - ox:
                d.line((xx, by, min(xx + 16, self.px1 - ox), by), fill=X.INK2 + (a,), width=3)
                xx += 28
            d.text((self.px1 - ox + 10, by), f"{self.prev_l}\n¥{self.base:,}", font=FB(24, "Bold"), fill=X.INK2 + (a,), anchor="lm")
        v = self.v
        p = _eo(_prog(t, 0.4, 2.0))
        if len(v) > 1 and p > 0:
            pos = p * (len(v) - 1)
            k = int(pos)
            xy = [(self.px0 - ox + (self.px1 - self.px0) * j / (len(v) - 1), self._y(q) - oy) for j, q in enumerate(v[:k + 1])]
            cur = v[k] if k >= len(v) - 1 else v[k] + (v[k + 1] - v[k]) * (pos - k)
            xy.append((self.px0 - ox + (self.px1 - self.px0) * pos / (len(v) - 1), self._y(cur) - oy))
            d.polygon(xy + [(xy[-1][0], self.py1 - oy), (xy[0][0], self.py1 - oy)], fill=col + (38,))
            d.line(xy, fill=col + (255,), width=8, joint="curve")
            ex, ey = xy[-1]
            d.ellipse((ex - 14, ey - 14, ex + 14, ey + 14), fill=col + (255,), outline=(255, 255, 255, 255), width=4)
            # 値札（線の先についていく）
            tag = f"¥{round(cur):,}"
            tw = d.textlength(tag, font=FB(34))
            bx = min(max(ex - tw / 2 - 16, 10), (x1 - x0) - tw - 42)
            byy = max(ey - 78, 54)
            d.rounded_rectangle((bx, byy, bx + tw + 32, byy + 52), 12, fill=X.INK + (235,))
            d.text((bx + 16, byy + 26), tag, font=FB(34), fill=(255, 255, 255, 255), anchor="lm")
        im.alpha_composite(lay, (ox, oy))
        # ％が数えあがる → 止まったらドン
        q = _eo(_prog(t, 0.5, 2.0))
        val = abs(self.pct) * q
        pulse = 1 + 0.18 * math.sin(math.pi * _prog(t, 2.0, 2.3))
        _put(im, _text_layer(f"{self.arrow}{val:.1f}%", FB(130), col), VW / 2, 1045, scale=pulse, alpha=_prog(t, 0.45, 0.6))
        _put(im, self.l_prices, VW / 2, 1150, alpha=_prog(t, 2.0, 2.3))
        # 1位：上昇は紙吹雪、下落は画面がゆれる
        if self.r == 0 and t > 2.0:
            tt = t - 2.0
            if self.kind == "up":
                lay, d = _layer(VW, VH)
                for x, y, vx, vy, rot, c in self.conf:
                    cx, cy = x + vx * tt, y + vy * tt
                    if 0 < cy < VH:
                        w = 10 + 8 * abs(math.sin(rot + tt * 8))
                        d.rectangle((cx - w / 2, cy - 7, cx + w / 2, cy + 7), fill=c + (255,))
                im.alpha_composite(lay)
            elif tt < 0.6:
                amp = 22 * (1 - tt / 0.6)
                dx, dy = int(amp * math.sin(tt * 70)), int(amp * 0.6 * math.cos(tt * 55))
                sh = Image.new("RGBA", (VW, VH), X.PAPER + (255,))
                sh.alpha_composite(im, (max(0, dx), max(0, dy)), (max(0, -dx), max(0, -dy)))
                im = sh
        return im


class Summary:
    def __init__(self, kind, span, game, rows, rk, cache):
        self.dur = 4.8
        self.rows, self.kind = rows, kind
        self.col = col = UP if kind == "up" else DOWN
        word, self.arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
        sj = "今週" if span == "week" else "今日"
        self.bg, d = _canvas()
        _header(d)
        _footer(d, span)
        _put(self.bg, _band_layer(f"まとめ｜{GN[game]} {sj}の{word}TOP{len(rows)}", 50, col), VW / 2, 270)
        self.mx = max(abs(r[0]) for r in rows) or 1
        self.cards = []
        for r, (pct, name, price, base, key, _) in enumerate(rows):
            card, d = _layer(VW - 80, 200)
            d.rounded_rectangle((0, 0, VW - 81, 199), 22, fill=X.CARD + (255,), outline=X.RULE + (255,), width=2)
            medal = X.MEDAL[r] if r < 3 else X.INK2
            d.ellipse((16, 58, 100, 142), fill=medal + (255,))
            d.text((58, 100), str(r + 1), font=FB(50), fill=(255, 255, 255, 255), anchor="mm")
            ph = _photo(key, rk, cache, 150)
            if ph:
                card.alpha_composite(ph, (118, 25))
            d.text((290, 30), X._fit(d, name, FB(40), VW - 80 - 290 - 190), font=FB(40), fill=X.INK + (255,))
            d.text((VW - 80 - 24, 34), f"¥{price:,}", font=FB(36), fill=X.INK + (255,), anchor="ra")
            self.cards.append(card)
        self.l_save = _text_layer("保存して相場チェック！", FB(54), X.INK)

    def frame(self, t):
        im = self.bg.copy()
        for r, card in enumerate(self.cards):
            st = 0.15 + r * 0.22
            p = _eo(_prog(t, st, st + 0.4))
            if p <= 0:
                continue
            y = 380 + r * 218
            x = 40 + int((1 - p) * VW)
            if x < VW:
                im.alpha_composite(card, (x, y), (0, 0, min(card.width, VW - x), card.height))
            # 棒グラフがのびて、％が数えあがる
            b = _eo(_prog(t, st + 0.3, st + 1.2))
            pct = abs(self.rows[r][0])
            full = 470 * pct / self.mx
            d = ImageDraw.Draw(im)
            bx0, by0 = x + 290, y + 100
            if b > 0:
                d.rounded_rectangle((bx0, by0, bx0 + max(16, full * b), by0 + 62), 12, fill=self.col)
                d.text((bx0 + max(16, full * b) + 14, by0 + 31), f"{self.arrow}{pct * b:.1f}%", font=FB(46), fill=self.col, anchor="lm")
        n = len(self.rows)
        pulse = 1 + 0.08 * math.sin(math.pi * 2 * max(0.0, t - 2.4) / 0.8) if t > 2.4 else 1
        _put(im, self.l_save, VW / 2, 380 + n * 218 + 50, scale=pulse, alpha=_prog(t, 2.2, 2.5))
        return im


class Outro:
    def __init__(self, span):
        self.dur = 2.8
        self.bg, d = _canvas()
        _header(d)
        self.ls = [(_text_layer("BOXの相場グラフ・", FB(76), X.INK), 560, 0.0),
                   (_text_layer("抽選の締切は", FB(76), X.INK), 660, 0.1),
                   (_text_layer("トレカ抽選ナビ", FD(110), X.RED), 830, 0.3),
                   (_text_layer("tcg-chusen.com", FB(60, "Bold"), X.INK2), 960, 0.5),
                   (_text_layer("フォローで相場ランキングが届きます", FB(48, "Bold"), X.INK), 1310, 0.9)]
        self.band = _band_layer("プロフィールのリンクから", 60, X.RED)

    def frame(self, t):
        im = self.bg.copy()
        for l, y, st in self.ls:
            _put(im, l, VW / 2, y + 40 * (1 - _eo(_prog(t, st, st + 0.35))), alpha=_prog(t, st, st + 0.3))
        pulse = _back(_prog(t, 0.6, 0.95)) * (1 + 0.06 * math.sin(max(0.0, t - 1.0) * 7))
        _put(im, self.band, VW / 2, 1140, scale=pulse)
        return im


def scenes(kind, span, game, rows, rk, today):
    cache = {}
    out = [Intro(kind, span, game, rows, today)]
    out += [BoxPage(kind, span, game, rows, r, rk, cache) for r in range(len(rows) - 1, -1, -1)]
    out += [Summary(kind, span, game, rows, rk, cache), Outro(span)]
    return out


def make(out_dir, kind, span, game, rows, today=None):
    """動画を1本つくってパスを返す。ランキングが空なら None"""
    today = today or now().date()
    if not rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sc = scenes(kind, span, game, rows, load_json("rakuten.json", {}), today)
    total = sum(s_.dur for s_ in sc)
    mp4 = out_dir / f"box_{game}_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_{today:%m%d}.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}",
                           "-r", str(FPS), "-i", "-", "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo",
                           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    SL = 0.35  # 横にスライドする時間
    last = None
    for si, s_ in enumerate(sc):
        nf = int(round(s_.dur * FPS))
        for f in range(nf):
            t = f / FPS
            im = s_.frame(t).convert("RGB")
            if last is not None and t < SL:
                p = _eo(t / SL)
                dx = int(VW * p)
                if si == len(sc) - 1:
                    im = Image.blend(last, im, p)  # おわりは ふわっと
                else:
                    c = Image.new("RGB", (VW, VH))
                    c.paste(last, (-dx, 0))
                    c.paste(im, (VW - dx, 0))
                    im = c
            ff.stdin.write(im.tobytes())
            if f == nf - 1:
                last = im
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg が失敗")
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
