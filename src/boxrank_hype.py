"""BOX相場ランキングの縦長動画「ハイテンション版」（黒×金×赤／黒×青×紫・スロットや抽選の当たり演出ふう）

boxrank.py の make()（白ベースの落ち着いた版）とは別物。データは同じ boxrank.rankings() を使う。
  表紙＋スロット（「1週間で +¥◯◯」の数字が回って止まる）→ 下の順位から1つずつ（順位ドン→カードがめくれる→値段が数えあがる→％ドン）
  → 1位の前の「ため」（3つのリールが1つずつ止まる）→ 1位（最大の演出）→ まとめ → おわり
  150BPM（1拍＝0.4秒＝12コマ）の自作BGMに、場面と効果音を全部合わせてある

守ること（サイトの決まり）
  ・出す数字はデータにあるものだけ（上昇率・値段・先週との差）。値段の予想はしない
  ・「買い」「売り」をすすめる言葉、もうけを約束する言葉は書かない。「激アツ」「確定」は順位発表の合図としてだけ使う
  ・実在のパチンコ・カジノなどのロゴやキャラは使わない。絵は全部ここで描いたもの、音も全部ここで作ったもの
  ・全画面が白く光るのは「ドン」の瞬間だけ（1秒に2回まで・白の濃さは6割まで）。光に弱い人への配慮

使い方: python src/boxrank_hype.py 出力フォルダ [week|day] [--only=pokemon-up,onepiece-down]
"""
import math
import random
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from common import now
import boxrank as B
import vidkit as V
import ximage as X
from vidkit import FB, FD, eo, back, prog, layer

VW, VH, FPS, SR = V.VW, V.VH, V.FPS, V.SR
BEAT = 0.4            # 150BPM。30コマ/秒でちょうど12コマ
QW, QH = VW // 4, VH // 4   # 背景は1/4の大きさで計算して引きのばす（速くするため）
FLASH_MAX = 0.6       # 全画面の白い光の濃さの上限

# 色：up＝黒×赤×金 / down＝黒×青×紫
PAL = {
    "up": dict(core0=(70, 6, 26), core1=(215, 36, 8), ray=(255, 196, 50), accent=(228, 20, 46), line=(255, 240, 190),
               sty="gold", sty2="fire", conf=[(255, 214, 60), (255, 255, 255), (255, 70, 60), (255, 150, 30), (255, 236, 150)]),
    "down": dict(core0=(8, 18, 84), core1=(70, 22, 170), ray=(80, 205, 255), accent=(70, 80, 235), line=(200, 240, 255),
                 sty="ice", sty2="volt", conf=[(190, 240, 255), (255, 255, 255), (110, 170, 255), (170, 120, 255)]),
}

# 文字の見た目：stops＝中の色（上→下）、strokes＝ふち（内→外。太さは文字の大きさに対する割合）
STY = {
    "gold": dict(stops=[(0, (255, 253, 205)), (.38, (255, 210, 50)), (.5, (255, 255, 240)), (.6, (246, 152, 12)), (1, (178, 82, 0))],
                 strokes=[(.03, (104, 36, 0)), (.065, (255, 255, 255)), (.115, (206, 12, 34)), (.155, (0, 0, 0))]),
    "fire": dict(stops=[(0, (255, 255, 200)), (.45, (255, 200, 30)), (.75, (255, 90, 20)), (1, (225, 20, 30))],
                 strokes=[(.03, (120, 0, 0)), (.07, (255, 255, 255)), (.12, (0, 0, 0))]),
    "ice": dict(stops=[(0, (255, 255, 255)), (.4, (150, 232, 255)), (.5, (255, 255, 255)), (.62, (60, 150, 255)), (1, (36, 60, 205))],
                strokes=[(.03, (8, 20, 100)), (.065, (255, 255, 255)), (.115, (112, 60, 240)), (.155, (0, 0, 0))]),
    "volt": dict(stops=[(0, (255, 255, 255)), (.5, (190, 215, 255)), (1, (150, 110, 255))],
                 strokes=[(.03, (20, 10, 90)), (.07, (255, 255, 255)), (.12, (0, 0, 0))]),
    "white": dict(stops=[(0, (255, 255, 255)), (1, (226, 230, 240))], strokes=[(.085, (0, 0, 0))]),
    "dim": dict(stops=[(0, (190, 196, 214)), (1, (150, 156, 178))], strokes=[(.085, (0, 0, 0))]),
}

_TMP = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


# ---------------- 文字 ----------------
def _grad(w, h, stops, y0, y1):
    ys = np.clip((np.arange(h) - y0) / max(1, y1 - y0), 0, 1)
    ps = [p for p, _ in stops]
    cs = np.array([c for _, c in stops], dtype=float)
    col = np.stack([np.interp(ys, ps, cs[:, k]) for k in range(3)], 1).astype(np.uint8)
    return Image.fromarray(np.ascontiguousarray(np.repeat(col[:, None, :], w, axis=1)), "RGB")


def _two(txt, f, size, st, adv=None, ext=None):
    """ふちの絵（under）と中の絵（over）を分けて作る。文字を横に並べるとき、ふちが隣の字にかぶらないように"""
    ws = [max(1, int(round(size * r))) for r, _ in st["strokes"]]
    pad = max(ws) + 4
    l, t, r, b = _TMP.textbbox((0, 0), txt, font=f)
    if ext:
        t, b = ext
    w = int((adv if adv else r - l) + pad * 2)
    h = int(b - t + pad * 2)
    ox = pad - l + ((adv - (r - l)) / 2 if adv else 0)
    oy = pad - t
    under, d = layer(w, h)
    for sw, (_, col) in sorted(zip(ws, st["strokes"]), key=lambda z: -z[0]):
        d.text((ox, oy), txt, font=f, fill=col + (255,), stroke_width=sw, stroke_fill=col + (255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((ox, oy), txt, font=f, fill=255)
    over, _ = layer(w, h)
    over.paste(_grad(w, h, st["stops"], pad, h - pad), (0, 0), mask)
    return under, over


def _skew(im, k):
    """右にかたむける（上が右へ）"""
    if not k:
        return im
    w, h = im.size
    return im.transform((int(w + k * h), h), Image.AFFINE, (1, k, -k * h, 0, 1, 0), Image.BILINEAR)


def glow_under(im, col, r, strength=1.0):
    """絵の下に、ぼんやり光る影を足す"""
    p = int(r * 2.2)
    out, _ = layer(im.width + p * 2, im.height + p * 2)
    a = Image.new("L", out.size, 0)
    a.paste(im.getchannel("A"), (p, p))
    a = a.filter(ImageFilter.GaussianBlur(r)).point(lambda v: min(255, int(v * 1.5 * strength)))
    out.paste(Image.new("RGB", out.size, col), (0, 0), a)
    out.alpha_composite(im, (p, p))
    return out


@lru_cache(maxsize=512)
def ftext(txt, size, sty="gold", font="dela", skew=0.0, glow=None, maxw=0):
    """ふち取りつきの大きな文字。maxw より広ければ縮める"""
    f = FD(size) if font == "dela" else FB(size, "Black")
    u, o = _two(txt, f, size, STY[sty])
    u.alpha_composite(o)
    im = _skew(u, skew)
    if glow:
        im = glow_under(im, glow, size * 0.1)
    if maxw and im.width > maxw:
        im = im.resize((maxw, max(1, int(im.height * maxw / im.width))), Image.LANCZOS)
    return im


class Glyphs:
    """数字（0〜9 と ¥ , + − % .）を1字ずつ絵にしておき、並べて金額や％にする（数えあがりを速く描くため）"""
    CH = "0123456789¥,+−%."

    def __init__(self, size, sty, skew=0.0):
        f = FD(size)
        st = STY[sty]
        self.size = size
        l, t, r, b = _TMP.textbbox((0, 0), "0123456789¥%", font=f)
        dw = max(_TMP.textlength(ch, font=f) for ch in "0123456789")
        self.pad = max(max(1, int(round(size * rr))) for rr, _ in st["strokes"]) + 4
        self.u, self.o, self.adv = {}, {}, {}
        for ch in self.CH:
            adv = dw if ch.isdigit() else _TMP.textlength(ch, font=f)
            u, o = _two(ch, f, size, st, adv=adv, ext=(t, b))
            self.u[ch], self.o[ch] = _skew(u, skew), _skew(o, skew)
            self.adv[ch] = int(adv + size * 0.02)
        self.h = self.u["0"].height
        self.extra = self.u["0"].width - int(dw)   # ふち＋かたむきの分

    def width(self, s):
        return sum(self.adv[ch] for ch in s) + self.extra

    def one(self, ch):
        im = self.u[ch].copy()
        im.alpha_composite(self.o[ch])
        return im

    def layer(self, s):
        im, _ = layer(self.width(s), self.h)
        for part in (self.u, self.o):
            x = 0
            for ch in s:
                im.alpha_composite(part[ch], (x, 0))
                x += self.adv[ch]
        return im


@lru_cache(maxsize=32)
def glyphs(size, sty, skew=0.0):
    return Glyphs(size, sty, skew)


def pill(txt, size, fill, ink=(255, 255, 255), edge=(255, 255, 255), weight="Black"):
    f = FB(size, weight)
    tw = _TMP.textlength(txt, font=f)
    w, h = int(tw + size * 1.3), int(size * 1.62)
    im, d = layer(w + 8, h + 8)
    d.rounded_rectangle((0, 0, w + 7, h + 7), h // 2 + 4, fill=(0, 0, 0, 255))
    d.rounded_rectangle((4, 4, w + 3, h + 3), h // 2, fill=fill + (255,), outline=edge + (255,), width=4)
    d.text((w / 2 + 4, h / 2 + 4), txt, font=f, fill=ink + (255,), anchor="mm")
    return im


def put(base, lay, cx, cy, scale=1.0, alpha=1.0, sx=1.0):
    """lay（透明つき）を base（RGB）の中心 (cx, cy) に重ねる。scale＝大きさ、sx＝横だけの倍率（カードをめくる用）"""
    if scale <= 0.01 or alpha <= 0.01 or abs(sx) <= 0.01:
        return
    if abs(scale - 1) > 0.005 or abs(sx - 1) > 0.005:
        lay = lay.resize((max(1, int(lay.width * scale * abs(sx))), max(1, int(lay.height * scale))), Image.BILINEAR)
    m = lay if alpha >= 0.999 else lay.getchannel("A").point(lambda v: int(v * alpha))
    base.paste(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)), m)


def slam(t, t0, dur=0.22, big=2.3):
    """ドン！と出る大きさ（大→1。少し行きすぎて戻る）。まだなら 0"""
    if t < t0:
        return 0.0
    p = prog(t, t0, t0 + dur)
    return big + (1 - big) * back(p) if p < 1 else 1 + 0.035 * math.exp(-(t - t0 - dur) * 9) * math.sin((t - t0 - dur) * 30)


def decay(t, t0, tau):
    return math.exp(-(t - t0) / tau) if t >= t0 else 0.0


# ---------------- 背景 ----------------
class Bg:
    """背景：up＝中心から回る金色の光のすじ / down＝上から落ちる青い光のすじ。lv（0〜1）が大きいほど派手"""

    def __init__(self, kind):
        self.up = kind == "up"
        P = PAL[kind]
        self.c0, self.c1 = np.array(P["core0"], np.float32), np.array(P["core1"], np.float32)
        self.ray = np.array(P["ray"], np.float32)
        self.yy, self.xx = np.mgrid[0:QH, 0:QW].astype(np.float32)
        self._pc = {}
        self._last = None
        if not self.up:  # 落ちる光：まばらな点を縦に尾を引かせた絵を、下へ流す
            rng = np.random.default_rng(5)
            H2 = QH * 2
            dots = (rng.random((H2, QW)) > 0.9982).astype(np.float32) * rng.uniform(0.4, 1.0, (H2, QW)).astype(np.float32)
            tex = np.zeros((H2, QW), np.float32)
            for k in range(70):
                tex += np.roll(dots, -k, axis=0) * (1 - k / 70) ** 2
            self.tex = np.clip(tex, 0, 1)
            self.rows = np.arange(QH)

    def _polar(self, cx, cy):
        key = (round(cx, 2), round(cy, 2))
        if key not in self._pc:
            dx, dy = self.xx - cx * QW, self.yy - cy * QH
            rad = np.sqrt(dx * dx + dy * dy) / (QH * 0.55)
            ang = np.arctan2(dy, dx)
            glow = np.exp(-rad * 2.0)
            fall = np.clip(rad * 1.5, 0, 1) * np.clip(1.25 - rad * 0.3, 0.3, 1)
            ex, ey = (self.xx / QW - 0.5) * 2, (self.yy / QH - 0.5) * 2
            vig = np.clip(1.08 - 0.30 * (ex * ex) - 0.34 * (ey ** 4), 0.25, 1)
            if len(self._pc) > 6:
                self._pc.clear()
            self._pc[key] = (ang, glow, fall, vig)
        return self._pc[key]

    def frame(self, t, lv=0.5, cx=0.5, cy=0.42, rainbow=False, dim=1.0):
        """背景は1秒に15枚だけ作る（同じ絵を2コマ使う）。描く時間と、動画にする時間の両方が短くなる"""
        t = int(t * FPS / 2 + 1e-6) * 2 / FPS
        key = (t, round(lv, 3), cx, cy, rainbow, round(dim, 3))
        if self._last and self._last[0] == key:
            return self._last[1].copy()
        im = self._make(t, lv, cx, cy, rainbow, dim)
        self._last = (key, im)
        return im.copy()

    def _make(self, t, lv, cx, cy, rainbow, dim):
        ang, glow, fall, vig = self._polar(cx, cy)
        core = self.c0 + (self.c1 - self.c0) * lv
        pulse = 1 + 0.10 * math.exp(-((t % BEAT) / BEAT) * 5)   # 拍に合わせてほんの少し明るく（1割まで）
        if self.up:
            sp = 0.45 + 0.9 * lv
            v = np.clip(np.sin(ang * 12 + t * sp) * 2.2, 0, 1)
            v += 0.55 * np.clip(np.sin(ang * 7 - t * sp * 0.7) * 2.2 - 0.9, 0, 1)
            v *= (0.10 + 0.34 * lv) * fall
        else:
            off = int(t * (260 + 420 * lv))
            v = self.tex[(self.rows - off) % (QH * 2)] * (0.5 + 0.7 * lv)
            v = v + 0.5 * np.clip(np.sin(ang * 9 + t * 0.4) * 2.2 - 0.6, 0, 1) * (0.06 + 0.16 * lv) * fall
        g = (glow * (0.5 + 0.75 * lv))[..., None]
        if rainbow:   # 1位だけ：光のすじが虹色
            h = ang * (3 / math.pi) + t * 1.6
            rc = np.stack([np.cos(h), np.cos(h - 2.094), np.cos(h + 2.094)], -1) * 110 + 145
            out = core * g + rc * v[..., None] * 1.5
        else:
            out = core * g + self.ray * v[..., None]
        out *= (vig * (pulse * dim))[..., None]
        out += 4
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").resize((VW, VH), Image.BILINEAR)


@lru_cache(maxsize=8)
def halo(size, col, power=1.0):
    """丸いぼんやりした光"""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.sqrt((x - size / 2) ** 2 + (y - size / 2) ** 2) / (size / 2)
    a = np.clip(1 - r, 0, 1) ** 1.6 * 255 * power
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., :3] = col
    arr[..., 3] = np.clip(a, 0, 255)
    return Image.fromarray(arr, "RGBA")


# ---------------- 飛びちるもの ----------------
class Burst:
    """1点からはじける紙吹雪（conf）・火花（spark）・ガラスのかけら（shard）"""

    def __init__(self, n, cx, cy, cols, seed=0, speed=(500, 1700), grav=1500, kind="conf", up_bias=0.35, life=2.2):
        r = np.random.default_rng(seed)
        a = r.uniform(0, 2 * np.pi, n)
        s = r.uniform(speed[0], speed[1], n)
        self.vx, self.vy = np.cos(a) * s, np.sin(a) * s - up_bias * s
        self.cx, self.cy, self.g, self.kind, self.life = cx, cy, grav, kind, life
        self.sz = r.uniform(9, 22, n) if kind != "spark" else r.uniform(3, 6, n)
        self.rot, self.rv = r.uniform(0, 6.28, n), r.uniform(-12, 12, n)
        self.col = [cols[k] for k in r.integers(0, len(cols), n)]
        self.n = n

    def draw(self, d, tt):
        if tt < 0 or tt > self.life:
            return
        k = 1.6
        f = (1 - math.exp(-k * tt)) / k            # 空気でだんだん遅く
        x = self.cx + self.vx * f
        y = self.cy + self.vy * f + 0.5 * self.g * tt * tt * 0.7
        fade = 1 if tt < self.life - 0.4 else max(0.0, (self.life - tt) / 0.4)
        for i in range(self.n):
            xi, yi = x[i], y[i]
            if not (-40 < xi < VW + 40 and -40 < yi < VH + 40):
                continue
            s = self.sz[i] * fade
            if s < 1:
                continue
            if self.kind == "spark":
                e = math.exp(-k * tt)
                d.line((xi, yi, xi - self.vx[i] * e * 0.035, yi - (self.vy[i] * e + self.g * tt * 0.7) * 0.035), fill=self.col[i], width=int(s) + 1)
                continue
            r = self.rot[i] + self.rv[i] * tt
            c, sn = math.cos(r), math.sin(r)
            if self.kind == "shard":
                pts = [(xi + c * s * 1.6, yi + sn * s * 1.6), (xi - sn * s * 0.7, yi + c * s * 0.7), (xi - c * s, yi - sn * s * 1.2)]
                d.polygon(pts, fill=self.col[i], outline=(255, 255, 255))
            else:
                w = s * abs(math.cos(r * 1.7 + i))  # ひらひら
                pts = [(xi - c * w - sn * s * .5, yi - sn * w + c * s * .5), (xi + c * w - sn * s * .5, yi + sn * w + c * s * .5),
                       (xi + c * w + sn * s * .5, yi + sn * w - c * s * .5), (xi - c * w + sn * s * .5, yi - sn * w - c * s * .5)]
                d.polygon(pts, fill=self.col[i])


class Rain:
    """上からふり続ける紙吹雪"""

    def __init__(self, n, cols, seed=0):
        r = np.random.default_rng(seed)
        self.x, self.y = r.uniform(0, VW, n), r.uniform(-1500, -20, n)
        self.vx, self.vy = r.uniform(-70, 70, n), r.uniform(520, 980, n)
        self.rot, self.sz = r.uniform(0, 6.28, n), r.uniform(10, 22, n)
        self.col = [cols[k] for k in r.integers(0, len(cols), n)]
        self.n = n

    def draw(self, d, tt):
        if tt < 0:
            return
        for i in range(self.n):
            xi, yi = self.x[i] + self.vx[i] * tt, self.y[i] + self.vy[i] * tt
            if not (-30 < yi < VH + 30):
                continue
            s = self.sz[i]
            w = s * abs(math.sin(self.rot[i] + tt * 7))
            d.rectangle((xi - w / 2, yi - s * .35, xi + w / 2, yi + s * .35), fill=self.col[i])


def embers(d, t, n, up, cols, seed=3):
    """ゆっくり上がる火の粉（up）／落ちる光のつぶ（down）"""
    for i in range(n):
        a = (i * 0.6180339 + seed * 0.37) % 1
        b = (i * 0.7548776 + seed * 0.11) % 1
        v = 120 + 260 * ((i * 0.5698403) % 1)
        y = (b * (VH + 60) - v * t * (1 if up else -1.6)) % (VH + 60) - 30
        x = a * VW + 26 * math.sin(t * (1 + a * 2) + i)
        r = 2 + 3.5 * ((i * 0.3819660) % 1)
        d.ellipse((x - r, y - r, x + r, y + r), fill=cols[i % len(cols)])


def focus_lines(d, cx, cy, seed, n=44, inner=430, col=(255, 255, 255)):
    """集中線（マンガの「ドン！」の線）"""
    rnd = random.Random(seed)
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        w = rnd.uniform(0.004, 0.018)
        r0 = inner * rnd.uniform(0.9, 1.6)
        d.polygon([(cx + math.cos(a) * r0, cy + math.sin(a) * r0 * 1.45),
                   (cx + math.cos(a - w) * 2400, cy + math.sin(a - w) * 2400),
                   (cx + math.cos(a + w) * 2400, cy + math.sin(a + w) * 2400)], fill=col)


def jag(x0, y0, x1, y1, seed, n=9, amp=0.16):
    """ギザギザの線（いなずま・ガラスのひび）"""
    rnd = random.Random(seed)
    L = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / (L or 1), (x1 - x0) / (L or 1)
    pts = [(x0, y0)]
    for k in range(1, n):
        q = k / n
        o = rnd.uniform(-1, 1) * amp * L / n * 2.2
        pts.append((x0 + (x1 - x0) * q + nx * o, y0 + (y1 - y0) * q + ny * o))
    pts.append((x1, y1))
    return pts


def draw_jag(d, pts, p, glow, core, w=4):
    k = max(2, int(len(pts) * min(1.0, p)))
    d.line(pts[:k], fill=glow, width=w * 3, joint="curve")
    d.line(pts[:k], fill=core, width=w, joint="curve")


def ring(d, cx, cy, tt, col, speed=1500, life=0.5, w0=26):
    """広がる輪（衝撃波）"""
    if 0 <= tt < life:
        r = 60 + speed * tt
        w = max(2, int(w0 * (1 - tt / life)))
        d.ellipse((cx - r, cy - r * 0.9, cx + r, cy + r * 0.9), outline=col, width=w)


def post(im, t, hits=(), flashes=(), zooms=()):
    """ゆれ・ズーム・白い光。hits=[(時刻, ゆれ幅)] flashes=[(時刻, 濃さ)] zooms=[(時刻, 倍率の上乗せ)]"""
    z = 1 + sum(a * decay(t, t0, 0.07) for t0, a in zooms)
    if z > 1.004:
        w, h = VW / z, VH / z
        im = im.crop((int((VW - w) / 2), int((VH - h) / 2), int((VW + w) / 2), int((VH + h) / 2))).resize((VW, VH), Image.BILINEAR)
    dx = dy = 0.0
    for t0, amp in hits:
        tt = t - t0
        if 0 <= tt < 0.4:
            k = amp * (1 - tt / 0.4) ** 2
            dx += k * math.sin(tt * 95)
            dy += k * 0.8 * math.cos(tt * 78)
    if abs(dx) >= 1 or abs(dy) >= 1:
        out = Image.new("RGB", (VW, VH), (0, 0, 0))
        out.paste(im, (int(dx), int(dy)))
        im = out
    a = min(FLASH_MAX, sum(p * decay(t, t0, 0.085) for t0, p in flashes))
    if a > 0.02:
        im = Image.blend(im, _WHITE, a)
    return im


_WHITE = Image.new("RGB", (VW, VH), (255, 250, 236))


# ---------------- 回るリール ----------------
class Reel:
    """絵（数字や文字）が縦に回る窓。pos＝いま真ん中にある絵の番号（小数で途中）"""

    def __init__(self, cells, cw, ch):
        n = len(cells)
        self.n, self.cw, self.ch = n, cw, ch
        s, _ = layer(cw, (n + 3) * ch)
        for k in range(-1, n + 2):
            c = cells[k % n]
            s.alpha_composite(c, (int((cw - c.width) / 2), int((k + 1.5) * ch - c.height / 2)))
        self.s = s
        self.b = s.resize((cw, max(1, s.height // 7)), Image.BILINEAR).resize(s.size, Image.BILINEAR)   # 回っている間の残像

    def crop(self, pos, wh, blur=False):
        y0 = int(((pos % self.n) + 1.5) * self.ch - wh / 2)
        return (self.b if blur else self.s).crop((0, y0, self.cw, y0 + int(wh)))


def reel_pos(t, lock, target, v=11.0, d=0.28):
    """lock 秒に target でぴたっと止まる。それまでは回り、最後の d 秒でゆっくりになる。(pos, まだ速く回っているか)"""
    x = lock - t
    if x <= 0:
        return target + 0.07 * math.exp(x * 14) * math.sin(-x * 40), False   # 止まった直後に少しはずむ
    if x > d:
        return target - v * d * 0.5 - v * (x - d), True
    return target - v * d * 0.5 * (x / d) ** 2, False


@lru_cache(maxsize=4)
def shade(w, h):
    """リールの窓の上下を暗くする（丸い筒に見せる）"""
    a = np.abs(np.linspace(-1, 1, h)) ** 2.2 * 215
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 3] = a[:, None].astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def bezel(w, h, P, r=40):
    """リールを入れる枠（金や氷のふち＋中は黒）"""
    im, d = layer(w, h)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=(0, 0, 0, 255))
    g = _grad(w, h, STY[P["sty"]]["stops"], 0, h)
    m = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(m)
    md.rounded_rectangle((5, 5, w - 6, h - 6), r - 4, fill=255)
    im.paste(g, (0, 0), m)
    d.rounded_rectangle((34, 34, w - 35, h - 35), r - 22, fill=(8, 6, 14, 255), outline=(0, 0, 0, 255), width=5)
    return im


def bulbs(d, x0, y0, x1, y1, t, P, step=62):
    """枠のまわりを流れる電球"""
    pts = []
    nx, ny = max(2, int((x1 - x0) / step)), max(2, int((y1 - y0) / step))
    pts += [(x0 + (x1 - x0) * k / nx, y0) for k in range(nx)]
    pts += [(x1, y0 + (y1 - y0) * k / ny) for k in range(ny)]
    pts += [(x1 - (x1 - x0) * k / nx, y1) for k in range(nx)]
    pts += [(x0, y1 - (y1 - y0) * k / ny) for k in range(ny)]
    ph = int(t * 7)
    for k, (x, y) in enumerate(pts):
        on = (k - ph) % 3 == 0
        d.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(0, 0, 0))
        d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(255, 252, 225) if on else tuple(int(v * 0.45) for v in P["ray"]))


# ---------------- 1本の動画で共通のもの ----------------
class Ctx:
    def __init__(self, kind, span, game, rows, rk, today):
        self.kind, self.span, self.game, self.rows, self.today = kind, span, game, rows, today
        self.up = kind == "up"
        self.P = P = PAL[kind]
        self.sty, self.sty2 = P["sty"], P["sty2"]
        self.word, self.sg = ("上昇", "+") if self.up else ("下落", "−")
        self.sj = "今週" if span == "week" else "今日"
        self.per = "1週間で" if span == "week" else "前の3日から"
        self.prev = "先週" if span == "week" else "前"
        self.gname = B.GN[game]
        self.n = len(rows)
        self.mx = max(abs(r[0]) for r in rows) or 1
        self.rk, self.cache = rk, {}
        self.bg = Bg(kind)
        self.em = [P["ray"], P["line"], tuple(int(v * 0.7) for v in P["ray"])]
        # いつも出ているもの：上のサイト名、下の「何を比べた数字か」
        self.top = ftext("トレカ抽選ナビ", 46, "white")
        note, d = layer(VW, 92)
        l2 = "直近数日と1週間前ごろの値段（中央値）を比べています" if span == "week" else "いちばん新しい日と、その前の3日の値段（中央値）を比べています"
        for k, s in enumerate(("スニダンで成立した取引（1BOX）の1日の平均から", l2)):
            d.text((VW / 2, 24 + k * 42), s, font=FB(28, "Bold"), fill=(214, 218, 232, 255), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, 255))
        self.note = note
        self.head = pill(f"{self.gname}｜{self.sj}のBOX相場 {self.word}ランキング", 38, P["accent"])
        # 上昇率・下落率のメーターの中身（下から上へ色が変わる棒）
        self.gbar = _grad(56, 400, list(reversed([(1 - p, c) for p, c in STY[self.sty2]["stops"]])), 0, 400)

    def photo(self, key, size):
        return B._photo(key, self.rk, self.cache, size)

    def diff(self, r):
        return abs(self.rows[r][2] - self.rows[r][3])

    def lv(self, r):
        """演出の強さ：いちばん下の順位＝0 … 1位＝1"""
        return 1.0 if self.n <= 1 else (self.n - 1 - r) / (self.n - 1)

    def card(self, r, size=430):
        """BOXのカード（写真があれば写真、なければ名前のカード）"""
        P = self.P
        name, key = self.rows[r][1], self.rows[r][4]
        im = bezel(size, size, P, r=38)
        d = ImageDraw.Draw(im)
        inner = size - 44
        ph = self.photo(key, inner - 16)
        if ph:
            d.rounded_rectangle((22, 22, size - 23, size - 23), 24, fill=(255, 255, 255, 255))
            im.alpha_composite(ph, (30, 30))
        else:
            g = _grad(inner, inner, [(0, P["core1"]), (1, (10, 8, 20))], 0, inner)
            m = Image.new("L", (inner, inner), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, inner - 1, inner - 1), 24, fill=255)
            im.paste(g, (22, 22), m)
            d.text((size / 2, size * 0.30), "BOX", font=FD(int(size * 0.27)), fill=(255, 255, 255, 46), anchor="mm")
            d.text((size / 2, 70), self.gname, font=FB(30), fill=P["line"] + (255,), anchor="mm")
            # 1行に入る大きさをさがす。長い名前は小さめの字で折り返す
            fs = next((z for z in (58, 52, 46, 42) if d.textlength(name, font=FB(z)) <= inner - 36), 0)
            f = FB(fs or 42)
            lines = [name] if fs else X._wrap(d, name, f, inner - 36, 3)
            y = size * 0.62 - (len(lines) - 1) * 28
            for ln in lines:
                d.text((size / 2, y), ln, font=f, fill=(255, 255, 255, 255), anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, 255))
                y += 56
        return im

    def card_back(self, size=430):
        P = self.P
        im = bezel(size, size, P, r=38)
        d = ImageDraw.Draw(im)
        for k in range(-size, size, 46):
            d.line((34 + max(0, k), 34 + max(0, -k), min(size - 35, k + size - 70) , min(size - 35, size - 70 - k) + 0), fill=tuple(int(v * 0.35) for v in P["core1"]) + (255,), width=10)
        q = ftext("？", int(size * 0.55), self.sty)
        im.alpha_composite(q, (int((size - q.width) / 2), int((size - q.height) / 2)))
        return im

    def finish(self, im):
        put(im, self.top, VW / 2, 128)
        im.paste(self.note, (0, 1574), self.note)
        return im

    def chips(self, cur):
        """上の「5 4 3 2 1」の丸。cur＝いまの順位（0始まり）。None なら全部ついている"""
        n = self.n
        im, d = layer(n * 84 + 20, 84)
        for k in range(n):
            r = n - 1 - k
            cx, cy = 52 + k * 84, 42
            on = cur is not None and r == cur
            done = cur is None or r > cur
            rad = 36 if on else 28
            d.ellipse((cx - rad - 4, cy - rad - 4, cx + rad + 4, cy + rad + 4), fill=(0, 0, 0, 255))
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(self.P["ray"] if on else self.P["accent"] if done else (30, 30, 44)) + (255,),
                      outline=(255, 255, 255, 255) if on else (120, 124, 150, 255), width=4)
            d.text((cx, cy - 2), str(r + 1), font=FD(40 if on else 30), fill=((0, 0, 0) if on else (255, 255, 255) if done else (150, 154, 176)) + (255,), anchor="mm")
        return im


class Scene:
    t0 = 0.0
    events = ()
    bgm = 2   # BGMの厚さ（0＝なし 1＝キックだけ 2＝＋ベース 3＝全部）


# ---------------- 場面 ----------------
class Hook(Scene):
    """表紙（最初の0.5秒は止め絵＝サムネ）→ 金額のスロットが回って、けたが1つずつ止まる"""

    def __init__(self, c):
        self.c, self.dur = c, 3.2
        P = c.P
        pct = c.rows[0][0]
        s = f"{c.sg}¥{c.diff(0):,}"
        size = next((z for z in (190, 170, 150, 130, 112) if glyphs(z, c.sty).width(s) <= 880), 100)
        self.G = G = glyphs(size, c.sty)
        self.s = s
        self.reel = Reel([G.one(str(k)) for k in range(10)], G.u["0"].width, int(G.h * 0.80))
        self.q = ftext("？", int(size * 0.9), "white")
        self.pw, self.ph = min(1010, G.width(s) + 150), int(G.h * 0.80 * 1.22) + 84
        self.panel = bezel(self.pw, self.ph, P)
        self.py = 925
        nd = sum(ch.isdigit() for ch in s)
        self.t_spin, self.t_end = 0.5, 2.4
        step = min(0.4, 1.6 / max(1, nd - 1))
        self.locks = [self.t_end - (nd - 1 - i) * step for i in range(nd)]
        self.l_game = ftext(c.gname, 160, c.sty, maxw=980)
        self.l_t1 = ftext(f"{c.sj}のBOX相場", 92, "white", font="zen")
        self.l_t2 = ftext(f"{c.word}ランキング", 112, c.sty2, skew=0.12, maxw=1000)
        self.l_top = pill(f"TOP{c.n}", 54, P["accent"])
        self.l_q = ftext(f"第1位は{c.per}…", 68, "white", font="zen")
        self.l_pp = pill(f"{c.word}率 第1位", 46, (0, 0, 0), edge=P["ray"])
        self.l_pct = glyphs(170, c.sty, 0.14).layer(f"{c.sg}{abs(pct):.1f}%")
        self.l_who = ftext("どのBOX？", 118, "white")
        self.l_last = ftext("1位は最後に発表", 100, c.sty, maxw=1000)
        self.burst = Burst(90, VW / 2, self.py, P["conf"], seed=1, kind="spark", speed=(600, 2200), grav=900, life=0.9)
        self.events = ([(0.0, "slam"), (self.t_spin, f"spin:{self.t_end - self.t_spin:.2f}"), (self.t_spin, "riser:1.9")]
                       + [(L, "lock") for L in self.locks[:-1]] + [(self.t_end, "kyuin"), (self.t_end, "slam")])

    def frame(self, t):
        c, P = self.c, self.c.P
        im = c.bg.frame(self.t0 + t, lv=0.85, cy=0.48)
        d = ImageDraw.Draw(im)
        embers(d, self.t0 + t, 36, c.up, c.em)
        if t >= self.t_end and t < self.t_end + 0.22:
            focus_lines(d, VW / 2, self.py, int(t * FPS), col=P["line"])
        put(im, self.l_game, VW / 2, 300)
        put(im, self.l_t1, VW / 2, 455)
        put(im, self.l_t2, VW / 2, 590)
        put(im, self.l_top, VW - 150, 700)
        put(im, self.l_q, VW / 2 - 90, 705)
        # スロット
        jolt = sum(7 * decay(t, L, 0.05) * (1 if t >= L else 0) for L in self.locks)
        py = self.py + jolt
        put(im, self.panel, VW / 2, py)
        x0, y0 = VW / 2 - self.pw / 2, py - self.ph / 2
        bulbs(d, x0 + 18, y0 + 18, x0 + self.pw - 18, y0 + self.ph - 18, t, P)
        G = self.G
        wh = self.ph - 84
        x = VW / 2 - G.width(self.s) / 2
        k = 0
        for ch in self.s:
            if ch.isdigit():
                if t < self.t_spin:
                    put(im, self.q, x + G.u["0"].width / 2, py)
                else:
                    pos, fast = reel_pos(t, self.locks[k], int(ch))
                    cr = self.reel.crop(pos, wh, fast)
                    im.paste(cr, (int(x), int(py - wh / 2)), cr)
                k += 1
            else:
                g1 = G.one(ch)
                im.paste(g1, (int(x), int(py - G.h / 2)), g1)
            x += G.adv[ch]
        sh = shade(self.pw - 76, int(wh))
        im.paste(sh, (int(VW / 2 - sh.width / 2), int(py - wh / 2)), sh)
        d = ImageDraw.Draw(im)
        ring(d, VW / 2, self.py, t - self.t_end, P["line"])
        self.burst.draw(d, t - self.t_end)
        put(im, self.l_pp, VW / 2, 1170)
        put(im, self.l_pct, VW / 2, 1310, scale=1 + 0.04 * math.sin(max(0, t - 0.5) * 2 * math.pi / BEAT))
        if t < self.t_end:
            put(im, self.l_who, VW / 2, 1480)
        else:
            put(im, self.l_last, VW / 2, 1480, scale=slam(t, self.t_end))
        c.finish(im)
        return post(im, t, hits=[(self.t_end, 26)], flashes=[(self.t_end, 0.55)], zooms=[(self.t_end, 0.07)])


class RankPage(Scene):
    """1つの順位。r＝0 が1位（長く・いちばん派手に）"""

    def __init__(self, c, r):
        self.c, self.r = c, r
        P = c.P
        self.top = r == 0
        self.lv = lv = c.lv(r)
        pct, name, price, base, key, _ = c.rows[r]
        self.pct, self.price, self.base = pct, price, base
        if self.top:
            self.dur = 5.2
            self.T = dict(rank=0.0, card=0.5, name=0.9, cnt0=1.2, cnt1=2.4, pct=2.4, diff=3.0)
            self.bgm = 3
        else:
            self.dur = 2.4
            self.T = dict(rank=0.0, card=0.15, name=0.4, cnt0=0.5, cnt1=1.4, pct=1.4, diff=1.7)
            self.bgm = 3 if lv >= 0.5 else 2
        T = self.T
        self.cx = 590
        self.chips = c.chips(r)
        self.l_rank = ftext(f"第{r + 1}位", 205 if self.top else int(150 + 40 * lv), c.sty if r < 3 else "white", skew=0.1,
                            glow=P["ray"] if self.top else None)
        self.l_stamp = None
        if self.top:   # 「確定」のはんこ（順位が決まった、の合図）
            st, d = layer(250, 160)
            d.rounded_rectangle((6, 6, 243, 153), 24, fill=(255, 255, 255, 255), outline=(214, 16, 40, 255), width=12)
            d.text((125, 78), "確定", font=FD(86), fill=(214, 16, 40, 255), anchor="mm")
            self.l_stamp = st.rotate(-13, expand=True, resample=Image.BICUBIC)
        self.front, self.backc = c.card(r), c.card_back()
        self.halo = halo(820, P["ray"], 0.5 + 0.4 * lv)
        self.l_name = ftext(V.fit(_TMP, name, FB(66), 1500), 66, "white", font="zen", maxw=980)
        self.l_old = ftext(f"{c.prev} ¥{base:,}", 44, "dim", font="zen")
        self.Gp = glyphs(116, "white")
        self.Gq = glyphs(int(168 + 52 * lv) if not self.top else 236, c.sty, 0.14)
        self.s_pct = f"{c.sg}{abs(pct):.1f}%"
        self.l_pct = self.Gq.layer(self.s_pct)
        if self.l_pct.width > 1010:
            self.l_pct = self.l_pct.resize((1010, int(self.l_pct.height * 1010 / self.l_pct.width)), Image.LANCZOS)
        if self.top:
            self.l_pct = glow_under(self.l_pct, P["ray"], 22, 0.8)
        self.l_diff = pill(f"{c.per} {c.sg}¥{c.diff(r):,}", 52, P["accent"])
        self.l_gl = ftext(f"{c.word}率", 32, "white", font="zen")
        self.frac = abs(pct) / c.mx
        self.marks = [abs(c.rows[k][0]) / c.mx for k in range(r + 1, c.n)]
        # 飛びちるもの
        seed = 10 + r
        n = int(40 + 140 * lv)
        if c.up:
            self.b1 = Burst(n, VW / 2, 1385, P["conf"], seed=seed, kind="conf" if lv > 0.4 else "spark")
            self.rain = Rain(170, P["conf"], seed=seed) if self.top else None
            self.bolts = [jag(VW * q, -20, VW * q + dx, 1250, seed + k, n=11, amp=0.5) for k, (q, dx) in enumerate([(0.14, 90), (0.88, -110)])] if self.top else []
        else:
            self.b1 = Burst(n, VW / 2, 1385, P["conf"], seed=seed, kind="shard" if lv > 0.4 else "spark", up_bias=0.1, grav=2400)
            self.rain = None
            rnd = random.Random(seed)
            self.bolts = [jag(VW / 2 + rnd.uniform(-60, 60), 1385, VW / 2 + math.cos(a) * 1500, 1385 + math.sin(a) * 1500, seed + k, n=10, amp=0.35)
                          for k, a in enumerate([rnd.uniform(0, 6.28) for _ in range(13)])] if self.top else []
        # 音
        nt = 22 if self.top else 12
        ev = [(T["rank"], "slam"), (T["card"], "whoosh")]
        ev += [(T["cnt0"] + (T["cnt1"] - T["cnt0"]) * (k / nt) ** 0.8, f"cnt:{k if c.up else nt - k}") for k in range(nt)]
        if self.top:
            ev += [(0.0, "fanfare" if c.up else "doom"), (0.0, "crash"), (T["cnt0"], "riser:1.2"),
                   (T["pct"], "slam"), (T["pct"], "kyuin" if c.up else "glass"), (T["pct"], "crash" if c.up else "boom"), (T["diff"], "ding")]
        else:
            ev += [(T["pct"], "slam" if lv > 0.4 else "hit"), (T["pct"], "ding" if c.up else "drop"), (T["diff"], "pop")]
        self.events = ev

    def frame(self, t):
        c, P, T, lv = self.c, self.c.P, self.T, self.lv
        top = self.top
        tg = self.t0 + t
        im = c.bg.frame(tg, lv=0.25 + 0.75 * lv, cy=0.40, rainbow=top and c.up)
        d = ImageDraw.Draw(im)
        embers(d, tg, int(14 + 40 * lv), c.up, c.em, seed=self.r)
        if t < 0.2 + 0.1 * lv:
            focus_lines(d, VW / 2, 430, int(tg * FPS), n=int(20 + 40 * lv), inner=380, col=P["line"])
        if T["pct"] <= t < T["pct"] + 0.2 + 0.1 * lv:
            focus_lines(d, VW / 2, 1385, int(tg * FPS), n=int(20 + 40 * lv), inner=420, col=P["line"])
        if top:
            ring(d, VW / 2, 430, t - T["rank"], P["line"])
            ring(d, VW / 2, 430, t - T["rank"] - 0.12, P["ray"], speed=1100)
        put(im, c.head, VW / 2, 222)
        if not top:
            put(im, self.chips, VW / 2, 306)
        # 順位ドン
        put(im, self.l_rank, VW / 2, 425 if top else 440, scale=slam(t, T["rank"], big=2.0 + 0.6 * lv))
        if self.l_stamp:
            put(im, self.l_stamp, VW - 150, 318, scale=slam(t, 0.4, dur=0.16, big=2.6))
        # メーター（1位を100としたときの上昇率・下落率）
        self.gauge(im, t)
        # カード：裏から表へめくれる
        p = prog(t, T["card"], T["card"] + (0.5 if top else 0.3))
        if p > 0:
            cy = 745 + 8 * math.sin(tg * 2.4)
            put(im, self.halo, self.cx, 745, alpha=1.0 if p > 0.66 else p * 1.5)
            turns = 1.5 if top else 0.5        # 1位は1回転半
            a = math.pi * turns * eo(p)
            face = self.front if math.cos(a) < 0 else self.backc
            if p >= 1:
                im.paste(self.front, (int(self.cx - 215), int(cy - 215)), self.front)
            else:
                put(im, face, self.cx, cy, scale=0.55 + 0.45 * back(p), sx=max(0.03, abs(math.cos(a))))
        put(im, self.l_name, VW / 2, 1018, alpha=prog(t, T["name"], T["name"] + 0.15), scale=1.0)
        put(im, self.l_old, VW / 2, 1092, alpha=prog(t, T["name"] + 0.05, T["name"] + 0.2))
        # 値段が数えあがる（先週の値 → 今の値）
        if t >= T["cnt0"]:
            q = eo(prog(t, T["cnt0"], T["cnt1"]))
            val = round(self.base + (self.price - self.base) * q)
            lp = self.Gp.layer(f"¥{val:,}")
            put(im, lp, VW / 2, 1190, scale=1 + 0.10 * decay(t, T["cnt1"], 0.08) * (t >= T["cnt1"]))
        d = ImageDraw.Draw(im)
        # ％ドン
        tp = t - T["pct"]
        if tp >= 0:
            if top:
                for k, pts in enumerate(self.bolts):
                    if c.up and tp < 0.28:
                        draw_jag(d, pts, tp / 0.08, P["ray"], (255, 255, 255), w=5)
                    elif not c.up:
                        draw_jag(d, pts, tp / 0.16, (70, 150, 230), (235, 250, 255), w=3)
            ring(d, VW / 2, 1385, tp, P["line"], speed=1300 + 600 * lv)
            if c.up:
                put(im, self.l_pct, VW / 2, 1385, scale=slam(t, T["pct"], big=2.2 + 0.8 * lv))
            else:   # 下落：上から落ちてきてドスン
                fall = eo(prog(tp, 0, 0.16))
                put(im, self.l_pct, VW / 2, 1385 - 700 * (1 - fall) ** 2 + 30 * decay(t, T["pct"] + 0.16, 0.06) * (tp > 0.16), scale=1.0)
            d = ImageDraw.Draw(im)
            self.b1.draw(d, tp - (0 if c.up else 0.16))
            if self.rain:
                self.rain.draw(d, tp)
        put(im, self.l_diff, VW / 2, 1522, scale=slam(t, T["diff"], dur=0.18, big=1.8))
        c.finish(im)
        hit_t = T["pct"] + (0 if c.up else 0.16)
        return post(im, t, hits=[(T["rank"], 10 + 22 * lv), (hit_t, 12 + 30 * lv)],
                    flashes=([(0.0, 0.5)] if top else []) + [(hit_t, 0.22 + 0.33 * lv)],
                    zooms=[(hit_t, 0.03 + 0.06 * lv)] + ([(0.0, 0.08)] if top else []))

    def gauge(self, im, t):
        c, P, T = self.c, self.c.P, self.T
        x, y0, y1 = 112, 560, 960
        H = y1 - y0
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((x - 38, y0 - 10, x + 38, y1 + 10), 18, fill=(6, 6, 12), outline=P["ray"], width=5)
        f = self.frac * eo(prog(t, T["cnt0"], T["cnt1"]))
        h = int(H * f)
        if h > 0:
            if c.up:
                im.paste(c.gbar.crop((0, H - h, 56, H)), (x - 28, y1 - h))
            else:
                im.paste(c.gbar.crop((0, H - h, 56, H)).transpose(Image.FLIP_TOP_BOTTOM), (x - 28, y0))
        Y = (lambda q: y1 - H * q) if c.up else (lambda q: y0 + H * q)
        for k, m in enumerate(self.marks):
            d.line((x - 46, Y(m), x + 46, Y(m)), fill=(255, 255, 255), width=3)
        yt = Y(1.0)
        lab = "1位" if not self.top else f"{abs(self.pct):.1f}%"
        d.text((x, yt + (-34 if c.up else 40)), lab, font=FD(34), fill=P["ray"], anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
        put(im, self.l_gl, x, (y1 + 44) if c.up else (y0 - 44))


class Tease(Scene):
    """1位の前の「ため」：3つのリールが1つずつ止まる。3つめはゆっくり"""
    bgm = 0

    def __init__(self, c):
        self.c, self.dur = c, 3.6
        P = c.P
        word = "激アツ" if c.up else "急降下"
        self.locks = [0.8, 1.6, 3.0]
        cw, ch = 280, 330
        self.cw, self.ch = cw, ch
        deco = [ftext(s, 200, "dim") for s in ("★", "？", "◆")]
        self.reels = []
        for k, w in enumerate(word):
            cells = [deco[k % 3], deco[(k + 1) % 3], ftext(w, 230, c.sty), deco[(k + 2) % 3]]
            self.reels.append(Reel(cells, cw, ch))
        self.pw, self.ph = 3 * cw + 2 * 14 + 96, int(ch * 1.18) + 84
        self.panel = bezel(self.pw, self.ph, P)
        self.py = 900
        self.l_1 = ftext("第1位は…", 150, "white", skew=0.08)
        self.l_b = pill(f"{c.gname} {c.sj}の{c.word}率 No.1", 46, P["accent"])
        self.l_2 = ftext(f"2位は {c.sg}{abs(c.rows[1][0]):.1f}%", 76, "dim", font="zen") if c.n > 1 else None
        self.l_3 = ftext("1位は ？？？", 104, c.sty)
        self.l_go = ftext("第1位 発表！", 150, c.sty2, skew=0.1, maxw=1000)
        self.glow = halo(900, P["ray"], 0.9)
        self.burst = Burst(110, VW / 2, self.py, P["conf"], seed=5, kind="spark", speed=(700, 2400), grav=800, life=0.6)
        self.events = ([(0.0, "boom"), (0.0, "roll:3.0"), (0.0, "spin:3.0"), (0.8, "lock"), (1.6, "lock"), (1.6, "riser:1.4")]
                       + [(1.6 + k * BEAT, "heart") for k in range(4)] + [(3.0, "kyuin" if c.up else "doom"), (3.0, "slam"), (3.0, "crash")])

    def frame(self, t):
        c, P = self.c, self.c.P
        tg = self.t0 + t
        done = t >= 3.0
        im = c.bg.frame(tg, lv=1.0 if done else 0.12 + 0.2 * prog(t, 1.6, 3.0), cy=0.47, dim=1.0 if done else 0.75)
        d = ImageDraw.Draw(im)
        if done and t < 3.25:
            focus_lines(d, VW / 2, self.py, int(tg * FPS), n=60, col=P["line"])
        put(im, self.l_1, VW / 2, 380, scale=slam(t, 0.0))
        put(im, self.l_b, VW / 2, 540, alpha=prog(t, 0.2, 0.4))
        # 3つめを待つあいだ、だんだん寄っていく
        py = self.py
        if done:
            put(im, self.glow, VW / 2, py, alpha=0.6 + 0.4 * math.sin((t - 3.0) * 2 * math.pi / BEAT) ** 2)
        put(im, self.panel, VW / 2, py)
        x0, y0 = VW / 2 - self.pw / 2, py - self.ph / 2
        bulbs(d, x0 + 18, y0 + 18, x0 + self.pw - 18, y0 + self.ph - 18, t * (2.2 if done else 1), P)
        wh = self.ph - 84
        for k, R in enumerate(self.reels):
            x = VW / 2 + (k - 1) * (self.cw + 14) - self.cw / 2
            pos, fast = reel_pos(t, self.locks[k], 2, v=9.0, d=1.2 if k == 2 else 0.28)
            d.rounded_rectangle((x, py - wh / 2, x + self.cw, py + wh / 2), 16, fill=(18, 14, 30) if t < self.locks[k] else tuple(int(v * 0.42) for v in P["core1"]))
            cr = R.crop(pos, wh, fast)
            j = 9 * decay(t, self.locks[k], 0.05) * (t >= self.locks[k])
            im.paste(cr, (int(x), int(py - wh / 2 + j)), cr)
            sh = shade(self.cw, int(wh))
            im.paste(sh, (int(x), int(py - wh / 2)), sh)
        d = ImageDraw.Draw(im)
        if not done and t >= 1.6:   # 止まっていない3つめの枠が拍ごとに光る
            x = VW / 2 + (self.cw + 14) - self.cw / 2
            a = decay(t, 1.6 + int((t - 1.6) / BEAT) * BEAT, 0.14)
            wd = int(4 + 10 * a)
            d.rounded_rectangle((x - wd, py - wh / 2 - wd, x + self.cw + wd, py + wh / 2 + wd), 20, outline=P["line"], width=wd)
        if done:
            ring(d, VW / 2, py, t - 3.0, P["line"])
            self.burst.draw(d, t - 3.0)
            put(im, self.l_go, VW / 2, 1340, scale=slam(t, 3.0))
        else:
            if self.l_2:
                put(im, self.l_2, VW / 2, 1270, alpha=prog(t, 0.5, 0.7))
            put(im, self.l_3, VW / 2, 1400, alpha=prog(t, 0.9, 1.1), scale=1 + 0.05 * decay(t, int(t / BEAT) * BEAT, 0.12))
        c.finish(im)
        return post(im, t, hits=[(0.8, 8), (1.6, 10), (3.0, 34)], flashes=[(3.0, 0.5)], zooms=[(3.0, 0.08)])


class Summary(Scene):
    """まとめ（保存用）：1位から順にバンバン並ぶ"""
    bgm = 3

    def __init__(self, c):
        self.c, self.dur = c, 3.6
        P = c.P
        self.l_title = ftext(f"{c.sj}の{c.word}TOP{c.n}", 100, c.sty, maxw=900)
        self.l_game = pill(f"まとめ｜{c.gname} BOX相場", 40, P["accent"])
        self.rows = []
        G = glyphs(74, c.sty, 0.1)
        W, H = 1000, 196
        for r, (pct, name, price, base, key, _) in enumerate(c.rows):
            im, d = layer(W, H)
            d.rounded_rectangle((0, 0, W - 1, H - 1), 26, fill=(10, 10, 18, 238), outline=(P["ray"] if r == 0 else P["accent"]) + (255,), width=6 if r == 0 else 4)
            medal = X.MEDAL[r] if r < 3 else (92, 96, 120)
            d.ellipse((18, 54, 106, 142), fill=medal + (255,), outline=(255, 255, 255, 255), width=4)
            d.text((62, 96), str(r + 1), font=FD(52), fill=(255, 255, 255, 255), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, 255))
            x = 126
            ph = c.photo(key, 150)
            if ph:
                m = Image.new("L", (150, 150), 0)
                ImageDraw.Draw(m).rounded_rectangle((0, 0, 149, 149), 16, fill=255)
                im.paste(ph, (x, 23), m)
                x += 168
            d.text((x, 22), V.fit(d, name, FB(46), W - x - 30), font=FB(46), fill=(255, 255, 255, 255))
            d.text((x, 92), f"¥{price:,}", font=FD(40), fill=(232, 236, 246, 255))
            d.text((x + d.textlength(f"¥{price:,}", font=FD(40)) + 16, 106), f"（{c.prev} ¥{base:,}）", font=FB(28, "Bold"), fill=(160, 166, 190, 255))
            gp = G.layer(f"{c.sg}{abs(pct):.1f}%")
            im.alpha_composite(gp, (W - gp.width - 8, H - gp.height - 4))
            self.rows.append((im, x, abs(pct) / c.mx))
        self.step = 0.2
        self.l_save = ftext("保存して相場チェック！", 78, "white", font="zen", maxw=980)
        self.events = [(0.1 + r * self.step, "hit") for r in range(c.n)] + [(0.1 + c.n * self.step + 0.3, "sparkle"), (2.0, "ding")]

    def frame(self, t):
        c, P = self.c, self.c.P
        tg = self.t0 + t
        im = c.bg.frame(tg, lv=0.45, cy=0.5, dim=0.8)
        d = ImageDraw.Draw(im)
        embers(d, tg, 26, c.up, c.em)
        put(im, self.l_game, VW / 2, 222)
        put(im, self.l_title, VW / 2, 330, scale=slam(t, 0.0))
        y0 = 425
        gap = min(212, (1440 - y0) // max(1, c.n))
        for r, (row, bx, frac) in enumerate(self.rows):
            st = 0.1 + r * self.step
            p = eo(prog(t, st, st + 0.22))
            if p <= 0:
                continue
            side = -1 if r % 2 == 0 else 1
            x = 40 + side * int((1 - p) * VW)
            y = y0 + r * gap
            im.paste(row, (x, y), row)
            b = eo(prog(t, st + 0.2, st + 0.9))
            if b > 0:
                d.rounded_rectangle((x + bx, y + 152, x + bx + max(10, (560 - bx) * frac * b), y + 176), 8, fill=P["ray"] if r == 0 else P["accent"])
        put(im, self.l_save, VW / 2, y0 + c.n * gap + 50, scale=slam(t, 2.0) * (1 + 0.04 * math.sin(max(0, t - 2.2) * 2 * math.pi / (BEAT * 2))))
        c.finish(im)
        return post(im, t, hits=[(0.1 + r * self.step + 0.2, 6) for r in range(c.n)])


class Outro(Scene):
    bgm = 2

    def __init__(self, c):
        self.c, self.dur = c, 2.4
        P = c.P
        self.ls = [(ftext("BOXの相場グラフ・", 76, "white", font="zen"), 600, 0.0),
                   (ftext("抽選の締切は", 76, "white", font="zen"), 700, 0.08)]
        self.l_site = ftext("トレカ抽選ナビ", 132, c.sty, maxw=1000, glow=P["ray"])
        self.l_url = ftext("tcg-chusen.com", 72, "white")
        self.l_band = pill("プロフィールのリンクから", 58, P["accent"])
        self.l_note = ftext("※値上がり・値下がりを約束するものではありません", 34, "dim", font="zen", maxw=1000)
        self.events = [(0.0, "hit"), (0.4, "slam"), (0.4, "sparkle"), (1.2, "pop")]

    def frame(self, t):
        c = self.c
        tg = self.t0 + t
        im = c.bg.frame(tg, lv=0.7, cy=0.46)
        d = ImageDraw.Draw(im)
        embers(d, tg, 36, c.up, c.em)
        for l, y, st in self.ls:
            put(im, l, VW / 2, y, alpha=prog(t, st, st + 0.15))
        put(im, self.l_site, VW / 2, 900, scale=slam(t, 0.4))
        put(im, self.l_url, VW / 2, 1070, alpha=prog(t, 0.7, 0.9))
        put(im, self.l_band, VW / 2, 1250, scale=slam(t, 1.2, dur=0.18, big=1.7) * (1 + 0.04 * math.sin(max(0, t - 1.4) * 2 * math.pi / BEAT)))
        put(im, self.l_note, VW / 2, 1420, alpha=prog(t, 0.9, 1.1))
        c.finish(im)
        return post(im, t, hits=[(0.4, 14)])


# ---------------- 音（全部ここで作る・著作権なし） ----------------
def _tone(f0, f1, dur, harm=(1.0, 0.4, 0.25), r=0.3, a=0.004):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = f0 + (f1 - f0) * (tt / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return sum(h * np.sin(ph * (k + 1)) for k, h in enumerate(harm)) * V._env(n, a, r)


def _at(out, x, t):
    i = int(t * SR)
    if i < len(out):
        out[i:i + len(x)] += x[:len(out) - i]


@lru_cache(maxsize=128)
def sfx(name):
    base, _, arg = name.partition(":")
    a = float(arg) if arg else 0.0
    if base == "slam":      # ドン！
        return V._sum(0.95 * V._sine(135, 36, 0.55, 0.2), 0.5 * V._lp(V._noise(0.25, 0.08, hp=False, seed=11), 8), 0.28 * V._noise(0.05, 0.012, seed=12))
    if base == "lock":      # リールが止まる カチャン
        return V._sum(0.5 * V._sine(240, 90, 0.12, 0.04), 0.2 * V._sine(1850, 1850, 0.2, 0.05), 0.14 * V._sine(2770, 2770, 0.2, 0.04), 0.3 * V._noise(0.03, 0.008, seed=13))
    if base == "spin":      # リールが回る カタカタ
        out = np.zeros(int(a * SR))
        tk = V._sum(0.07 * V._noise(0.012, 0.004, seed=14), 0.05 * V._sine(3000, 2600, 0.012, 0.004))
        for k in range(int(a * 24)):
            _at(out, tk, k / 24)
        return out
    if base == "cnt":       # 数えあがりのピッ（だんだん高く／下落は低く）
        f = 1050 * 2 ** (a / 18)
        return 0.15 * V._sine(f, f, 0.05, 0.016)
    if base == "kyuin":     # キュイン
        out = np.zeros(int(1.3 * SR))
        for k in range(3):
            n = int(0.15 * SR)
            _at(out, 0.2 * _tone(650, 3300, 0.15, r=9) * np.sin(np.pi * np.arange(n) / n), k * 0.14)
        n = int(0.85 * SR)
        tt = np.arange(n) / SR
        tail = np.sin(2 * np.pi * 3300 * tt + 3 * np.sin(2 * np.pi * 15 * tt)) * (0.6 + 0.4 * np.sin(2 * np.pi * 22 * tt)) * np.exp(-tt / 0.28)
        _at(out, 0.16 * tail, 0.42)
        return out
    if base == "fanfare":   # ジャジャジャーン（Cメジャー）
        out = np.zeros(int(2.0 * SR))
        saw = tuple(1 / k for k in range(1, 7))
        for t0, dur, r in ((0.0, 0.14, 0.08), (0.2, 0.14, 0.08), (0.4, 1.5, 0.55)):
            for f in (261.63, 523.25, 659.25, 783.99, 1046.5):
                _at(out, 0.055 * _tone(f, f, dur, harm=saw, r=r), t0)
        return V._lp(out, 3)
    if base == "doom":      # ヒューーン…ドーン（落ちる音）
        return V._sum(0.3 * _tone(900, 70, 0.6, r=0.6, a=0.02), np.concatenate([np.zeros(int(0.5 * SR)), 0.9 * V._sine(80, 30, 1.0, 0.4)]))
    if base == "drop":      # 下落のピュー
        return 0.22 * _tone(1200, 300, 0.25, r=0.12)
    if base == "glass":     # ガシャーン
        out = np.zeros(int(1.1 * SR))
        _at(out, 0.5 * V._noise(0.5, 0.12, seed=15), 0)
        r = np.random.default_rng(16)
        for _ in range(34):
            f = r.uniform(2200, 7500)
            _at(out, 0.07 * V._sine(f, f * 0.98, 0.25, r.uniform(0.02, 0.09)), r.uniform(0, 0.5))
        return out
    if base == "roll":      # ドラムロール（だんだん速く・大きく）
        out = np.zeros(int(a * SR))
        t, gap, k = 0.0, 0.10, 0
        while t < a - 0.05:
            _at(out, V._noise(0.06, 0.03, seed=20 + k % 7) * (0.10 + 0.45 * (t / a) ** 1.5), t)
            t += gap
            gap = max(0.033, gap * 0.965)
            k += 1
        return out
    if base == "riser":     # シュワー（だんだん上がる）
        n = int(a * SR)
        x = V._lp(np.random.default_rng(5).uniform(-1, 1, n), 3)
        tt = np.arange(n) / SR
        sw = np.sin(2 * np.pi * np.cumsum(300 + 1500 * (tt / a) ** 2) / SR)
        return (0.2 * x + 0.07 * sw) * np.linspace(0, 1, n) ** 2
    if base == "heart":     # ドクン
        return V._sum(0.9 * V._sine(72, 40, 0.2, 0.07), np.concatenate([np.zeros(int(0.15 * SR)), 0.6 * V._sine(66, 38, 0.2, 0.07)]))
    if base == "sparkle":   # キラキラ
        out = np.zeros(int(0.9 * SR))
        for k, f in enumerate((1568, 1760, 2093, 2349, 2637, 3136, 3520, 4186)):
            _at(out, 0.09 * V._sine(f, f, 0.3, 0.09), k * 0.05)
        return out
    return V.sfx(name)


def bgm(total, levels):
    """150BPMのBGM。levels＝[(はじまり, おわり, 厚さ 0〜3)]。Am→F→C→G"""
    n = int(total * SR)
    out = np.zeros(n + SR)
    kick = 0.6 * V._sine(125, 40, 0.26, 0.11)
    hat = 0.09 * V._noise(0.04, 0.012, seed=7)
    clap = 0.26 * V._lp(V._noise(0.12, 0.05, seed=8), 2)
    roots = [55.0, 43.65, 65.41, 49.0]
    chords = [(440, 523.25, 659.25, 880), (349.23, 440, 523.25, 698.46), (523.25, 659.25, 783.99, 1046.5), (392, 493.88, 587.33, 783.99)]
    arp = [0, 1, 2, 3, 2, 1, 2, 3]

    @lru_cache(maxsize=None)
    def bass(f):
        return V._lp(0.2 * _tone(f, f, BEAT * 0.48, harm=tuple(1 / k for k in range(1, 9)), r=0.16), 22)

    @lru_cache(maxsize=None)
    def pluck(f):
        return V._lp(0.07 * np.sign(V._sine(f, f, 0.09, 0.035)), 6)

    b = 0
    while b * BEAT < total:
        t = b * BEAT
        lv = next((l for a, e, l in levels if a - 1e-6 <= t < e - 1e-6), 0)
        bar = (b // 4) % 4
        if lv >= 1:
            _at(out, kick, t)
            _at(out, hat, t + BEAT / 2)
        if lv >= 2:
            if b % 4 in (1, 3):
                _at(out, clap, t)
            _at(out, bass(roots[bar] * 2), t + BEAT / 2)
            _at(out, bass(roots[bar] * 2) * 0.6, t + BEAT * 0.75)
        if lv >= 3:
            for q in range(4):
                _at(out, pluck(chords[bar][arp[(b * 4 + q) % 8]]), t + q * BEAT / 4)
                if q % 2:
                    _at(out, hat * 0.7, t + q * BEAT / 4)
        b += 1
    return out[:n]


def mix(events, total, levels, music=True):
    n = int(total * SR)
    out = np.zeros(n + 3 * SR)
    if music:
        m = bgm(total, levels)
        out[:len(m)] += m * 0.62
    for t, nm in events:
        _at(out, sfx(nm), t)
    out = np.tanh(out[:n] * 1.15) * 0.9
    f = int(0.02 * SR)
    out[:f] *= np.linspace(0, 1, f)
    e = int(0.5 * SR)
    out[-e:] *= np.linspace(1, 0, e)
    return out


# ---------------- 書き出し ----------------
def scenes(c):
    sc = [Hook(c)] + [RankPage(c, r) for r in range(c.n - 1, 0, -1)]
    sc += ([Tease(c)] if c.n > 1 else []) + [RankPage(c, 0), Summary(c), Outro(c)]
    t0 = 0.0
    for s in sc:
        s.t0 = t0
        t0 += s.dur
    return sc


def render(sc, mp4, music=True):
    """場面を順に描いて mp4 に（切りかえはパッと変える。各場面の頭の「ドン」がつなぎになる）"""
    mp4 = Path(mp4)
    total = sum(s.dur for s in sc)
    events = [(s.t0 + t, nm) for s in sc for t, nm in s.events]
    levels = [(s.t0, s.t0 + s.dur, s.bgm) for s in sc]
    wav = mp4.with_suffix(".wav")
    V.write_wav(wav, mix(events, total, levels, music))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}",
                           "-r", str(FPS), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a",
                           "-c:v", "libx264", "-preset", "superfast", "-crf", "23", "-maxrate", "2200k", "-bufsize", "4400k", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    for s in sc:
        for f in range(int(round(s.dur * FPS))):
            ff.stdin.write(s.frame(f / FPS).tobytes())
    ff.stdin.close()
    ok = ff.wait() == 0
    wav.unlink(missing_ok=True)
    if not ok:
        raise RuntimeError("ffmpeg が失敗")
    return mp4


def make_hype(out_dir, kind, span, game, rows, today=None, music=True):
    """ハイテンション版の動画を1本つくってパスを返す。ランキングが空なら None"""
    today = today or now().date()
    if not rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    c = Ctx(kind, span, game, rows, B._rk(), today)
    mp4 = out_dir / f"box_{game}_{'joushou' if kind == 'up' else 'geraku'}_{'konshu' if span == 'week' else 'kyou'}_hype_{today:%m%d}.mp4"
    return render(scenes(c), mp4, music=music)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "video"
    span = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("week", "day") else "week"
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), [])
    today = now().date()
    rk_all = B.rankings(span, today)
    for game in B.GN:
        for kind in ("up", "down"):
            if only and f"{game}-{kind}" not in only:
                continue
            rows = rk_all[kind].get(game) or []
            print(game, kind, make_hype(out, kind, span, game, rows, today), [(round(x[0], 1), x[1]) for x in rows])
