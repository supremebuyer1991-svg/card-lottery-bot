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
  表紙（0.5秒）→ フック「1週間で◯円 上がった／下がったBOXは？」→ 5位〜2位を1ページずつ（横にスライド）
  → 1位の前の「ため」→ 1位 → 保存用のまとめ → おわり（全部で25秒ほど）
  ページの中は動く：順位がポンと出る・値段が先週の値から今の値まで数えあがる（30日のチャートの線も一緒に伸びる）・
  「1週間で±◯円」がドン・定価が分かる弾は「定価◯円の約◯倍」。1位は紙吹雪（上昇）／画面がゆれる（下落）
  書くのは事実（データの数字）だけ。売り買いをすすめる言葉・値段の予想は入れない。1コマずつ絵を描いて ffmpeg に流しこむ

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
    """1本の動画で共通のもの（見た目・電光掲示板・写真・定価）"""
    def __init__(self, th, kind, span, game, rows, all_rows, rk, today):
        self.th, self.kind, self.span, self.game, self.rows, self.today = th, kind, span, game, rows, today
        self.col = th.up if kind == "up" else th.down
        self.word, self.arrow = ("上昇", "↑") if kind == "up" else ("下落", "↓")
        self.sj = "今週" if span == "week" else "今日"
        self.span_w = "1週間で" if span == "week" else "直近3日とくらべて"
        self.sign = "+" if kind == "up" else "−"
        self.verb = "上がった" if kind == "up" else "下がった"
        self.gname = GN[game]
        self.rk, self.cache = rk, {}
        # 定価（公式の希望小売価格・1BOX）。分かる弾だけ（state/souba.json の teika）
        self.teika = {k: v.get("teika") for k, v in (load_json("souba.json", {}).get("items") or {}).items() if v.get("teika")}
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

    def mystery(self, size, blur_r=20):
        """1位の箱をぼかして「？」をのせたカード（名前は最後まで出さない）"""
        th = self.th
        ph = self.photo(self.rows[0][4], size - 40)
        card, cd = layer(size, size)
        cd.rounded_rectangle((0, 0, size - 1, size - 1), 34, fill=th.card + (255,), outline=self.col + (255,), width=10)
        if ph:
            card.alpha_composite(ph, (20, 20))
        card = V.blur(card, blur_r)
        mask = Image.new("L", (size, size), 0)  # ぼかしで角ににじんだ灰色を切りおとす
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), 34, fill=255)
        card.putalpha(mask)
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, size - 1, size - 1), 34, outline=self.col + (255,), width=10)
        cd.text((size / 2, size * 0.48), "？", font=FD(int(size * 0.55)), fill=self.col + (255,), anchor="mm")
        return card


class Cover:
    """いちばん最初の0.5秒＝TikTok・ショートの表紙（サムネ）になる1枚（11/10）
    ・大きな文字で「何のランキングか」と「1位の上がり幅（名前は伏せる）」
    ・2〜4位の箱の写真を並べ、1位はぼかして「？」"""
    transition = "cut"

    def __init__(self, c):
        self.c, self.dur = c, 0.5
        self.events = []
        th = c.th
        im, _ = V.canvas(th)
        W, H = V.VW, V.VH
        d = ImageDraw.Draw(im)
        # 上半分を色の帯にして目立たせる
        d.rectangle((0, 0, W, 760), fill=c.col)
        d.polygon([(0, 760), (W, 700), (W, 760)], fill=th.paper)
        put(im, text_layer(c.gname, FD(170 if c.game == "pokemon" else 120), (255, 255, 255)), W / 2, 230)
        put(im, text_layer(f"{c.sj}のBOX相場", FB(110), (255, 255, 255)), W / 2, 420)
        put(im, text_layer(f"{c.word}TOP{len(c.rows)}", FD(150), (255, 236, 120)), W / 2, 590)
        # 1位（ぼかし＋？）
        pct = c.rows[0][0]
        ph = c.photo(c.rows[0][4], 520)
        card, cd = layer(560, 560)
        cd.rounded_rectangle((0, 0, 559, 559), 34, fill=th.card + (255,), outline=c.col + (255,), width=10)
        if ph:
            card.alpha_composite(ph, (20, 20))
        card = V.blur(card, 18)
        cd = ImageDraw.Draw(card)
        cd.text((280, 270), "？", font=FD(300), fill=c.col + (255,), anchor="mm")
        put(im, card, W / 2 - 150, 1110)
        sign = "+" if pct > 0 else "−"
        badge = band_layer(f"1位 {sign}{abs(pct):.1f}%", 78, c.col)
        put(im, badge, W / 2 - 150, 1440)
        # 2〜4位の写真
        for i, row in enumerate(c.rows[1:4]):
            p2 = c.photo(row[4], 230)
            t, td = layer(250, 250)
            td.rounded_rectangle((0, 0, 249, 249), 22, fill=th.card + (255,), outline=th.rule + (255,), width=4)
            if p2:
                t.alpha_composite(p2, (10, 10))
            td = ImageDraw.Draw(t)
            td.ellipse((6, 6, 76, 76), fill=c.col + (255,))
            td.text((41, 41), str(i + 2), font=FD(48), fill=(255, 255, 255, 255), anchor="mm")
            put(im, t, W - 200, 900 + i * 270)
        td_ = c.today
        put(im, text_layer(f"{td_.month}/{td_.day}時点・スニダンの取引", FB(42, "Bold"), th.pink2), W / 2, 1660)
        put(im, text_layer("トレカ抽選ナビ", FD(60), th.pink), W / 2, 1780)
        self.im = im

    def frame(self, t):
        return self.im.copy()


def _fitw(lay, w):
    """絵 lay が幅 w をこえるなら、おさまる倍率"""
    return min(1.0, w / lay.width)


def _yen_ticks(t0, t1, k0=0.9, k1=1.9, gap=0.07):
    """数字が数えあがる間のカチカチ（だんだん高く）"""
    out, t = [], t0
    while t < t1 - 0.01:
        out.append((t, f"tick:{k0 + (k1 - k0) * (t - t0) / (t1 - t0):.2f}"))
        t += gap
    return out


class Hook:
    """表紙のすぐあとの2.5秒：「1週間で ◯円 上がった（下がった）BOXは？」と数字で引きこむ。1位の名前は出さない"""
    transition = "cut"

    def __init__(self, c):
        self.c, self.dur = c, 2.5
        th = c.th
        self.bg = c.base(0)
        pct, name, price, base, key, _ = c.rows[0]
        self.diff = abs(price - base)
        self.card = c.mystery(360)
        self.l_band = band_layer(f"{c.gname} {c.sj}のBOX相場", 52, c.col)
        self.l1 = text_layer(c.span_w, FB(100), th.pink)
        self.l3 = text_layer(f"{c.verb}BOXは？", FB(96), th.pink)
        tk = c.teika.get(key)
        self.l_teika = band_layer(f"定価は ¥{tk:,}", 50, th.pink) if tk else None
        self.l_last = text_layer(f"1位は最後に発表  {len(c.rows)}位から", FB(50), th.pink2)
        self.land = 1.0
        self.events = [(0.0, "riser")] + _yen_ticks(0.1, self.land) + [(self.land, "hit"), (1.5, "pop")]

    def frame(self, t):
        c = self.c
        im = self.bg.copy()
        c.tick(im, t)
        W = V.VW
        put(im, self.l_band, W / 2, 310, scale=back(prog(t, 0, 0.25)))
        put(im, self.l1, W / 2, 470, alpha=prog(t, 0, 0.12))
        q = eo(prog(t, 0.1, self.land))
        num = text_layer(f"{c.sign}¥{round(self.diff * q):,}", FB(230), c.col)
        pulse = 1 + 0.14 * math.sin(math.pi * prog(t, self.land, self.land + 0.3))
        put(im, num, W / 2, 680, scale=_fitw(num, 940) * pulse, alpha=prog(t, 0.03, 0.15))
        put(im, self.l3, W / 2, 890, scale=back(prog(t, self.land, self.land + 0.3)))
        put(im, self.card, W / 2, 1150, scale=(0.94 + 0.03 * t) * back(prog(t, 0.2, 0.55)))
        if self.l_teika:
            put(im, self.l_teika, W / 2, 1405, scale=back(prog(t, 1.5, 1.8)))
        put(im, self.l_last, W / 2, 1505, alpha=prog(t, 1.6, 1.9))
        return im


class BoxPage:
    """1つの弾につき1ページ：順位 → 箱 → 値段が先週の値から今の値まで数えあがる（チャートの線も一緒に伸びる）→ 「1週間で ±◯円」がドン
    大事な文字は、TikTok・ショートのボタンや説明文が重ならない所（上220〜下1500・右はしを空ける）に置く"""
    tdur = 0.25

    def __init__(self, c, r):
        n = len(c.rows)
        self.c, self.r = c, r
        self.top = r == 0
        # 下の順位はテンポよく、上に行くほど少しゆっくり。長さは拍（0.5秒）にそろえる
        self.dur = 4.0 if self.top else (3.0 if r <= 2 else 2.5)
        self.land = 1.0 if (self.top or r > 2) else 1.5   # 値段が止まる時（拍の上）
        self.c0 = 0.15 if self.top else 0.3              # 数えはじめ
        if self.top:
            self.transition = "cut"
        th = c.th
        pct, name, price, base, key, pts = c.rows[r]
        self.pct, self.price, self.base = pct, price, base
        self.prev_l = "先週" if c.span == "week" else "前"
        W = V.VW
        self.bg = c.base(0)
        d = ImageDraw.Draw(self.bg)
        # 上の行：何のランキングか（途中から見た人にも分かるように）＋ 5→1 の進み具合（1位は「？」のまま）
        d.text((50, 285), f"{c.gname} {c.sj}の{c.word}TOP{n}", font=FB(36 if c.game == "pokemon" else 32), fill=th.pink2, anchor="lm")
        for k in range(n):
            rank = n - k
            cx = W - 50 - 30 - (n - 1 - k) * 68
            on, done = rank == r + 1, rank > r + 1
            rad = 30 if on else 24
            d.ellipse((cx - rad, 285 - rad, cx + rad, 285 + rad), fill=c.col if on else (th.pink2 if done else th.card),
                      outline=None if (on or done) else th.rule, width=3)
            d.text((cx, 285), "？" if (rank == 1 and not on) else str(rank), font=FB(34 if on else 26),
                   fill=(255, 255, 255) if (on or done) else th.pink2, anchor="mm")
        # 名前
        d.text((W / 2, 890), V.fit(d, name, FB(70), W - 120), font=FB(70), fill=th.pink, anchor="mm")
        # チャートの箱
        self.cb = (50, 1300, W - 50, V.VH - 250)
        x0, y0, x1, y1 = self.cb
        d.rounded_rectangle(self.cb, 22, fill=th.card, outline=th.rule if th.name == "dark" else None, width=2)
        d.text((x0 + 26, y0 + 14), "30日の値段の動き（1日ごとの平均）", font=FB(26, "Bold"), fill=th.cink2)
        self.v = [q for _, q in pts]
        self.dates = [dd for dd, _ in pts]
        self.plot = (x0 + 40, y0 + 70, x1 - 150, y1 - 50)
        if self.dates:
            d.text((self.plot[0], y1 - 16), _md(self.dates[0]), font=FB(24, "Medium"), fill=th.cink2, anchor="ls")
            d.text((self.plot[2], y1 - 16), _md(self.dates[-1]), font=FB(24, "Medium"), fill=th.cink2, anchor="rs")
        # 順位の札・箱の写真
        medal = X.MEDAL[r] if r < 3 else th.pink2
        if th.name == "game" and sum(th.paper) > 500:
            medal = th.pink
        self.l_rank = band_layer(f"第{r + 1}位", 84 if not self.top else 96, medal)
        ph = c.photo(key, 400)
        card, cd = layer(440, 440)
        cd.rounded_rectangle((0, 0, 439, 439), 30, fill=(255, 255, 255, 255), outline=(c.col if self.top else th.rule) + (255,), width=8 if self.top else 3)
        if ph:
            card.alpha_composite(ph, (20, 20))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle((0, 0, 439, 439), 30, outline=(c.col if self.top else th.rule) + (255,), width=8 if self.top else 3)
        else:  # 写真が取れなかったとき：順位の数字を大きく
            cd.text((220, 235), str(r + 1), font=FD(300), fill=medal + (255,), anchor="mm")
        self.l_photo = card
        # 「1週間で +¥5,449 ↑29.6%」
        diff = abs(price - base)
        b1 = band_layer(f"{c.span_w} {c.sign}¥{diff:,}", 58, c.col)
        b2 = text_layer(f"{c.arrow}{abs(pct):.1f}%", FB(72), c.col)
        lay, _ = layer(b1.width + 20 + b2.width, max(b1.height, b2.height))
        lay.alpha_composite(b1, (0, (lay.height - b1.height) // 2))
        lay.alpha_composite(b2, (b1.width + 20, (lay.height - b2.height) // 2))
        self.l_delta = lay
        tk = c.teika.get(key)
        self.l_teika = None
        if tk:
            s = f"定価 ¥{tk:,} の 約{price / tk:.1f}倍" if price >= tk * 1.1 else f"定価 ¥{tk:,}"
            self.l_teika = text_layer(s, FB(42), th.pink2)
        rnd = random.Random(r * 7 + 3)
        self.conf = [(rnd.uniform(0, W), rnd.uniform(-900, -20), rnd.uniform(-60, 60), rnd.uniform(600, 1000),
                      rnd.uniform(0, 6.28), rnd.choice([th.up, (214, 165, 33), (40, 120, 220), (0, 170, 110), (240, 140, 0)]))
                     for _ in range(130)]
        self.events = [(0.05, "pop")] + _yen_ticks(self.c0, self.land) + [(self.land, "hit")]
        if self.top:
            self.events = [(0.0, "crash" if c.kind == "up" else "boom")] + _yen_ticks(self.c0, self.land, 1.2, 2.2) + [(self.land, "hit"), (self.land, "shine")]

    def frame(self, t):
        c, th = self.c, self.c.th
        W = V.VW
        im = self.bg.copy()
        c.tick(im, t)
        put(im, self.l_photo, W / 2, 600, scale=0.86 + 0.14 * back(prog(t, 0.0, 0.35)), alpha=prog(t, 0.0, 0.2))
        put(im, self.l_rank, W / 2, 385, scale=back(prog(t, 0.05, 0.35)))
        # チャート（線は値段の数えあげと一緒に伸びる）
        x0, y0, x1, y1 = self.cb
        lay, _ = layer(x1 - x0, y1 - y0)
        q = eo(prog(t, self.c0, self.land))
        V.line_chart(lay, self.plot, self.v, q, c.col, th, base=self.base,
                     base_label=f"{self.prev_l} ¥{self.base:,}", ox=x0, oy=y0, tag=False, label_in=True)
        im.alpha_composite(lay, (x0, y0))
        # 値段：先週の値 → 今の値
        cur = self.base + (self.price - self.base) * q
        pulse = 1 + 0.12 * math.sin(math.pi * prog(t, self.land, self.land + 0.28))
        num = text_layer(f"¥{round(cur):,}", FB(170), th.pink)
        put(im, num, W / 2, 1030, scale=_fitw(num, 900) * pulse, alpha=prog(t, 0.1, 0.25))
        put(im, self.l_delta, W / 2, 1165, scale=_fitw(self.l_delta, 960) * back(prog(t, self.land, self.land + 0.3)))
        if self.l_teika:
            put(im, self.l_teika, W / 2, 1250, alpha=prog(t, self.land + 0.35, self.land + 0.65))
        if self.top:
            if c.kind == "up":
                lay, d = layer(W, V.VH)
                for x, y, vx, vy, rot, cc in self.conf:
                    cx, cy = x + vx * t, y + vy * t
                    if 0 < cy < V.VH:
                        w = 10 + 8 * abs(math.sin(rot + t * 8))
                        d.rectangle((cx - w / 2, cy - 7, cx + w / 2, cy + 7), fill=cc + (255,))
                im.alpha_composite(lay)
            elif t < 0.7:
                amp = 26 * (1 - t / 0.7)
                dx, dy = int(amp * math.sin(t * 70)), int(amp * 0.6 * math.cos(t * 55))
                sh = Image.new("RGBA", (W, V.VH), th.paper + (255,))
                sh.alpha_composite(im, (max(0, dx), max(0, dy)), (max(0, -dx), max(0, -dy)))
                im = sh
            if t < 0.3:  # 発表のしゅんかんの白い光
                im = Image.blend(im, Image.new("RGBA", im.size, (255, 255, 255, 255)), 0.85 * (1 - t / 0.3))
        return im


class Tease:
    """1位の発表の前の「ため」1.5秒：画面を色でぬって「第1位は…」、ぼかした箱がドクン・ドクン（BGMは小さく、ドラムロール）"""
    transition = "fade"
    tdur = 0.2

    def __init__(self, c):
        self.c, self.dur = c, 1.5
        th = c.th
        W = V.VW
        im = Image.new("RGBA", (W, V.VH), c.col + (255,))
        self.bg = im
        self.l1 = text_layer("第1位は…", FD(170), (255, 255, 255))
        self.card = c.mystery(520)
        pct, name, price, base, *_ = c.rows[0]
        self.l2 = band_layer(f"{c.span_w} {c.sign}¥{abs(price - base):,}", 72, (255, 255, 255), c.col)
        self.events = [(0.0, "duck:1.5"), (0.0, "drumroll"), (0.0, "heart"), (0.5, "heart"), (1.0, "heart")]

    def frame(self, t):
        im = self.bg.copy()
        W = V.VW
        put(im, self.l1, W / 2, 470, scale=_fitw(self.l1, 940) * back(prog(t, 0, 0.3)))
        beat = (t % 0.5) / 0.5
        put(im, self.card, W / 2, 940, scale=1.0 + 0.1 * t + 0.07 * max(0.0, 1 - beat * 3))
        put(im, self.l2, W / 2, 1360, scale=back(prog(t, 0.3, 0.6)))
        return im


class Summary:
    """まとめの1枚（スクショ・保存用）：5つをパパッと並べて、「あなたの箱、入ってた？」"""
    transition = "fade"

    def __init__(self, c):
        self.c, self.dur = c, 3.5
        th = c.th
        W = V.VW
        self.bg = c.base(0)
        n = len(c.rows)
        put(self.bg, band_layer(f"保存用まとめ｜{c.gname} {c.sj}の{c.word}TOP{n}", 44 if c.game == "pokemon" else 38, c.col), W / 2, 300)
        self.cards = []
        cw, self.ch, self.gap = W - 100, 158, 14
        for r, (pct, name, price, base, key, _) in enumerate(c.rows):
            card, d = layer(cw, self.ch)
            d.rounded_rectangle((0, 0, cw - 1, self.ch - 1), 22, fill=th.card + (255,), outline=th.rule + (255,), width=2)
            medal = X.MEDAL[r] if r < 3 else th.cink2
            d.ellipse((16, 40, 94, 118), fill=medal + (255,))
            d.text((55, 79), str(r + 1), font=FB(48), fill=(255, 255, 255, 255), anchor="mm")
            ph = c.photo(key, 130)
            tx = 112
            if ph:
                card.alpha_composite(ph, (108, 14))
                tx = 256
            # 右はし（ボタンが重なる所）は空ける：％は右から130内がわまで
            px = cw - 130
            pw = d.textlength(f"{c.arrow}{abs(pct):.1f}%", font=FB(56))
            d.text((px, 100), f"{c.arrow}{abs(pct):.1f}%", font=FB(56), fill=c.col + (255,), anchor="rm")
            d.text((tx, 22), V.fit(d, name, FB(42), cw - tx - 40), font=FB(42), fill=th.cink + (255,))
            d.text((tx, 84), f"¥{price:,}", font=FB(46), fill=th.cink + (255,))
            yw = d.textlength(f"¥{price:,}", font=FB(46))
            s = f"{c.sign}¥{abs(price - base):,}"
            if tx + yw + 20 + d.textlength(s, font=FB(32)) < px - pw - 16:
                d.text((tx + yw + 20, 96), s, font=FB(32), fill=c.col + (255,))
            self.cards.append(card)
        self.y0 = 375
        yb = self.y0 + n * (self.ch + self.gap)
        self.l_q = text_layer("あなたの箱、入ってた？", FB(70), th.pink)
        self.l_save = band_layer("保存して来週とくらべよう", 52, th.pink)
        self.yq, self.ys = yb + 60, yb + 170
        self.events = [(0.1 + r * 0.12, "tick:%.2f" % (1.0 + r * 0.15)) for r in range(n)] + [(1.0, "ding"), (1.5, "pop")]

    def frame(self, t):
        c = self.c
        W = V.VW
        im = self.bg.copy()
        c.tick(im, t)
        for r, card in enumerate(self.cards):
            st = 0.05 + r * 0.12
            p = eo(prog(t, st, st + 0.3))
            if p <= 0:
                continue
            y = self.y0 + r * (self.ch + self.gap)
            x = 50 + int((1 - p) * W)
            if x < W:
                im.alpha_composite(card, (x, y), (0, 0, min(card.width, W - x), card.height))
        put(im, self.l_q, W / 2, self.yq, scale=back(prog(t, 1.0, 1.3)))
        pulse = 1 + 0.05 * math.sin(max(0.0, t - 1.8) * 9)
        put(im, self.l_save, W / 2, self.ys, scale=back(prog(t, 1.5, 1.8)) * pulse)
        return im


class Outro:
    transition = "fade"

    def __init__(self, c):
        self.c, self.dur = c, 2.5
        th = c.th
        self.bg = c.base(0, foot=False)
        self.ls = [(text_layer("毎日のBOX相場グラフ・", FB(72), th.pink), 520, 0.0),
                   (text_layer("抽選の締切は", FB(72), th.pink), 620, 0.08),
                   (text_layer("トレカ抽選ナビ", FD(110), th.accent), 790, 0.2),
                   (text_layer("tcg-chusen.com", FB(60, "Bold"), th.pink2), 920, 0.35),
                   (text_layer("フォローで毎週のランキングが届く", FB(50), th.pink), 1270, 0.7)]
        self.band = band_layer("プロフィールのリンクから", 60, th.accent, (255, 255, 255) if th.accent != (255, 196, 37) else (13, 30, 66))
        self.events = [(0.5, "pop")]

    def frame(self, t):
        im = self.bg.copy()
        self.c.tick(im, t)
        for l, y, st in self.ls:
            put(im, l, V.VW / 2, y + 40 * (1 - eo(prog(t, st, st + 0.3))), alpha=prog(t, st, st + 0.25))
        put(im, self.band, V.VW / 2, 1100, scale=back(prog(t, 0.5, 0.8)) * (1 + 0.06 * math.sin(max(0.0, t - 0.9) * 7)))
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
    # 表紙 → 数字のフック → 5位〜2位（テンポよく）→ 1位の前のため → 1位 → 保存用まとめ → おわり
    # 場面の長さはどれも0.5秒の倍数＝BGM（120拍/分）の拍に合わせてあるので、切りかえと「ドン」が拍に乗る
    sc = [Cover(c)] + ([Hook(c)] if hook else [])
    for r in range(len(rows) - 1, -1, -1):
        if r == 0 and len(rows) > 1:
            sc.append(Tease(c))
        sc.append(BoxPage(c, r))
    sc += [Summary(c), Outro(c)]
    t0 = 0.0
    for s_ in sc:  # 電光掲示板は動画全体で流れ続ける
        s_.c.t0 = t0
        s_.t0 = t0
        t0 += s_.dur
    for s_ in sc:
        s_.frame = _bind_t0(s_)
    mp4 = out_dir / f"box_{game}_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_{theme}_{today:%m%d}.mp4"
    return V.render(sc, mp4, th, music=music, bpm=120, rich=True)


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
    lines.append("#ポケカ #ポケカ相場 #ポケモンカード #トレカ" if game == "pokemon" else "#ワンピースカード #ワンピースカード相場 #BOX相場 #トレカ")
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
    gs = "ポケカ" if game == "pokemon" else "ワンピースカード"
    diff = abs(rows[0][2] - rows[0][3])
    lead = (f"1週間で{diff:,}円" if span == "week" else f"{diff:,}円") + ("上がった" if kind == "up" else "下がった") + "BOXは？"
    title = f"【{gs}相場】{lead}{sj}の{word}TOP{len(rows)}（{today.month}/{today.day}）#shorts"
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
    # YouTube は1日1本：水＝ワンピ下落・金＝ポケカ上昇・土＝ワンピ上昇・日＝ポケカ下落。どれも19時に予約公開
    from datetime import datetime, timezone
    WEEK_PLAN = {2: "onepiece-down", 4: "pokemon-up", 5: "onepiece-up", 6: "pokemon-down"}
    if "--weekly-slot" in sys.argv:
        only = [WEEK_PLAN[today.weekday()]] if today.weekday() in WEEK_PLAN else []
        if not only:
            print("今日はランキング動画の日ではない")
            sys.exit(0)
    slots = {k: 19 for k in ("pokemon-up", "onepiece-up", "pokemon-down", "onepiece-down")}
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
                if "--tiktok" in sys.argv:
                    import tiktok
                    try:
                        if tiktok.upload_draft(p):
                            note += "\n📱TikTokの下書きに送りました（アプリの受信箱から曲をのせて「投稿」）"
                    except Exception as e:
                        log(f"TikTok: 失敗 {e}")
                        note += f"\n⚠TikTokの下書きに失敗：{str(e)[:150]}"
                if "--send" in sys.argv:
                    send(p, "🎬ランキング動画（TikTokなどに手で投稿する用）" + note + "\n\n" + caption(kind, span, game, rows))
