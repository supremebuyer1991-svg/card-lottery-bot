"""収録カードの写真（楽天市場の商品の写真）から「カード1枚だけが写った、文字の入っていない写真」を選ぶ（11/11）

ユーザーの希望：お店の文字・ロゴ・枠・「美品」などの文字が入った写真はいらない。カード単体の写真がいい
写真の決まり（全部満たすときだけ使う）
  1. まわり（外側のふち）が無地（白など1色）
  2. 背景とちがう部分（＝写っているもの）を囲んだ四角が、カードの形（横:縦＝63:88 前後）
  3. その四角が写真の高さの6割以上（小さく写っているもの・何枚も並んだものは外す）
  4. 四角の外に、ほかの物（文字・ロゴ）がほとんどない
  5. 四角のふち（カードの外わく）がきちんとつながっている（文字のかたまりを四角とまちがえない）
"""
import io
import re

import numpy as np
import requests
from PIL import Image

CARD = 63 / 88


def check(img):
    """PIL の画像 → (OKか, 理由)"""
    im = img.convert("RGB")
    im.thumbnail((400, 400))
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    if h < 120 or w < 90:
        return False, "小さい"
    b = 3
    border = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    if (np.abs(border - bg).max(axis=1) < 28).mean() < 0.92:
        return False, "まわりが無地でない"
    m = np.abs(a - bg).max(axis=2) > 40
    rows = np.where(m.mean(axis=1) > 0.03)[0]
    cols = np.where(m.mean(axis=0) > 0.03)[0]
    if not len(rows) or not len(cols):
        return False, "何も写っていない"
    y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    bh, bw = y1 - y0, x1 - x0
    r = bw / bh
    if not (CARD * 0.88 <= r <= CARD * 1.12):
        return False, f"カードの形でない {r:.2f}"
    if bh < h * 0.6:
        return False, "カードが小さい"
    out = m.copy()
    out[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2] = False
    if out.mean() > 0.004:
        return False, "カードの外に文字など"
    ins = m[y0:y1, x0:x1]
    e = max(2, int(min(bh, bw) * 0.02))
    edges = [ins[:e].mean(), ins[-e:].mean(), ins[:, :e].mean(), ins[:, -e:].mean()]
    if min(edges) < 0.6:
        return False, "カードのわくが切れている"
    if ins.mean() < 0.7:
        return False, "中がすかすか"
    return True, "ok"


def images_of(item):
    out = []
    for u in item.get("mediumImageUrls") or []:
        u = u.get("imageUrl", "") if isinstance(u, dict) else u
        if u:
            out.append(re.sub(r"\?_ex=\d+x\d+", "", u) + "?_ex=400x400")
    return out


def pick(items, ok_item, limit=8, sess=None, log=None):
    """合う商品（ok_item が True）の写真を順に見て、最初の「カードだけの写真」を返す → (商品, 写真URL) / (最初に合った商品, "")"""
    first, n = None, 0
    for it in items:
        if not ok_item(it):
            continue
        first = first or it
        for u in images_of(it):
            if n >= limit:
                return first, ""
            n += 1
            try:
                r = (sess or requests).get(u, timeout=15)
                good, why = check(Image.open(io.BytesIO(r.content)))
            except Exception as e:
                good, why = False, f"読めない {e}"
            if log:
                log(f"  写真 {why}: {u[-60:]}")
            if good:
                return it, u
    return first, ""
