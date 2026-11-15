"""検索結果に出るタイトルを、サイト名が切れない長さにそろえる（11/15 SEO見直し）

- 幅は「全角＝1、半角＝0.5」で数える（Google は文字数ではなく表示の幅で切るため）
- サイト名「｜トレカ抽選ナビ」まで入れて LIMIT 以内に収める
- 日付の【◯/◯更新】はタイトルに入れない（説明文に入れる）
ゲーム・ホビー入荷速報（sitegen_game）からは使わない。
"""
import re

SITE = "トレカ抽選ナビ"
LIMIT = 36  # サイト名こみの幅（全角で数えて）。35字前後が目安

_UPD = re.compile(r"【[^【】]*更新】")
_PAREN = re.compile(r"\s*[（(][^（）()]*[）)]")


def tw(s):
    """表示の幅（全角1・半角0.5）"""
    return sum(0.5 if (ord(c) < 0x2000 or 0xFF61 <= ord(c) <= 0xFF9F) else 1 for c in str(s or ""))


def short_name(name, maxw=16):
    """長い店名を短く：カッコ書き（各店の一覧など）を外す。それでも長ければそのまま（店名は途中で切らない）"""
    name = str(name or "").strip()
    if tw(name) <= maxw:
        return name
    cut = _PAREN.sub("", name).strip()
    return cut or name


def fit(*cands, site=SITE, limit=LIMIT):
    """候補を「出したい順（長い順）」に渡す。サイト名こみで limit に収まる最初の候補を使う。
    どれも収まらないときは、最後（いちばん短い）候補を「｜」「・」の区切りで後ろから削る"""
    suf = "｜" + site
    room = limit - tw(suf)
    cands = [re.sub(r"\s+", " ", _UPD.sub("", c)).strip() for c in cands if c]
    for c in cands:
        if tw(c) <= room:
            return c + suf
    return squeeze(cands[-1], room) + suf


def combo(heads, tails):
    """fit に渡す候補を作る：後ろ（tails）を出したい順に、それぞれ前（heads）を長い順に組み合わせる"""
    return [h + t for t in tails if t is not None for h in heads if h]


def squeeze(body, room):
    """「A｜B・C｜D」を、A は必ず残し、後ろの区切りから入るだけ入れる"""
    if tw(body) <= room:
        return body
    segs = body.split("｜")
    out = segs[0]
    for seg in segs[1:]:
        if tw(out) + 1 + tw(seg) <= room:
            out += "｜" + seg
            continue
        parts, add = re.split(r"・(?![^（(]*[）)])", seg), ""  # カッコの中の「・」では切らない
        for p in parts:
            cand = (add + "・" + p) if add else p
            if tw(out) + 1 + tw(cand) <= room:
                add = cand
            else:
                break
        if add:
            out += "｜" + add
        break
    if tw(out) > room:  # 先頭だけでも長い：カッコ書きを外す
        cut = _PAREN.sub("", out).strip()
        if cut:
            out = cut
    return out


def clean(title, site=SITE, limit=LIMIT):
    """できあがったタイトルの最後の点検：【更新】を外し、サイト名で終わるものは幅を収める"""
    t = re.sub(r"\s+", " ", _UPD.sub("", str(title or ""))).strip()
    suf = "｜" + site
    if t.endswith(suf):
        return squeeze(t[: -len(suf)], limit - tw(suf)) + suf
    if t.startswith(site + "｜"):  # トップ：サイト名が先頭
        return site + "｜" + squeeze(t[len(site) + 1:], limit - tw(suf))
    return t
