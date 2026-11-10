"""縦長のショート動画（1080×1920・30コマ/秒）をつくる道具（ランキング動画などのテンプレ）

・見た目（THEMES）：light＝サイトと同じ白×赤 / dark＝株アプリ風の黒（光る線・電光掲示板）/ game＝ゲームの色（ポケカ黄×赤・ワンピ紺×金）
・場面（scene）は dur（秒）・frame(t)（t秒目の絵）・events（[(秒, 音の名前)]）を持つ
・render() が場面を順に描いて ffmpeg に流しこみ、横スライドで切りかえ、効果音＋BGM（自作の音・著作権なし）を重ねる
"""
import io
import math
import random
import struct
import subprocess
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import ximage as X

VW, VH, FPS, SR = 1080, 1920, 30, 44100


# ---------------- 見た目 ----------------
@dataclass
class Theme:
    name: str
    paper: tuple        # 背景
    pink: tuple         # 背景の上の文字
    pink2: tuple        # 背景の上の小さい文字
    card: tuple         # カード・チャートの地
    cink: tuple         # カードの上の文字
    cink2: tuple
    rule: tuple         # 線
    head: tuple         # ヘッダー・フッターの地
    headink: tuple
    headink2: tuple
    up: tuple           # 上がった色
    down: tuple         # 下がった色
    accent: tuple       # 「トレカ抽選ナビ」の色
    glow: bool = False  # 線を光らせる
    ticker: bool = True
    tickbg: tuple = (22, 28, 46)
    bgfx: str = ""      # 背景の飾り（grid / dots / ""）


def theme(name, game="pokemon"):
    if name == "dark":
        return Theme("dark", paper=(9, 12, 20), pink=(238, 240, 247), pink2=(150, 158, 182), card=(18, 23, 36),
                     cink=(238, 240, 247), cink2=(140, 150, 175), rule=(38, 45, 64), head=(14, 18, 30),
                     headink=(238, 240, 247), headink2=(140, 150, 175), up=(255, 62, 86), down=(0, 214, 143),
                     accent=(255, 62, 86), glow=True, tickbg=(0, 0, 0), bgfx="grid")
    if name == "game" and game == "onepiece":
        return Theme("game", paper=(13, 30, 66), pink=(255, 255, 255), pink2=(196, 208, 235), card=(255, 255, 255),
                     cink=(13, 30, 66), cink2=(84, 98, 130), rule=(215, 220, 232), head=(196, 18, 48),
                     headink=(255, 255, 255), headink2=(255, 220, 225), up=(214, 22, 50), down=(0, 140, 105),
                     accent=(255, 196, 37), tickbg=(6, 16, 38), bgfx="dots")
    if name == "game":
        return Theme("game", paper=(255, 204, 0), pink=(26, 32, 60), pink2=(92, 76, 20), card=(255, 255, 255),
                     cink=(26, 32, 60), cink2=(95, 100, 120), rule=(232, 186, 0), head=(42, 92, 170),
                     headink=(255, 255, 255), headink2=(214, 228, 255), up=(214, 22, 50), down=(0, 130, 95),
                     accent=(214, 22, 50), tickbg=(26, 32, 60), bgfx="dots")
    return Theme("light", paper=X.PAPER, pink=X.INK, pink2=X.INK2, card=X.CARD, cink=X.INK, cink2=X.INK2, rule=X.RULE,
                 head=X.CARD, headink=X.INK, headink2=X.INK2, up=(200, 16, 46), down=(0, 128, 96), accent=X.RED)


# ---------------- 文字・動き ----------------
@lru_cache(maxsize=None)
def FB(size, w="Black"):
    return X.F(size, w)


@lru_cache(maxsize=None)
def FD(size):
    return X.DELA(size)


def eo(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def back(x):
    x = max(0.0, min(1.0, x))
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def prog(t, a, b):
    return max(0.0, min(1.0, (t - a) / (b - a))) if b > a else float(t >= a)


def layer(w, h):
    im = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def text_layer(txt, font, fill, pad=12, stroke=0, stroke_fill=None):
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), txt, font=font, stroke_width=stroke)
    im, d = layer(r - l + pad * 2, b - t + pad * 2)
    d.text((pad - l, pad - t), txt, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return im


def band_layer(txt, size, fill, ink=(255, 255, 255)):
    f = FB(size)
    tw = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(txt, font=f)
    w, h = int(tw + 64), int(size * 1.55)
    im, d = layer(w, h)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 22, fill=fill)
    d.text((w / 2, h / 2), txt, font=f, fill=ink, anchor="mm")
    return im


def put(base, lay, cx, cy, scale=1.0, alpha=1.0):
    """lay を中心 (cx, cy) に、大きさ scale・濃さ alpha で重ねる"""
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        lay = lay.resize((max(1, int(lay.width * scale)), max(1, int(lay.height * scale))), Image.BILINEAR)
    if alpha < 0.999:
        lay = lay.copy()
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = int(cx - lay.width / 2), int(cy - lay.height / 2)
    sx, sy = max(0, -x), max(0, -y)
    if sx >= lay.width or sy >= lay.height or x >= base.width or y >= base.height:
        return
    base.alpha_composite(lay.crop((sx, sy, min(lay.width, base.width - x), min(lay.height, base.height - y))), (max(0, x), max(0, y)))


def fit(d, txt, font, w):
    return X._fit(d, txt, font, w)


# ---------------- 共通の部品 ----------------
def canvas(th):
    im = Image.new("RGBA", (VW, VH), th.paper + (255,))
    d = ImageDraw.Draw(im)
    if th.bgfx == "grid":
        for y in range(0, VH, 60):
            d.line((0, y, VW, y), fill=th.rule, width=1)
        for x in range(0, VW, 60):
            d.line((x, 0, x, VH), fill=th.rule, width=1)
    elif th.bgfx == "dots":
        c = tuple(min(255, int(v * 0.9 + (255 if sum(th.paper) < 300 else 0) * 0.1)) for v in th.paper)
        for y in range(30, VH, 48):
            for x in range(24 if (y // 48) % 2 else 0, VW, 48):
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=c)
    return im, d


HEAD_H, TICK_H = 170, 54


def header(im, th, dots=None):
    """上：ロゴ。dots=(全部の数, 今の番号) なら右に進み具合の丸"""
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, VW, HEAD_H), fill=th.head)
    d.text((VW / 2, 92), "トレカ抽選ナビ", font=FD(56), fill=th.headink, anchor="mm")
    if dots:
        n, cur = dots
        for k in range(n):  # 左から 5,4,3,2,1
            rank = n - k
            cx, cy = VW - 60 - (n - 1 - k) * 40, 92
            on = rank == cur
            done = rank > cur
            d.ellipse((cx - 15, cy - 15, cx + 15, cy + 15), fill=th.accent if on else (th.headink2 if done else th.head),
                      outline=th.headink2, width=2)
            d.text((cx, cy), str(rank), font=FB(18), fill=th.head if (on or done) else th.headink2, anchor="mm")


def footer(im, th, lines):
    d = ImageDraw.Draw(im)
    d.rectangle((0, VH - 230, VW, VH), fill=th.head)
    d.text((VW / 2, VH - 150), lines[0], font=FB(44), fill=th.headink, anchor="mm")
    for k, ln in enumerate(lines[1:3]):
        d.text((VW / 2, VH - 92 + k * 40), ln, font=FB(27, "Medium"), fill=th.headink2, anchor="mm")


def ticker_strip(th, items):
    """電光掲示板の帯（横に長い絵）。items=[(文字, 色)]"""
    f = FB(30)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(sum(tmp.textlength(s, font=f) + 70 for s, _ in items)) + 10
    im, d = layer(max(w, VW), TICK_H)
    d.rectangle((0, 0, im.width, TICK_H), fill=th.tickbg + (255,))
    x = 20
    for s, c in items:
        d.text((x, TICK_H / 2), s, font=f, fill=c, anchor="lm")
        x += tmp.textlength(s, font=f) + 40
        d.text((x - 20, TICK_H / 2), "｜", font=FB(26), fill=(90, 98, 120), anchor="mm")
        x += 30
    return im


def draw_ticker(im, strip, t, y=HEAD_H, speed=170):
    if strip is None:
        return
    w = strip.width
    off = int(t * speed) % w
    im.alpha_composite(strip.crop((off, 0, min(w, off + VW), TICK_H)), (0, y))
    if off + VW > w:
        im.alpha_composite(strip.crop((0, 0, off + VW - w, TICK_H)), (w - off, y))


def line_chart(lay, box, vals, p, col, th, base=None, base_label="", ox=0, oy=0, tag_fmt="¥{:,}", tag=True, label_in=False):
    """箱 box の中に値の線（p=0〜1 で左から伸びる）。base は点線。lay は box の左上を (ox,oy) とする絵
    tag=False で線の先の値札なし。label_in=True で点線のラベルを箱の中（左上）に書く（画面の右はしを空けたいとき）"""
    d = ImageDraw.Draw(lay)
    px0, py0, px1, py1 = box
    lo, hi = min(vals + ([base] if base else [])), max(vals + ([base] if base else []))
    pad = max(1, (hi - lo) * 0.12)
    lo, hi = lo - pad, hi + pad
    Y = lambda q: py1 - (py1 - py0) * (q - lo) / (hi - lo)
    for k in range(5):  # 目盛りの横線
        yy = py0 + (py1 - py0) * k / 4
        d.line((px0 - ox, yy - oy, px1 - ox, yy - oy), fill=th.rule + (255,), width=1)
    if base:
        a = int(255 * min(1.0, p * 4))
        by = Y(base) - oy
        xx = px0 - ox
        while xx < px1 - ox:
            d.line((xx, by, min(xx + 16, px1 - ox), by), fill=th.cink2 + (a,), width=3)
            xx += 28
        if label_in:
            d.text((px0 - ox + 8, by - 8), base_label, font=FB(26, "Bold"), fill=th.cink2 + (a,), anchor="ls")
        else:
            d.text((px1 - ox + 10, by), base_label, font=FB(24, "Bold"), fill=th.cink2 + (a,), anchor="lm")
    if len(vals) < 2 or p <= 0:
        return None
    pos = p * (len(vals) - 1)
    k = int(pos)
    xy = [(px0 - ox + (px1 - px0) * j / (len(vals) - 1), Y(q) - oy) for j, q in enumerate(vals[:k + 1])]
    cur = vals[k] if k >= len(vals) - 1 else vals[k] + (vals[k + 1] - vals[k]) * (pos - k)
    xy.append((px0 - ox + (px1 - px0) * pos / (len(vals) - 1), Y(cur) - oy))
    d.polygon(xy + [(xy[-1][0], py1 - oy), (xy[0][0], py1 - oy)], fill=col + (40,))
    if th.glow:
        g, gd = layer(lay.width, lay.height)
        gd.line(xy, fill=col + (150,), width=26, joint="curve")
        lay.alpha_composite(g.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(lay)
    d.line(xy, fill=col + (255,), width=8, joint="curve")
    ex, ey = xy[-1]
    d.ellipse((ex - 14, ey - 14, ex + 14, ey + 14), fill=col + (255,), outline=th.card + (255,), width=4)
    if not tag:
        return cur
    tag = tag_fmt.format(round(cur))
    tw = d.textlength(tag, font=FB(34))
    bx = min(max(ex - tw / 2 - 16, 10), lay.width - tw - 42)
    byy = max(ey - 78, 54)
    d.rounded_rectangle((bx, byy, bx + tw + 32, byy + 52), 12, fill=th.cink + (235,))
    d.text((bx + 16, byy + 26), tag, font=FB(34), fill=th.card + (255,), anchor="lm")
    return cur


def blur(im, r=28):
    return im.filter(ImageFilter.GaussianBlur(r))


# ---------------- 音（自作・著作権なし） ----------------
def _env(n, a=0.005, r=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / r)


def _sine(f0, f1, dur, r=0.2, a=0.003):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * _env(n, a, r)


def _noise(dur, r=0.1, hp=True, seed=0):
    n = int(dur * SR)
    x = np.random.default_rng(seed).uniform(-1, 1, n)
    if hp:
        x = np.diff(x, prepend=0) * 0.6
    return x * _env(n, 0.002, r)


def _lp(x, k):
    k = max(1, int(k))
    return np.convolve(x, np.ones(k) / k, mode="same")


def _sum(*xs):
    out = np.zeros(max(len(x) for x in xs))
    for x in xs:
        out[:len(x)] += x
    return out


def sfx(name):
    if name.startswith("tick:"):  # 高さつきのカチッ（数字が数えあがるとき、だんだん高くする）。例 "tick:1.4"
        k = float(name.split(":")[1])
        return 0.16 * _sine(1500 * k, 1400 * k, 0.035, 0.012)
    if name == "heart":  # ドクン（1位の発表の前のため）
        return _sum(0.9 * _sine(95, 40, 0.3, 0.1), np.concatenate([np.zeros(int(0.13 * SR)), 0.6 * _sine(80, 38, 0.3, 0.1)]))
    if name == "shine":  # キラッ
        return _sum(*[np.concatenate([np.zeros(int(0.05 * j * SR)), 0.14 * _sine(f, f, 0.6, 0.2)]) for j, f in enumerate((1568, 2093, 2637, 3136))])
    if name == "pop":
        return 0.55 * _sine(900, 420, 0.14, 0.05)
    if name == "tick":
        return 0.12 * _sine(2200, 2000, 0.03, 0.01)
    if name == "hit":
        return _sum(0.7 * _sine(150, 45, 0.35, 0.12), 0.25 * _noise(0.2, 0.05, seed=1))
    if name == "whoosh":
        n = int(0.42 * SR)
        x = np.random.default_rng(2).uniform(-1, 1, n)
        x = _lp(x, 6)
        env = np.sin(np.pi * np.arange(n) / n) ** 2
        return 0.35 * x * env
    if name == "ding":
        return _sum(0.3 * _sine(1320, 1320, 0.5, 0.18), 0.12 * _sine(2640, 2640, 0.3, 0.1))
    if name == "drumroll":
        out = np.zeros(int(1.7 * SR))
        t, gap, k = 0.0, 0.11, 0
        while t < 1.65:
            s = _noise(0.06, 0.03, seed=10 + k) * (0.15 + 0.5 * t / 1.65)
            i = int(t * SR)
            out[i:i + len(s)] += s[:len(out) - i]
            t += gap
            gap = max(0.035, gap * 0.93)
            k += 1
        return out
    if name == "crash":
        chord = sum(_sine(f, f, 1.6, 0.6) for f in (523.25, 659.25, 783.99, 1046.5)) * 0.16
        return _sum(chord, 0.45 * _noise(1.4, 0.45, seed=3), 0.6 * _sine(140, 50, 0.4, 0.15))
    if name == "boom":
        return _sum(0.9 * _sine(90, 32, 1.0, 0.45), 0.25 * _sine(400, 120, 0.8, 0.3), 0.2 * _noise(0.5, 0.2, hp=False, seed=4))
    if name == "riser":
        n = int(1.2 * SR)
        x = _lp(np.random.default_rng(5).uniform(-1, 1, n), 4)
        return 0.25 * x * np.linspace(0, 1, n) ** 2
    return np.zeros(1)


def bgm(dur, bpm=124, seed=0, rich=False):
    """BGM：キック・ハイハット・ベース（Aマイナーの4小節をくり返す）。rich=True で手拍子と分散和音も足す"""
    n = int(dur * SR)
    out = np.zeros(n + SR)
    beat = 60 / bpm
    roots = [55.0, 43.65, 65.41, 49.0]  # A1 F1 C2 G1
    kick = 0.55 * _sine(110, 42, 0.28, 0.12)
    hat = 0.10 * _noise(0.05, 0.015, seed=7)
    k = 0
    t = 0.0
    while t < dur:
        i = int(t * SR)
        out[i:i + len(kick)] += kick
        h = int((t + beat / 2) * SR)
        out[h:h + len(hat)] += hat
        root = roots[(k // 4) % 4]
        for e in (0, 0.5):
            j = int((t + e * beat) * SR)
            bass = 0.16 * np.sign(_sine(root * 2, root * 2, beat * 0.45, 0.2))  # ぶーん（くぐもった四角い波）
            bass = _lp(bass, 30)
            out[j:j + len(bass)] += bass
        if rich:
            if k % 2 == 1:  # 2・4拍目の手拍子
                cl = 0.22 * _noise(0.12, 0.04, seed=20)
                out[i:i + len(cl)] += cl
            ch = root * 8  # 分散和音（根音・短3度か長3度・5度・オクターブ）
            third = 1.189 if (k // 4) % 4 == 0 else 1.26
            for e, m in enumerate((1, third, 1.498, 2)):
                j = int((t + e * beat / 4) * SR)
                pl = 0.07 * _sine(ch * m, ch * m, beat * 0.5, 0.09)
                out[j:j + len(pl)] += pl
        t += beat
        k += 1
    return out[:n]


def mix(events, dur, music=True, bpm=124, rich=False):
    n = int(dur * SR)
    out = np.zeros(n + 3 * SR)
    if music:
        m = bgm(dur, bpm=bpm, rich=rich)
        # 1位の発表の前後は少し小さく（ドラムロールを聞かせる）
        duck = np.ones(len(m))
        for t, nm in events:
            if nm.startswith("duck:"):  # "duck:秒数" ＝その間だけBGMをぐっと小さく（発表の前のため）
                a, b = int(t * SR), int((t + float(nm.split(":")[1])) * SR)
                duck[a:b] = 0.12
            elif nm == "drumroll" and not rich:
                a, b = int(t * SR), int((t + 2.6) * SR)
                duck[a:b] = 0.35
        out[:len(m)] += m * duck * 0.55
    for t, nm in events:
        s = sfx(nm)
        i = int(t * SR)
        if 0 <= i < len(out):
            out[i:i + len(s)] += s[:len(out) - i]
    out = np.tanh(out[:n] * 1.2) * 0.9
    # はじめと終わりをなめらかに
    f = int(0.05 * SR)
    out[:f] *= np.linspace(0, 1, f)
    out[-int(0.6 * SR):] *= np.linspace(1, 0, int(0.6 * SR))
    return out


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32000).astype(np.int16)
    st = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())


# ---------------- 書き出し ----------------
def render(scenes, mp4, th, slide=0.35, music=True, bpm=124, rich=False):
    """場面を順に描いて mp4 に。切りかえは横スライド（transition="fade" の場面はふわっと・"cut" はパッと）
    場面に tdur（秒）があれば、その場面に入るときの切りかえの長さ"""
    mp4 = Path(mp4)
    total = sum(s.dur for s in scenes)
    events, t0 = [], 0.0
    for k, s in enumerate(scenes):
        if k > 0 and getattr(s, "transition", "slide") != "cut":
            events.append((t0, "whoosh"))
        events += [(t0 + t, nm) for t, nm in getattr(s, "events", [])]
        t0 += s.dur
    wav = mp4.with_suffix(".wav")
    write_wav(wav, mix(events, total, music, bpm=bpm, rich=rich))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{VW}x{VH}",
                           "-r", str(FPS), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    last = None
    for si, s in enumerate(scenes):
        nf = int(round(s.dur * FPS))
        for f in range(nf):
            t = f / FPS
            im = s.frame(t).convert("RGB")
            sl = getattr(s, "tdur", slide)
            tr = getattr(s, "transition", "slide")
            if last is not None and t < sl and tr != "cut":
                p = eo(t / sl)
                if tr == "fade":
                    im = Image.blend(last, im, p)
                else:
                    dx = int(VW * p)
                    c = Image.new("RGB", (VW, VH))
                    c.paste(last, (-dx, 0))
                    c.paste(im, (VW - dx, 0))
                    im = c
            ff.stdin.write(im.tobytes())
            if f == nf - 1:
                last = im
    ff.stdin.close()
    ok = ff.wait() == 0
    wav.unlink(missing_ok=True)
    if not ok:
        raise RuntimeError("ffmpeg が失敗")
    return mp4
