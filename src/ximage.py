"""X投稿用の画像（1080×1350・縦長）をつくる。サイトと同じ「抽選券」デザイン

kind:
  list     … 抽選の一覧（左に締切時刻、右に店名と商品）  rows=[(左, 店名, 商品)]
  ranking  … ランキング（メダル・名前・件数）            rows=[(名前, 件数の文字)]
  stat     … 大きな数字                                rows=[(ラベル, 数字)]
  text     … 見出し＋箇条書き                          rows=[文, 文, …]
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import now

W, H = 1080, 1350
FONTS = Path(__file__).resolve().parent / "fonts"
PAPER = (243, 244, 247)
CARD = (255, 255, 255)
INK = (22, 28, 46)
INK2 = (84, 92, 115)
RULE = (223, 226, 234)
RED = (200, 16, 46)
RED_SOFT = (251, 231, 234)
MEDAL = [(214, 165, 33), (150, 158, 172), (178, 108, 58)]
WEEK = "月火水木金土日"


def _f(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def F(size, w="Bold"):
    return _f(f"ZenKakuGothicNew-{w}.ttf", size)


def DELA(size):
    return _f("DelaGothicOne-Regular.ttf", size)


def _fit(d, text, font, width):
    """幅に収まらなければ末尾を … に"""
    text = text or ""
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _wrap(d, text, font, width, max_lines=3):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n" or d.textlength(cur + ch, font=font) > width:
            lines.append(cur)
            cur = "" if ch == "\n" else ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(d, lines[-1] + "……", font, width)
    return lines


def _ticket(img, box, stub=None, radius=22):
    """白い抽選券。stub の位置に切り取り線と左右の切り欠き"""
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 4, x1, y1 + 4), radius, fill=(22, 28, 46, 18))
    img.alpha_composite(sh)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius, fill=CARD, outline=RULE, width=2)
    if stub:
        r = 13
        for cy in (y0, y1):
            d.ellipse((stub - r, cy - r, stub + r, cy + r), fill=PAPER)
        y = y0 + r + 8
        while y < y1 - r - 8:
            d.line((stub, y, stub, min(y + 10, y1 - r - 8)), fill=RULE, width=3)
            y += 20


def _frame(title, kicker=None, sub=None):
    img = Image.new("RGBA", (W, H), PAPER + (255,))
    d = ImageDraw.Draw(img)
    # ヘッダー：ロゴ（トレカ［抽選］ナビ）と日時
    d.rectangle((0, 0, W, 150), fill=CARD)
    d.line((0, 150, W, 150), fill=RULE, width=2)
    d.text((62, 30), "TORECA LOTTERY NAVI", font=F(20, "Bold"), fill=INK2, spacing=0)
    x, cy = 60, 100  # ロゴの縦の中心
    big = DELA(50)
    d.text((x, cy), "トレカ", font=big, fill=INK, anchor="lm")
    x += d.textlength("トレカ", font=big) + 10
    tw = d.textlength("抽選", font=big)
    bw = tw + 34
    d.rounded_rectangle((x, cy - 36, x + bw, cy + 36), 8, fill=RED)
    for ex in (x, x + bw):
        d.ellipse((ex - 9, cy - 9, ex + 9, cy + 9), fill=CARD)
    for yy in range(int(cy - 28), int(cy + 28), 9):
        d.line((x + bw - 14, yy, x + bw - 14, yy + 4), fill=(255, 255, 255, 140), width=2)
    d.text((x + 15, cy), "抽選", font=big, fill=(255, 255, 255), anchor="lm")
    x += bw + 10
    d.text((x, cy), "ナビ", font=big, fill=INK, anchor="lm")
    t = now()
    stamp = f"{t.month}/{t.day}({WEEK[t.weekday()]}) {t.hour}:{t.minute:02d}時点"
    d.text((W - 60, 92), stamp, font=F(26, "Medium"), fill=INK2, anchor="rm")
    # 見出し
    y = 200
    if kicker:
        kw = d.textlength(kicker, font=F(30, "Black"))
        d.rounded_rectangle((60, y, 60 + kw + 36, y + 52), 26, fill=RED)
        d.text((60 + 18, y + 26), kicker, font=F(30, "Black"), fill=(255, 255, 255), anchor="lm")
        y += 72
    for line in _wrap(d, title, F(66, "Black"), W - 120, 2):
        d.text((60, y), line, font=F(66, "Black"), fill=INK)
        y += 84
    if sub:
        d.text((60, y + 4), _fit(d, sub, F(30, "Medium"), W - 120), font=F(30, "Medium"), fill=INK2)
        y += 52
    # フッター
    d.rectangle((0, H - 96, W, H), fill=RED)
    d.text((60, H - 48), "@pokepi_tcg", font=F(32, "Black"), fill=(255, 255, 255), anchor="lm")
    d.text((W - 60, H - 48), "toreca-chusen-navi.pages.dev", font=F(28, "Bold"), fill=(255, 255, 255), anchor="rm")
    return img, y + 30


def _list(img, y, rows, more=None):
    d = ImageDraw.Draw(img)
    bottom = H - 96 - 40 - (50 if more else 0)
    rh, gap = 122, 14
    n = max(1, min(len(rows), (bottom - y + gap) // (rh + gap)))
    stub = 60 + 230
    for left, store, prod in rows[:n]:
        _ticket(img, (60, y, W - 60, y + rh), stub=stub)
        d = ImageDraw.Draw(img)
        ln = left.split("\n")
        if len(ln) == 2:
            d.text((60 + 115, y + 42), ln[0], font=F(26, "Bold"), fill=INK2, anchor="mm")
            d.text((60 + 115, y + 82), ln[1], font=F(44, "Black"), fill=RED, anchor="mm")
        else:
            d.text((60 + 115, y + rh // 2), _fit(d, left, F(40, "Black"), 200), font=F(40, "Black"), fill=RED, anchor="mm")
        tx = stub + 34
        d.text((tx, y + 22), _fit(d, store, F(38, "Black"), W - 60 - 30 - tx), font=F(38, "Black"), fill=INK)
        d.text((tx, y + 72), _fit(d, prod, F(28, "Medium"), W - 60 - 30 - tx), font=F(28, "Medium"), fill=INK2)
        y += rh + gap
    rest = len(rows) - n + (more or 0)
    if rest > 0:
        d.text((W // 2, y + 18), f"ほか {rest}件はサイトで", font=F(32, "Bold"), fill=INK2, anchor="mm")


def _ranking(img, y, rows):
    d = ImageDraw.Draw(img)
    rows = rows[:5]
    gap = 22
    rh = min(170, (H - 96 - 50 - y) // max(1, len(rows)) - gap)  # 下の帯にかからない高さ
    for k, (name, val) in enumerate(rows):
        _ticket(img, (60, y, W - 60, y + rh))
        d = ImageDraw.Draw(img)
        c = MEDAL[k] if k < 3 else RULE
        cx, cy = 60 + 90, y + rh // 2
        d.ellipse((cx - 48, cy - 48, cx + 48, cy + 48), fill=c)
        d.text((cx, cy - 2), str(k + 1), font=DELA(50), fill=(255, 255, 255) if k < 3 else INK, anchor="mm")
        vw = d.textlength(val, font=F(52, "Black"))
        d.text((W - 60 - 40, cy), val, font=F(52, "Black"), fill=RED, anchor="rm")
        d.text((cx + 80, cy), _fit(d, name, F(42, "Black"), W - 60 - 40 - vw - 30 - (cx + 80)), font=F(42, "Black"), fill=INK, anchor="lm")
        y += rh + gap


def _stat(img, y, rows):
    d = ImageDraw.Draw(img)
    big = rows[0]
    need = 300 + (260 if len(rows) > 1 else 0)
    y += max(0, (H - 96 - 60 - y - need) // 2)  # 空いた所の真ん中に
    _ticket(img, (60, y, W - 60, y + 300))
    d = ImageDraw.Draw(img)
    d.text((W // 2, y + 70), big[0], font=F(36, "Bold"), fill=INK2, anchor="mm")
    d.text((W // 2, y + 190), big[1], font=DELA(140), fill=RED, anchor="mm")
    y += 330
    rest = rows[1:4]
    if rest:
        cw = (W - 120 - 24 * (len(rest) - 1)) // len(rest)
        for k, (lab, val) in enumerate(rest):
            x0 = 60 + k * (cw + 24)
            _ticket(img, (x0, y, x0 + cw, y + 230))
            d = ImageDraw.Draw(img)
            d.text((x0 + cw // 2, y + 62), _fit(d, lab, F(30, "Bold"), cw - 30), font=F(30, "Bold"), fill=INK2, anchor="mm")
            d.text((x0 + cw // 2, y + 150), val, font=DELA(72), fill=INK, anchor="mm")


def _text(img, y, rows):
    """箇条書き。行が少ない時は大きめの字で、空いた所の真ん中に置く"""
    d = ImageDraw.Draw(img)
    bottom = H - 96 - 60
    for size in (56, 50, 44, 38):
        f = F(size, "Bold")
        lines = []
        for r in rows:
            lines += [("・" if k == 0 else "　") + t for k, t in enumerate(_wrap(d, r, f, W - 240 - size, 3))]
        lh = int(size * 1.75)
        hgt = 100 + lh * len(lines)
        if y + hgt <= bottom:
            break
    hgt = min(hgt, bottom - y)
    top = y + max(0, (bottom - y - hgt) // 2)
    _ticket(img, (60, top, W - 60, top + hgt))
    d = ImageDraw.Draw(img)
    yy = top + 50
    for t in lines:
        if yy + lh > top + hgt:
            break
        d.text((120, yy), t, font=f, fill=INK)
        yy += lh


def render(kind, title, rows, kicker=None, sub=None, more=None):
    import re
    emo = re.compile("[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\uFE0F]")
    title, kicker, sub = (emo.sub("", t).strip() if t else t for t in (title, kicker, sub))
    clean = lambda v: emo.sub("", v).strip() if isinstance(v, str) else tuple(clean(x) for x in v) if isinstance(v, tuple) else v
    rows = [clean(r) for r in rows]
    img, y = _frame(title, kicker, sub)
    {"list": lambda: _list(img, y, rows, more), "ranking": lambda: _ranking(img, y, rows),
     "stat": lambda: _stat(img, y, rows), "text": lambda: _text(img, y, rows)}[kind]()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()
