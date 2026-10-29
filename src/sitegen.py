"""自作サイトの書き出し：state/lotteries.json → site/
  python src/sitegen.py            本番データで site/ を作る
  python src/sitegen.py --sample   サンプルデータで output/site_preview.html を作る（見た目確認用）

作るページ（すべて静的HTML。検索エンジン向けに一覧の文字も最初から埋め込む）
  /                                トップ（ポケカを表示）
  /pokeka/  /onepiece/  /fusionworld/     ゲーム別
  /pokeka/s-xxxxxxxx/              弾ごと（「〇〇 抽選」で検索されるページ）
  /pokeka/area/osaka/              都道府県ごとの店頭抽選（「ポケカ 抽選 大阪」）
  /l/xxxxxxxxxx/                   抽選ごとの個別ページ（Xに貼る用。detail.py）
  /sitemap.xml  /robots.txt
"""
import json
import re
import os
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

from common import ROOT, load_json, save_json, load_settings, now, parse_dt, sha, normalize
import detail

TEMPLATE = Path(__file__).with_name("site_template.html")
ACTIVE = ("approved", "posted", "listed")
FIELDS = ("key", "game", "store", "product", "series", "end", "conditions", "tags", "url",
          "channel", "area", "found_at", "id_check", "member", "image", "img_url", "multi", "method",
          "start", "announce", "buy", "products", "manual")
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}
GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "フュージョンワールド"}
GAME_TAB = {"onepiece": "ワンピース"}  # 上のタブ・一覧の小さなラベルだけ短く（スマホで横にはみ出さないように）
PREF = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi", "秋田県": "akita",
    "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki", "栃木県": "tochigi", "群馬県": "gunma",
    "埼玉県": "saitama", "千葉県": "chiba", "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata",
    "富山県": "toyama", "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie", "滋賀県": "shiga",
    "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo", "奈良県": "nara", "和歌山県": "wakayama",
    "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama", "広島県": "hiroshima", "山口県": "yamaguchi",
    "徳島県": "tokushima", "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi", "福岡県": "fukuoka",
    "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita", "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}

# となりの都道府県（海をはさむ所も近い所を入れる）。地域ページで「近くの県」に使う
NEAR = {
    "北海道": ["青森県", "秋田県", "岩手県"], "青森県": ["北海道", "岩手県", "秋田県"], "岩手県": ["青森県", "秋田県", "宮城県"],
    "宮城県": ["岩手県", "秋田県", "山形県", "福島県"], "秋田県": ["青森県", "岩手県", "宮城県", "山形県"], "山形県": ["秋田県", "宮城県", "福島県", "新潟県"],
    "福島県": ["宮城県", "山形県", "新潟県", "栃木県", "茨城県", "群馬県"], "茨城県": ["福島県", "栃木県", "埼玉県", "千葉県"],
    "栃木県": ["福島県", "茨城県", "群馬県", "埼玉県"], "群馬県": ["栃木県", "埼玉県", "長野県", "新潟県", "福島県"],
    "埼玉県": ["東京都", "千葉県", "茨城県", "栃木県", "群馬県", "長野県", "山梨県"], "千葉県": ["東京都", "埼玉県", "茨城県", "神奈川県"],
    "東京都": ["神奈川県", "埼玉県", "千葉県", "山梨県"], "神奈川県": ["東京都", "山梨県", "静岡県", "千葉県"],
    "新潟県": ["山形県", "福島県", "群馬県", "長野県", "富山県"], "富山県": ["新潟県", "長野県", "岐阜県", "石川県"],
    "石川県": ["富山県", "岐阜県", "福井県"], "福井県": ["石川県", "岐阜県", "滋賀県", "京都府"], "山梨県": ["東京都", "神奈川県", "埼玉県", "長野県", "静岡県"],
    "長野県": ["新潟県", "群馬県", "埼玉県", "山梨県", "静岡県", "愛知県", "岐阜県", "富山県"], "岐阜県": ["愛知県", "長野県", "富山県", "石川県", "福井県", "滋賀県", "三重県"],
    "静岡県": ["神奈川県", "山梨県", "長野県", "愛知県"], "愛知県": ["岐阜県", "三重県", "静岡県", "長野県"], "三重県": ["愛知県", "岐阜県", "滋賀県", "京都府", "奈良県", "和歌山県"],
    "滋賀県": ["京都府", "三重県", "岐阜県", "福井県"], "京都府": ["大阪府", "滋賀県", "兵庫県", "奈良県", "三重県", "福井県"],
    "大阪府": ["京都府", "兵庫県", "奈良県", "和歌山県"], "兵庫県": ["大阪府", "京都府", "岡山県", "鳥取県", "徳島県"],
    "奈良県": ["大阪府", "京都府", "三重県", "和歌山県"], "和歌山県": ["大阪府", "奈良県", "三重県"], "鳥取県": ["島根県", "岡山県", "兵庫県", "広島県"],
    "島根県": ["鳥取県", "広島県", "山口県", "岡山県"], "岡山県": ["広島県", "兵庫県", "鳥取県", "香川県"], "広島県": ["岡山県", "山口県", "島根県", "鳥取県", "愛媛県"],
    "山口県": ["広島県", "島根県", "福岡県"], "徳島県": ["香川県", "愛媛県", "高知県", "兵庫県"], "香川県": ["徳島県", "愛媛県", "岡山県"],
    "愛媛県": ["香川県", "高知県", "徳島県", "広島県"], "高知県": ["愛媛県", "徳島県", "香川県"], "福岡県": ["佐賀県", "熊本県", "大分県", "山口県"],
    "佐賀県": ["福岡県", "長崎県"], "長崎県": ["佐賀県", "福岡県"], "熊本県": ["福岡県", "大分県", "宮崎県", "鹿児島県"],
    "大分県": ["福岡県", "熊本県", "宮崎県"], "宮崎県": ["大分県", "熊本県", "鹿児島県"], "鹿児島県": ["宮崎県", "熊本県", "沖縄県"],
    "沖縄県": ["鹿児島県", "福岡県"],
}
WEEK = "月火水木金土日"


def load_images() -> dict:
    """config/images.yaml：弾名 → 商品画像URL"""
    import yaml
    p = ROOT / "config" / "images.yaml"
    if not p.exists():
        return {}
    return {k: v for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).items() if v}


# チェーン（店名で判定）。big=True は「おすすめ」（全国の多くの店舗で抽選をするので応募のチャンスが多い）
# おすすめ：ヤマダ・ジョーシン・ビックカメラ・ヨドバシ・エディオン・ゲオ・トイザらス・古本市場・ポケモンセンター
CHAINS = [
    ("yamada", "ヤマダデンキ", r"ヤマダ(電機|デンキ)|YAMADA|LABI", True),
    ("biccamera", "ビックカメラ", r"ビックカメラ|BicCamera|コジマ", True),
    ("yodobashi", "ヨドバシカメラ", r"ヨドバシ", True),
    ("edion", "エディオン", r"エディオン|EDION", True),
    ("joshin", "ジョーシン", r"ジョーシン|Joshin", True),
    ("ksdenki", "ケーズデンキ", r"ケーズデンキ", False),
    ("nojima", "ノジマ", r"ノジマ", False),
    ("tsutaya", "TSUTAYA", r"TSUTAYA|ツタヤ|蔦屋", False),
    ("geo", "ゲオ", r"ゲオ|\bGEO\b", True),
    ("aeon", "イオン", r"イオン|AEON", False),
    ("toysrus", "トイザらス", r"トイザらス|Toys\s*R\s*Us", True),
    ("bookoff", "ブックオフ", r"ブックオフ|BOOKOFF|BOOK OFF", False),
    ("furuichi", "古本市場・ふるいち", r"古本市場|ふるいち", True),
    ("hobbyoff", "ホビーオフ", r"ホビーオフ|ハードオフ|オフハウス", False),
    ("kiddyland", "キデイランド", r"キデ?[イィ]ランド|KIDDY\s*LAND", False),
    ("pokemoncenter", "ポケモンセンター", r"ポケモンセンター", True),
    ("amazon", "Amazon", r"Amazon|アマゾン", False),
    ("sevennet", "セブンネット", r"セブンネット|セブン-?イレブン", False),
    ("cardlabo", "カードラボ", r"カードラボ", False),
    ("cardcrew", "カードクルー（CARD CREW）", r"カードクルー|CARD\s*CREW", False),
    # カードショップのチェーン（「〇〇 ポケカ 抽選」で探されるので、まとめのページを作る）
    ("beatdown", "ビートダウン", r"ビートダウン", False),
    ("cardbox", "カードボックス", r"カードボックス|CARD\s*BOX", False),
    ("hobbystation", "ホビーステーション", r"ホビーステーション|ホビステ", False),
    ("torecastation", "トレカステーション", r"トレカステーション|トレステ", False),
    ("cardwings", "カードウィングス（CARD WINGS）", r"CARD\s*WINGS|カードウィングス", False),
    ("mint", "ミント（MINT）", r"(?<![ァ-ヴー])ミント|(?<![A-Za-z])MINT(?![A-Za-z])", False),
    ("magi", "magi", r"(?<![A-Za-z])magi(?![A-Za-z])", False),
    ("surugaya", "駿河屋", r"駿河屋", False),
    ("bigmagic", "BIGMAGIC", r"BIG\s*MAGIC|ビッグマジック", False),
    ("yellowsubmarine", "イエローサブマリン", r"イエローサブマリン", False),
    ("dragonstar", "ドラゴンスター", r"ドラゴンスター", False),
    ("sanyodo", "三洋堂", r"三洋堂", False),
    ("batoroco", "バトロコ", r"バトロコ", False),
    ("miraiya", "未来屋書店", r"未来屋", False),
    ("wondergoo", "WonderGOO", r"WonderGOO|ワンダーグー", False),
    ("jumpshop", "ジャンプショップ", r"ジャンプショップ", False),
    ("dmm", "DMM", r"DMM", False),
]


def _rec_note(cname):
    return '<p class="rec-note"><b>★おすすめ</b></p>'


def chain_of(store):
    import re
    for slug, name, pat, big in CHAINS:
        if re.search(pat, store or "", re.I):
            return slug
    return None


CHAIN = {c[0]: c for c in CHAINS}


_KANA = dict(zip(
    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポヴ",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho ma mi mu me mo ya yu yo ra ri ru re ro wa o n "
    "ga gi gu ge go za ji zu ze zo da ji zu de do ba bi bu be bo pa pi pu pe po vu".split()))
_SMALL = {"ャ": "ya", "ュ": "yu", "ョ": "yo", "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o"}


def romaji(text):
    """カタカナ・ひらがな・英数字をローマ字に（漢字は区切りとして扱う）。お店のアドレス用"""
    t = "".join(chr(ord(c) + 96) if "ぁ" <= c <= "ゖ" else c for c in normalize(text or ""))
    out, i = [], 0
    while i < len(t):
        c = t[i]
        if c in _KANA:
            r = _KANA[c]
            nx = t[i + 1] if i + 1 < len(t) else ""
            if nx in _SMALL:
                r = (r[:-1] if r[-1] == "i" and nx in "ャュョ" else r[:-1]) + _SMALL[nx]
                if r.startswith(("shy", "chy", "jy")):
                    r = r.replace("y", "", 1)
                i += 1
            out.append(r)
        elif c == "ッ" and i + 1 < len(t) and t[i + 1] in _KANA:
            out.append(_KANA[t[i + 1]][0])
        elif c.isascii() and c.isalnum():
            out.append(c.lower())
        elif c == "ー":
            pass
        else:
            out.append("-")
        i += 1
    return re.sub(r"-+", "-", "".join(out)).strip("-")


def store_path(store):
    """お店ごとのページ。店名（チェーン名）＋短い記号で読めるアドレスに（同じ店は同じページ）"""
    key = normalize(store or "").replace(" ", "")
    c = chain_of(store)
    base = c or romaji(re.sub(r"[（(【［\[].*?[）)】］\]]", "", store or ""))[:30].strip("-") or "shop"
    return f"store/{base}-{sha(key)[:5]}/"  # 地域は店によって抽選ごとに入ったり入らなかったりするのでアドレスに入れない


def old_store_path(store):
    return f"store/{sha(normalize(store or '').replace(' ', ''))[:8]}/"


_SER = {}


def _ser_cfg():
    """弾の別名・アドレス・基本情報（settings.yaml）。sitegen の外（xpost など）から呼ばれても使えるように読み込みは1回だけ"""
    if not _SER:
        st = load_settings()
        import newsets  # 公式サイトから自動で見つけた弾 ＋ settings.yaml（手書きが優先）
        _SER["alias"] = {g: {normalize(k): v for k, v in (m or {}).items()} for g, m in newsets.merged_aliases(st).items()}
        _SER["slug"] = newsets.merged_slugs(st)
        _SER["info"] = newsets.merged_info(st)
    return _SER


def canon_series(game, series):
    """弾名をサイト用にそろえる。「A / B」のように2つの弾をまとめた抽選は [A, B]（それぞれの弾ページに出す）"""
    if not series:
        return []
    al = _ser_cfg()["alias"].get(game, {})
    out = []
    for x in re.split(r"\s*[／/]\s*", series):
        x = x.strip()
        if not x:
            continue
        x = al.get(normalize(x), x) if normalize(x) in al else x
        if x and x not in out:
            out.append(x)
    return out


def ann_days(vals):
    """締切から結果発表までの日数（履歴の e と a から）。(中央値, 最短, 最長, 件数) か None"""
    ds = []
    for v in vals:
        if v.get("a") and v.get("e"):
            try:
                n = (__import__("datetime").date.fromisoformat(v["a"][:10]) - __import__("datetime").date.fromisoformat(v["e"][:10])).days
            except ValueError:
                continue
            if 0 <= n <= 45:
                ds.append(n)
    if not ds:
        return None
    ds.sort()
    return ds[len(ds) // 2], ds[0], ds[-1], len(ds)


def ann_text(r):
    med, lo, hi, n = r
    d = "締切の当日" if med == 0 else "締切の翌日" if med == 1 else f"締切の{med}日後"
    rng = "" if lo == hi or n < 3 else f"（早いと{'当日' if lo == 0 else f'{lo}日後'}、遅いと{hi}日後）"
    return f"多くは{d}ごろ{rng}。これまで{n}回分から"


def guess_series(game, text):
    """商品名の中から知っている弾の名前を探す（いちばん長く当てはまるもの）。なければ None"""
    t = normalize(text or "")
    if not t:
        return None
    cands = {normalize(x): x for x in (_ser_cfg()["info"].get(game) or {})}
    cands.update({k: v for k, v in (_ser_cfg()["alias"].get(game) or {}).items() if v and len(k) >= 4})
    hit = sorted((k for k in cands if k and k in t), key=len, reverse=True)
    return cands[hit[0]] if hit else None


def series_path(game, series):
    """弾ページのアドレス。決めた英語のアドレス → 英数字だけの弾名は自動 → それ以外は記号"""
    xs = canon_series(game, series) or [series]
    x = xs[0]
    slug = _ser_cfg()["slug"].get(game, {}).get(x)
    if not slug and re.fullmatch(r"[A-Za-z0-9 .\-]+", x or ""):
        slug = re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-")
    if slug:
        return f"{GAME_SLUG[game]}/{slug}/"
    return old_series_path(game, x)


def old_series_path(game, series):
    """前のアドレス（弾名の記号）。転送（_redirects）に使う"""
    return f"{GAME_SLUG[game]}/s-{sha(normalize(series))[:8]}/"


def _fmt(s):
    dt = parse_dt(s)
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}) {dt:%H:%M}" if dt else "締切 要確認"


def prerender(items) -> str:
    """JSが動く前（＝検索エンジンが最初に読む）一覧。JSが動くと本来の表示に置き換わる"""
    if not items:
        return '<div class="empty">現在受付中の抽選はありません。</div>'
    out = []
    for ch, title in (("online", "ネット抽選（当選後に発送）"), ("store", "店頭抽選（受け取りは店頭）")):
        rows = []
        for i in sorted([i for i in items if (i.get("channel") == "store") == (ch == "store")],
                        key=lambda x: x.get("end") or "9999")[:150]:
            where = f"［{i['area']}］" if ch == "store" and i.get("area") else ""
            dt = parse_dt(i.get("end"))
            when = f'<time datetime="{dt.isoformat()}">{_fmt(i.get("end"))}</time>' if dt else "締切 要確認"
            link = f' <a href="{escape(i["url"])}" rel="nofollow noopener">応募ページ</a>' if i.get("url") else ""
            rows.append(f"<li><b>{escape(where + i['store'])}</b> {escape(i.get('product') or '')} ／ 締切 {when}{link}</li>")
        if rows:
            out.append(f'<h2>{title}</h2><ul class="pre">{"".join(rows)}</ul>')
    return "".join(out)


PAGE_DROP = {"products", "start", "buy", "manual"}  # announce は「応募したリスト」で使う  # ページのJSで使わない項目（ページを軽くする）


def pack_items(items):
    """埋め込むデータを軽くする：空の項目を省く・同じ画像（楽天の長いリンク）は表にまとめて番号で持つ"""
    imgs, idx, out = [], {}, []

    def ref(src, url):
        k = (src, url)
        if k not in idx:
            idx[k] = len(imgs)
            imgs.append([src, url])
        return idx[k]
    for i in items:
        o = {k: v for k, v in i.items() if k not in PAGE_DROP and v is not None and v != "" and v != [] and v != {}}
        for k in ("found_at", "end"):  # 秒より細かい時刻はいらない
            if isinstance(o.get(k), str):
                o[k] = re.sub(r"(T\d\d:\d\d):\d\d(\.\d+)?", r"\1", o[k])
        if o.get("image"):
            o["im"] = ref(o.pop("image"), o.pop("img_url", None))
        o.pop("img_url", None)
        if o.get("images"):
            o["ims"] = [ref(x["src"], x.get("url")) for x in o.pop("images")]
        out.append(o)
    return out, imgs


def _yen(v):
    return f"¥{v:,}"


def _diff(a, b):
    """前と比べた差（▲+1,200円 +5.1%）"""
    if a is None or b is None or not b:
        return "", "flat"
    d = a - b
    pct = d * 100 / b
    cls = "up" if d > 0 else "down" if d < 0 else "flat"
    mark = "▲" if d > 0 else "▼" if d < 0 else "±"
    return f"{mark}{abs(d):,}円（{'+' if d > 0 else '−' if d < 0 else '±'}{abs(pct):.1f}%）", cls


def spark(points, w=300, h=64):
    """30日の値動きの小さなグラフ（SVG）"""
    vs = [v for _, v in points]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1
    xs = [round(i * (w - 8) / (len(vs) - 1) + 4, 1) for i in range(len(vs))]
    ys = [round(h - 6 - (v - lo) * (h - 12) / rng, 1) for v in vs]
    pts = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    col = "var(--red)" if vs[-1] >= vs[0] else "#2563eb"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="30日の値動き（{_yen(lo)}〜{_yen(hi)}）">'
            f'<polyline fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>'
            f'<circle cx="{xs[-1]}" cy="{ys[-1]}" r="3.2" fill="{col}"/></svg>')


def _md(d):
    y, m, dd = d.split("-")
    return f"{int(m)}/{int(dd)}"


def souba_block(x, sm, fx=None, link=True):
    """弾ページの相場の欄：いまの相場・定価との差・前日比・7日前比・30日のグラフ・海外"""
    if not sm:
        return ""
    t = sm.get("teika")
    gap = sm["price"] - t if t else None
    d1, c1 = _diff(sm["price"], sm["prev"][1] if sm.get("prev") else None)
    d7, c7 = _diff(sm["price"], sm["week"][1] if sm.get("week") else None)
    rows = []
    if t:
        rows.append(f'<div><span>定価</span><b>{_yen(t)}</b></div>')
        rows.append(f'<div><span>定価との差</span><b class="{"up" if gap > 0 else "down" if gap < 0 else "flat"}">'
                    f'{"+" if gap > 0 else "−" if gap < 0 else "±"}{abs(gap):,}円</b></div>')
    if d1:
        rows.append(f'<div><span>{_md(sm["prev"][0])}比</span><b class="{c1}">{d1}</b></div>')
    if d7:
        rows.append(f'<div><span>1週間前（{_md(sm["week"][0])}）比</span><b class="{c7}">{d7}</b></div>')
    us = ""
    if sm.get("us"):
        ud, uv = sm["us"]
        yen = f"（約{_yen(round(uv * fx))}）" if fx else ""
        us = (f'<p class="sb-us">海外（アメリカ TCGplayer・{_md(ud)}）：${uv:,.2f}{yen}'
              + (f"　前日比 {'+' if uv >= sm['us_prev'][1] else '−'}{abs(uv - sm['us_prev'][1]) * 100 / sm['us_prev'][1]:.1f}%" if sm.get("us_prev") else "")
              + "</p>")
    src = f'https://snkrdunk.com/apparels/{sm["snkr"]}' if sm.get("snkr") else ""
    return (f'<section class="souba" aria-label="{escape(x)}の相場"><div class="sb-h"><b>{escape(x)}の相場</b>'
            f'<small>スニダン・{_md(sm["date"])}の取引</small></div>'
            f'<div class="sb-main"><div class="sb-now"><em>{_yen(sm["price"])}</em>'
            + (f'<span>定価より <b>{abs(gap):,}円</b> 高い相場です</span>' if t and gap > 0 else "")
            + f'</div>{spark(sm.get("points") or [])}</div><div class="sb-grid">{"".join(rows)}</div>{us}'
            f'<p class="sb-note">※スニダンでその日に成立した「1個」の取引の平均です（買取価格ではありません）。取引が少ない日は1件で大きく動きます。'
            + (f' <a href="{src}" rel="nofollow noopener" target="_blank">スニダンで見る</a>' if src else "")
            + ("　<a href=\"/souba/\">ほかのBOXの相場</a>" if link else "") + "</p></section>")


def og_image(path, game_label, color, title, rows, sub=""):
    """弾ページの共有画像（XやLINEにリンクを貼ったときに出る画像）。1200×630"""
    from PIL import Image, ImageDraw, ImageFont
    fdir = Path(__file__).with_name("fonts")
    F = lambda w, n: ImageFont.truetype(str(fdir / f"ZenKakuGothicNew-{w}.ttf"), n)
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#0f172a")
    d = ImageDraw.Draw(im)
    for y in range(H):  # 上から下へ少しずつ色を変える
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(15 + 15 * t), int(23 + 8 * t), int(42 + 20 * t)))
    d.rectangle([0, 0, 14, H], fill=color)
    f = F("Bold", 30)
    tw = d.textlength(game_label, font=f)
    d.rounded_rectangle([60, 52, 60 + tw + 44, 104], radius=26, fill=color)
    d.text((82, 78), game_label, font=f, fill="#111827", anchor="lm")
    size = 76
    while size > 40 and d.textlength(title, font=F("Black", size)) > W - 120:
        size -= 4
    d.text((60, 175), title, font=F("Black", size), fill="#ffffff", anchor="lm")
    if sub:
        d.text((60, 250), sub, font=F("Medium", 32), fill="#cbd5e1", anchor="lm")
    y = 298
    for k, v, hl in rows[:4]:
        d.rounded_rectangle([60, y, W - 60, y + 52], radius=14, fill="#1e293b")
        d.text((88, y + 26), k, font=F("Bold", 27), fill="#94a3b8", anchor="lm")
        d.text((W - 88, y + 26), v, font=F("Black", 32), fill=color if hl else "#f8fafc", anchor="rm")
        y += 62
    d.text((60, H - 26), "トレカ抽選ナビ", font=F("Black", 28), fill="#ffffff", anchor="ls")
    d.text((W - 60, H - 26), "tcg-chusen.com", font=F("Bold", 26), fill=color, anchor="rs")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def page(data: dict, meta: dict, standalone=True) -> str:
    base = meta.get("root", "/")
    canon = meta.get("canonical")
    site = meta.get("site", "")
    head = []
    if site:  # 古いアドレス（*.pages.dev）で開かれたら、同じページの独自ドメインへ移動
        head.append('<script>if(/\\.pages\\.dev$/.test(location.hostname))location.replace(%s+location.pathname+location.search+location.hash)</script>' % json.dumps(site))
    if canon:
        head += [f'<link rel="canonical" href="{escape(canon)}">',
                 f'<meta property="og:url" content="{escape(canon)}">']
    og_img = meta.get("og_image") or (f"{site}/og.png" if site else "/og.png")
    head += [f'<meta property="og:title" content="{escape(meta["title"])}">',
             f'<meta property="og:description" content="{escape(meta["desc"])}">',
             '<meta property="og:type" content="website">', '<meta property="og:site_name" content="トレカ抽選ナビ">',
             '<meta property="og:locale" content="ja_JP">',
             f'<meta property="og:image" content="{escape(og_img)}">', '<meta property="og:image:width" content="1200">',
             '<meta property="og:image:height" content="630">',
             '<meta name="twitter:card" content="summary_large_image">',
             f'<meta name="twitter:image" content="{escape(og_img)}">',
             '<meta name="theme-color" content="#c8102e">',
             '<link rel="icon" href="/favicon.svg" type="image/svg+xml">', '<link rel="icon" href="/favicon.png" sizes="48x48">',
             '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
             ('<meta name="robots" content="noindex,follow">' if meta.get("noindex")
              else '<meta name="robots" content="index,follow,max-image-preview:large">')]
    if meta.get("verify"):
        head.append(f'<meta name="google-site-verification" content="{escape(meta["verify"])}">')
    for ld in meta.get("ld") or []:
        head.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    body = TEMPLATE.read_text(encoding="utf-8")
    for k, v in {"__TITLE__": escape(meta["title"]), "__DESC__": escape(meta["desc"]),
                 "__HEADMETA__": "\n".join(head), "__ROOT__": escape(base), "__H1__": escape(meta["h1"]),
                 "__LEAD__": escape(meta["lead"]), "__SUMMARY__": escape(meta.get("summary", "")),
                 "__CRUMBS__": meta.get("crumbs", ""),
                 "__LINKS__": meta.get("links", ""), "__AFF__": meta.get("aff", ""), "__SUPPLY__": meta.get("supply", ""),
                 "__PRERENDER__": meta.get("prerender", ""), "__FAQ__": meta.get("faq_html", "")}.items():
        body = body.replace(k, v)
    if data.get("items") and not data.get("sample"):
        data = dict(data)
        packed, data["imgs"] = pack_items(data["items"])
        # 表の形で持つ（項目名を1回だけ書く）＝ページが軽くなる。ページのJSで元の形に戻す
        cols = []
        for o in packed:
            for k in o:
                if k not in cols:
                    cols.append(k)
        data.pop("items")
        data["cols"] = cols
        data["rows"] = [[o.get(k) for k in cols] for o in packed]
    body = body.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    if not standalone:
        return body
    # テンプレートの <header> より前（title・meta・CSS）は <head> に入れる（検索エンジンは <head> の中を読む）
    cut = body.index("<header")
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>[hidden]{display:none!important}body{margin:0}img{max-width:100%}'
            ':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>'
            f'{body[:cut]}</head><body>{body[cut:]}</body></html>')


def _ser_areas(game, slug, series, si):
    """弾のページに「この弾の店頭抽選がある都道府県」へのリンク"""
    cnt = {}
    for i in si:
        if i.get("channel") == "store" and i.get("area") in PREF:
            cnt[i["area"]] = cnt.get(i["area"], 0) + 1
    if not cnt or game not in ("pokemon", "onepiece"):
        return ""
    order = list(PREF)
    return ('<nav class="ser-areas" aria-label="店頭抽選がある都道府県"><b>「' + escape(series) + '」の店頭抽選がある都道府県</b>' +
            "".join(f'<a href="/{slug}/area/{PREF[a]}/">{escape(a)}<span>{n}</span></a>' for a, n in sorted(cnt.items(), key=lambda kv: order.index(kv[0]))) +
            "</nav>")


def _links(title, pairs):
    if not pairs:
        return ""
    return (f'<nav class="links" aria-label="{escape(title)}"><b>{escape(title)}</b>' +
            "".join(f'<a href="{escape(h)}">{escape(t)}</a>' for t, h in pairs) + "</nav>")


GAME_EN = {"pokemon": "POKEMON CARD", "onepiece": "ONE PIECE CARD", "dragonball": "FUSION WORLD"}


def _menu(items, games, g, here=""):
    """「抽選をさがす」メニュー（ページ下部＋ヘッダーのメニューボタンで開くシート）。
    タイトル（件数つきカード）／弾ごと（多い順・件数つき）／店頭抽選の地域"""
    gi = [i for i in items if i["game"] == g]
    slug = GAME_SLUG[g]
    cards = []
    for x in games:
        n = sum(1 for i in items if i["game"] == x)
        cur = ' aria-current="page"' if x == g else ""
        cards.append(f'<a class="m-game g-{x}" href="/{GAME_SLUG[x]}/"{cur}><small>{GAME_EN[x]}</small>'
                     f'<b>{escape(GAME_SHORT[x])}</b><span><em>{n}</em>件 受付中</span></a>')
    cnt = {}
    for i in gi:
        for x in i.get("sers") or ([i["series"]] if i.get("series") else []):
            cnt[x] = cnt.get(x, 0) + 1
    ser = sorted(cnt, key=lambda x: -cnt[x])

    def row(k, x):
        href = "/" + series_path(g, x)
        cur = ' aria-current="page"' if href == here else ""
        return (f'<li><a href="{escape(href)}"{cur}><i>{k:02d}</i><b>{escape(x)}</b>'
                f'<span>{cnt[x]}件</span></a></li>')
    rows = [row(k, x) for k, x in enumerate(ser, 1)]
    ser_html = ""
    if rows:
        ser_html = (f'<section class="m-sec"><h3>{escape(GAME_SHORT[g])}の弾ごと<small>受付中が多い順</small></h3>'
                    f'<ol class="m-ser">{"".join(rows[:8])}</ol>'
                    + (f'<details class="m-more"><summary>すべての弾を見る（{len(rows)}）</summary>'
                       f'<ol class="m-ser" start="9">{"".join(rows[8:])}</ol></details>' if len(rows) > 8 else "")
                    + '</section>')
    acnt = {}
    for i in gi:
        if i.get("channel") == "store" and i.get("area") in PREF:
            acnt[i["area"]] = acnt.get(i["area"], 0) + 1
    area_html = ""
    if acnt:
        chips = "".join(f'<a href="/{slug}/area/{PREF[a]}/">{escape(a)}<span>{acnt[a]}</span></a>'
                        for a in sorted(acnt, key=lambda a: list(PREF).index(a)))
        area_html = (f'<section class="m-sec"><h3>店頭抽選を地域でさがす<small>{len(acnt)}都道府県</small></h3>'
                     f'<div class="m-area">{chips}</div></section>')
    ccnt = {}
    for i in items:
        if i.get("chain"):
            ccnt[i["chain"]] = ccnt.get(i["chain"], 0) + 1
    top = sorted(ccnt, key=lambda c: (not CHAIN[c][3], -ccnt[c]))[:10]
    store_html = ('<section class="m-sec"><h3>お店からさがす<small>★＝大手・おすすめ</small></h3>'
                  '<div class="m-area"><a href="/store/">店舗一覧（都道府県別）</a>' +
                  "".join(f'<a href="/chain/{c}/">{"★" if CHAIN[c][3] else ""}{escape(CHAIN[c][1])}<span>{ccnt[c]}</span></a>' for c in top) +
                  '</div></section>')
    today_d = now().date().isoformat()
    up = sorted([(inf.get("release"), x) for x, inf in (_ser_cfg()["info"].get(g) or {}).items()
                 if str(inf.get("release") or "") > today_d])
    up_html = ('<section class="m-sec"><h3>発売予定の弾<small>抽選・予約はここに載ります</small></h3><div class="m-area">' +
               "".join(f'<a href="/{series_path(g, x)}">{escape(x)}<span>{int(r[5:7])}/{int(r[8:10])}</span></a>' for r, x in up) +
               '</div></section>') if up else ""
    cond_html = up_html + ('<section class="m-sec"><h3>条件でさがす</h3><div class="m-area">' +
                 (f'<a href="/{slug}/no-id/">本人確認なし</a><a href="/{slug}/online/">ネット抽選</a><a href="/{slug}/today/">今日締切</a>' if gi else "") +
                 '<a href="/guide/">抽選の当て方・コツ</a><a href="/souba/">BOXの相場</a><a href="/weekly/">今週のまとめ</a><a href="/kekka/">抽選結果</a><a href="/calendar/">発売日カレンダー</a><a href="/mylist/">応募したリスト</a></div></section>')
    return (f'<nav class="menu" aria-label="抽選をさがす"><section class="m-sec"><h3>タイトルで選ぶ</h3>'
            f'<div class="m-games">{"".join(cards)}</div></section>{ser_html}{cond_html}{area_html}{store_html}</nav>')


def _amz(q, tag):
    return f"https://www.amazon.co.jp/s?k={quote(q)}&tag={quote(tag)}"


def _rak(q, aff):
    """楽天の検索結果ページへのアフィリエイトリンク（楽天アフィリエイトの公式の形式）"""
    u = f"https://search.rakuten.co.jp/search/mall/{quote(q)}/"
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(u, safe='')}&m={quote(u, safe='')}" if aff else u


# サプライのアイコン（自作の簡単な図形）
_ICON = {
    "スリーブ": '<rect x="7" y="4" width="14" height="20" rx="2"/><rect x="10" y="7" width="8" height="12" rx="1" opacity=".45"/>',
    "ローダー": '<rect x="6" y="3" width="16" height="22" rx="2.5" stroke-width="2.4"/><rect x="10" y="7" width="8" height="12" rx="1" opacity=".45"/>',
    "デッキケース": '<path d="M5 9h18v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"/><path d="M5 9l3-5h12l3 5"/><path d="M12 14h4"/>',
    "ストレージ": '<rect x="3" y="10" width="22" height="14" rx="2"/><path d="M3 10l2-5h18l2 5"/><path d="M10 15h8"/>',
}


def _icon(k):
    return (f'<svg viewBox="0 0 28 28" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">{_ICON[k]}</svg>')


_REL = 'target="_blank" rel="nofollow sponsored noopener"'


def _product_ad(x, name, rr, tag, aff):
    """弾ページの広告：商品写真＋楽天／Amazonのボタン＋一緒に使うサプライ"""
    if not (tag or aff or rr.get("url")):
        return ""
    rak = rr.get("url") or _rak(f"{name} {x}", aff)
    amz = _amz(f"{name} {x}", tag) if tag else ""
    img = (f'<img src="{escape(rr["image"])}" alt="{escape(x)}" loading="lazy">' if rr.get("image")
           else f'<span class="ph">{_icon("ストレージ")}</span>')
    btns = (f'<a class="b-rak" href="{escape(rak)}" {_REL}>楽天市場で見る</a>' +
            (f'<a class="b-amz" href="{escape(amz)}" {_REL}>Amazonで見る</a>' if amz else ""))
    sup = "".join(f'<a href="{escape(_amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff))}" {_REL}>{_icon(k)}<span>{k}</span></a>'
                  for k in ("スリーブ", "ローダー", "デッキケース"))
    return (f'<aside class="ad"><div class="ad-top"><span class="ad-pr">PR</span><span>抽選に外れても、通販で探せます</span></div>'
            f'<div class="ad-main"><a class="ad-img" href="{escape(rak)}" {_REL}>{img}</a>'
            f'<div class="ad-info"><small>{escape(name)}</small><b>{escape(x)}</b><div class="ad-btns">{btns}</div></div></div>'
            f'<div class="ad-sup"><p>一緒にそろえたいサプライ</p><div>{sup}</div></div></aside>')


def _flow_ad(prods, title):
    """商品写真が横に流れる広告。prods: [(ゲーム略称, 弾名, 画像URL, 楽天リンク, 件数)]（画像のあるものだけ）"""
    prods = [p for p in prods if p[2] and p[3]][:14]
    if len(prods) < 3:
        return ""
    cards = "".join(
        f'<a class="fi" href="{escape(u)}" {_REL}><span class="fi-img"><img src="{escape(img)}" alt="{escape(x)}" loading="lazy"></span>'
        f'<small>{escape(g)}・抽選{n}件</small><b>{escape(x)}</b><em>楽天で見る</em></a>'
        for g, x, img, u, n in prods)
    sec = max(24, len(prods) * 5)  # 1枚あたり約5秒で流れる
    return (f'<aside class="ad ad-flow"><div class="ad-top"><span class="ad-pr">PR</span><span>{escape(title)}</span></div>'
            f'<div class="flow-wrap"><div class="flow-track" style="--sec:{sec}s">{cards}'
            f'<span class="flow-dup" aria-hidden="true">{cards}</span></div></div></aside>')


def _supply_ad(short, name, tag, aff, prices=None, game=None):
    """ゲームページの広告：サプライ4ジャンルのタイル。楽天の最安値があれば「¥199〜」を表示（押すと楽天の安い順）"""
    if not (tag or aff):
        return ""
    prices = prices or {}
    tiles, dates = [], []
    for k in ("スリーブ", "ローダー", "デッキケース", "ストレージ"):
        p = prices.get(k) or prices.get(f"{game}|{k}") or {}
        if p.get("price") and p.get("url"):
            href, price = p["url"], f'<small>楽天</small><strong>¥{p["price"]:,}〜</strong>'
            dates.append(p.get("fetched_at") or "")
        else:
            href = _amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff)
            price = ""
        tiles.append(f'<a href="{escape(href)}" {_REL}>{_icon(k)}<span>{k}</span>{price}</a>')
    amz = ("".join(f'<a href="{escape(_amz(f"{name} {k}", tag))}" {_REL}>{k}</a>'
                   for k in ("スリーブ", "ローダー", "デッキケース", "ストレージ")) if tag else "")
    note = ""
    if dates:
        d = parse_dt(max(dates))
        note = f'<p class="ad-note">価格は楽天市場の{d.month}/{d.day}時点の最安値（税込）</p>' if d else ""
    return (f'<aside class="ad"><div class="ad-top"><span class="ad-pr">PR</span><span>{escape(short)}のサプライをさがす</span></div>'
            f'<div class="ad-sup ad-tiles"><div>{"".join(tiles)}</div></div>{note}'
            + (f'<div class="ad-amz"><b>Amazonで見る</b>{amz}</div>' if amz else "") + '</aside>')


AMZ_SHORT = ("amzn.to", "amzn.asia", "link.amazon", "a.co")


def own_amazon_url(url, name, tag):
    """Amazonのリンクを自分のタグ付きに作り直す（他人のタグ・短縮リンクは使わない）。Amazon以外はそのまま"""
    import re
    from urllib.parse import urlparse
    if not url or not tag:
        return url
    host = urlparse(url).netloc.lower()
    if "amazon." in host:
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        return f"https://www.amazon.co.jp/dp/{m.group(1)}/?tag={quote(tag)}" if m else _amz(name, tag)
    if host in AMZ_SHORT:  # 短縮リンクの中身（商品）は分からないので、商品名の検索にする
        return _amz(name, tag)
    return url


def amazon_invites(items, tag):
    """ネット抽選の一番上に固定する「Amazon 招待リクエスト」の券の中身。ゲームごとに [{name, url}]
    商品ページ（/dp/）のあるものを先に、短縮リンクしかないものは同じ商品が無いときだけ（検索リンクで）入れる"""
    import re
    norm = lambda s: re.sub(r"[\s・「」『』()（）\-]", "", (s or "").lower())
    rows = []
    for i in items:
        if "amazon" not in ((i.get("store") or "") + (i.get("url") or "")).lower() or i.get("channel") == "store":
            continue
        p = i.get("product") or ""
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", i.get("url") or "")
        name = i.get("series") or p
        sub = re.search(r"[（(]([^）)]{2,30})[）)]", p)
        if sub and "招待" not in sub.group(1) and "BOX" not in sub.group(1):
            name = f"{name}（{sub.group(1)}）"
        rows.append((0 if m else 1, i["game"], m.group(1) if m else None, name, p, i.get("url")))
    out = {}
    for has_short, g, asin, name, p, url in sorted(rows, key=lambda r: r[0]):
        lst = out.setdefault(g, [])
        seen = " ".join(norm(x["name"]) + " " + norm(x["p"]) for x in lst)
        if (asin and any(x["asin"] == asin for x in lst)) or any(x["name"] == name for x in lst):
            continue
        if not asin and norm(name) and norm(name) in seen:
            continue  # 短縮リンクの商品が、商品ページのある行と同じなら入れない
        lst.append({"asin": asin, "name": name, "p": p, "url": own_amazon_url(url, p or name, tag)})
    return {g: [{"name": x["name"], "url": x["url"]} for x in v] for g, v in out.items()}


# 商品名から画像を探すとき、これだけでは商品が決まらない短い語（ほかの弾名の一部にもなる）
IMG_IGNORE = {"mega", "30th", "30周年", "heroines", "box"}


def match_images(game, texts, rk, images, aliases, series=None):
    """抽選の商品名（弾名・商品名・商品リスト）から、載っている商品ごとに画像を探す。
    商品名を「／」「、」「＋」などで区切り、区切りごとに1つの弾を選ぶ（区切りの中では後ろに出てくる名前ほど具体的なので優先。
    例：「30th CELEBRATION プレミアムデッキセット エーフィ・ブラッキー」→ エーフィ・ブラッキー）。
    長い名前の一部（「30th CELEBRATION カードセット」の中の「30th CELEBRATION」）は数えない。
    商品名から決まらなければ弾名（series）の画像。
    返り値: [(画像URL, 楽天リンク or None), ...]（同じ商品は1つ・最大4つ）"""
    from rakuten import _norm
    keys = {}
    for k in rk:
        g, _, x = k.partition("|")
        if g == game:
            keys[_norm(x)] = x
    for x in images:
        keys.setdefault(_norm(x), x)
    for a, x in ((aliases or {}).get(game) or {}).items():
        keys[_norm(a)] = x
    keys = {nk: x for nk, x in keys.items() if len(nk) >= 3 and nk not in IMG_IGNORE}

    picked = []
    for seg in re.split(r"[／/、，,＋+]", "／".join(x for x in texts[1:] if x)):
        t = _norm(seg)
        spans = []
        for nk, x in keys.items():
            p = t.find(nk)
            while p >= 0:
                spans.append((p, p + len(nk), x))
                p = t.find(nk, p + 1)
        kept = []
        for s_ in sorted(spans, key=lambda s: (s[0] - s[1], s[0])):  # 長い順
            if not any(k[0] <= s_[0] and s_[1] <= k[1] for k in kept):
                kept.append(s_)
        if kept:
            picked.append(max(kept, key=lambda s: s[0])[2])  # 区切りの中でいちばん後ろの名前
    if not picked and series:
        picked = [series]  # 商品名から分からなければ弾名で
    out, seen_img, seen_name = [], set(), []
    for x in picked:
        nx = _norm(x)
        if any(nx in y or y in nx for y in seen_name):
            continue  # 同じ商品（「バトルコレクション」と「スタートデッキ100 バトルコレクション」など）
        seen_name.append(nx)
        r = rk.get(f"{game}|{x}") or {}
        img = images.get(x) or r.get("image")
        if img and img not in seen_img:
            seen_img.add(img)
            out.append((img, None if images.get(x) else r.get("url")))
    return out[:4]


def active_series(settings=None):
    """{game: [弾名（受付中が多い順）]}"""
    s = settings or load_settings()
    cnt = {}
    for i in load_json("lotteries.json", {}).values():
        if i.get("status") not in ACTIVE or not i.get("series"):
            continue
        e = parse_dt(i.get("end"))
        if e and e < now():
            continue
        cnt.setdefault(i["game"], {}).setdefault(i["series"], 0)
        cnt[i["game"]][i["series"]] += 1
    return {g: sorted(c, key=lambda x: -c[x]) for g, c in cnt.items() if g in s["game_names"]}


def build(settings=None, out_dir=None, sample=None):
    s = settings or load_settings()
    site = (s.get("site_public_url") or os.environ.get("SITE_URL") or "").rstrip("/")
    tag = os.environ.get("AMAZON_TAG") or s.get("amazon_tag")
    raff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or s.get("rakuten_affiliate_id") or "").strip()
    out = Path(out_dir or ROOT / "site")
    games = [g for g in s["game_names"]]

    prices = load_json("rakuten_prices.json", {}) if sample is None else {}  # サプライの楽天最安値
    import souba as souba_mod
    souba_raw = load_json("souba.json", {}) if sample is None else {}
    souba_fx = souba_raw.get("fx")
    souba_sm = {k: souba_mod.summary(v) for k, v in (souba_raw.get("items") or {}).items()}
    souba_sm = {k: v for k, v in souba_sm.items() if v}
    if sample is not None:
        items = sample
    else:
        images = load_images()
        from rakuten import item_link
        rk = {k: dict(v, url=item_link(v.get("url"), raff)) for k, v in load_json("rakuten.json", {}).items()}  # 楽天の商品画像＋自分のIDのリンク
        for k, v in (s.get("rakuten_fixed") or {}).items():  # 手で決めた画像・リンクを優先
            rk[k] = {"image": v.get("image", ""), "url": item_link(v.get("url"), raff)}
        items = []
        raw_lots = load_json("lotteries.json", {})
        for i in raw_lots.values():
            if i.get("status") not in ACTIVE:
                continue
            e = parse_dt(i.get("end"))
            if e and e < now():
                continue
            row = {k: i.get(k) for k in FIELDS}
            for k_ in ("product", "conditions"):  # 「ワンピカード」とは書かない
                if isinstance(row.get(k_), str):
                    row[k_] = row[k_].replace("ワンピカード", "ワンピースカード")
            row["lpath"] = detail.lottery_path(i)  # 抽選ごとの個別ページ
            row["image"] = row.get("image") or images.get(i.get("series") or "")
            row["url"] = own_amazon_url(row.get("url"), row.get("product") or row.get("series") or "", tag)
            if tag and re.search(r"amazon|アマゾン", row.get("store") or "", re.I) and "amazon." not in (row.get("url") or ""):
                row["url"] = _amz(row.get("series") or row.get("product") or "", tag)  # XのURL（t.co）などは自分のタグ付きの検索に
            r = rk.get(f"{i.get('game')}|{i.get('series')}") or {}
            if not row["image"] and r.get("image"):
                row["image"], row["img_url"] = r["image"], r.get("url")
            # 商品名からも画像を探す（弾名が空の抽選・複数の商品をまとめた抽選）
            found = match_images(i.get("game"), [i.get("series"), i.get("product")] + list(i.get("products") or []),
                                 rk, images, s.get("image_aliases"), i.get("series"))
            if found:
                row["image"], row["img_url"] = found[0]
                if len(found) > 1:
                    row["images"] = [{"src": a, "url": b} for a, b in found[:4]]
            sers = canon_series(i.get("game"), i.get("series"))  # 別名をまとめる・「A / B」は両方の弾に出す
            row["series"] = sers[0] if sers else None  # 別のゲームの商品が入っていた弾名は外す
            if sers:
                if len(sers) > 1:
                    row["sers"] = sers
            if row.get("store"):
                row["spath"] = store_path(row["store"])
                ch_ = chain_of(row["store"])
                if ch_:
                    row["chain"] = ch_
                    if CHAIN[ch_][3]:
                        row["rec"] = True  # 大手チェーン（おすすめ）
            items.append(row)

    # 中身が変わっていなければ「最終更新」も据え置き（無駄な再公開をしない）
    meta_state = load_json("site_meta.json", {})
    digest = sha(json.dumps(sorted(items, key=lambda x: x.get("key") or ""), ensure_ascii=False, sort_keys=True))
    digest = sha(digest + str(load_json("x_trends.json", {}).get("generated")))
    digest = sha(digest + json.dumps(sorted((load_json("newsets.json", {}).get("series") or {}).get("pokemon", {})) +
                                     sorted((load_json("newsets.json", {}).get("series") or {}).get("onepiece", {})) +
                                     sorted(load_json("results.json", {})), ensure_ascii=False))  # 新弾が増えたら公開し直す
    digest = sha(digest + str(load_json("souba.json", {}).get("updated")))  # BOX相場を読み直したら（朝・夜21時ごろ）公開し直す  # 話題ネタが更新されたら下書きページも出し直す
    changed = meta_state.get("digest") != digest
    updated = now().isoformat() if changed or not meta_state.get("updated") else meta_state["updated"]

    common_data = {"sample": False, "updated": updated,
                   "games": [{"id": g, "name": GAME_SHORT[g], "tab": GAME_TAB.get(g, GAME_SHORT[g])} for g in games],
                   "gameUrls": {"all": "/", **{g: f"/{GAME_SLUG[g]}/" for g in games}}, "items": items,
                   "gameNames": {g: s["game_names"][g] for g in games}, "amazonTag": tag or "", "amazonInvites": amazon_invites(items, tag) if tag else {}}
    urls = []
    upd = parse_dt(updated) or now()
    md = f"{upd.month}/{upd.day}"
    verify = s.get("google_site_verification") or os.environ.get("GOOGLE_SITE_VERIFICATION") or ""
    game_counts = {g: sum(1 for i in items if i["game"] == g) for g in games}

    def summary(sub, what):
        """ページごとの要約文（件数・一番近い締切・店頭が多い都道府県）。検索結果にも使われる独自の文章"""
        if not sub:
            return f"現在受付中の{what}はありません。新しい抽選が見つかり次第、自動で追加されます。"
        on = sum(1 for i in sub if i.get("channel") != "store")
        txt = f"現在受付中の{what}は{len(sub)}件" + (f"（ネット抽選{on}件・店頭抽選{len(sub) - on}件）。" if 0 < on < len(sub) else "。")
        soon = sorted([i for i in sub if parse_dt(i.get("end"))], key=lambda i: i["end"])
        if soon:
            i = soon[0]
            txt += f"締切が一番近いのは{i['store']}の「{i.get('series') or i.get('product')}」（{_fmt(i['end'])}締切）。"
        cnt = {}
        for i in sub:
            if i.get("channel") == "store" and i.get("area"):
                cnt[i["area"]] = cnt.get(i["area"], 0) + 1
        top3 = sorted(cnt, key=lambda a: -cnt[a])[:3]
        if top3:
            txt += "店頭抽選が多い地域は" + "・".join(f"{a}（{cnt[a]}件）" for a in top3) + "です。"
        return txt

    upd_hm = f"{upd.month}/{upd.day} {upd:%H:%M}"

    def jdate(d):
        dt = parse_dt(d + "T00:00:00+09:00") if d and len(d) == 10 else None
        return f"{dt.year}年{dt.month}月{dt.day}日" if dt else d

    def faq_for(sub, what, x_info=None, x_label=None):
        """よくある質問（画面に出す文と構造化データの文は同じもの）"""
        qa = []
        if x_info and x_info.get("release"):
            qa.append((f"{x_label}の発売日はいつですか？",
                       f"{x_label}（{x_info.get('type') or '商品'}）の発売日は{jdate(x_info['release'])}です。"
                       "発売前から予約抽選が始まり、発売後も再販・入荷分の抽選が行われることがあります。"))
        if x_info and x_info.get("price"):
            qa.append((f"{x_label}の定価（希望小売価格）はいくらですか？",
                       f"メーカー希望小売価格は{x_info['price']}です。抽選販売は定価で買えることが多く、"
                       "ほかの商品と一緒に買うセット販売の場合もあるため、各抽選の条件をご確認ください。"))
        n = len(sub)
        on = sum(1 for i in sub if i.get("channel") != "store")
        if n:
            qa.append((f"{what}はどこで応募できますか？",
                       f"{upd_hm}時点で受付中の{what}は{n}件です（ネット抽選{on}件・店頭抽選{n - on}件）。"
                       "ネット抽選は当選すると自宅に発送され、店頭抽選は店舗で受け取ります。"
                       "一覧の「応募する」から各店舗の応募ページに進めます。"))
            noid = sum(1 for i in sub if i.get("id_check") is False)
            nomem = sum(1 for i in sub if i.get("member") == "none")
            qa.append((f"本人確認や会員登録なしで応募できる{what}はありますか？",
                       f"本人確認が不要と分かっている抽選は{noid}件、会員登録が不要な抽選は{nomem}件です。"
                       "一覧の「本人確認なし」「会員不要」で絞り込めます。条件は変わることがあるため、応募前に各店舗の告知をご確認ください。"))
            soon = sorted([i for i in sub if parse_dt(i.get("end"))], key=lambda i: i["end"])
            if soon:
                today_n = sum(1 for i in soon if parse_dt(i["end"]).date() == now().date())
                i = soon[0]
                qa.append((f"締切が近い{what}はどれですか？",
                           (f"今日が締切の抽選は{today_n}件です。" if today_n else "") +
                           f"いちばん締切が近いのは{i['store']}の「{i.get('series') or i.get('product')}」で、{_fmt(i['end'])}締切です。"
                           "一覧は締切が近い順に並んでいます。"))
        qa.append(("抽選情報はいつ更新されますか？",
                   f"30分ごとに自動で更新しています（最終更新 {upd_hm}）。新しい抽選は見つかり次第追加し、締切を過ぎた抽選は一覧から外します。"))
        return qa

    def stores_of(sub, k=4):
        out_ = []
        for i in sorted(sub, key=lambda i: i.get("end") or "9999"):
            if i.get("store") and i["store"] not in out_:
                out_.append(i["store"])
        return out_[:k]

    def crumbs(trail):
        """パンくず（画面）と構造化データ。trail: [(名前, パス)]"""
        html = '<nav class="crumbs" aria-label="パンくず">' + " › ".join(
            (f'<a href="/{escape(p)}">{escape(n)}</a>' if k < len(trail) - 1 else f"<span>{escape(n)}</span>")
            for k, (n, p) in enumerate(trail)) + "</nav>"
        ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": k + 1, "name": n, "item": f"{site}/{p}"} for k, (n, p) in enumerate(trail)]}
        return html, ld

    def item_list(sub, title):
        rows = sorted([i for i in sub if parse_dt(i.get("end"))], key=lambda i: i["end"])[:20]
        return {"@context": "https://schema.org", "@type": "ItemList", "name": title, "numberOfItems": len(sub),
                "itemListElement": [{"@type": "ListItem", "position": k + 1,
                                     "name": f"{i['store']} {i.get('series') or i.get('product')}（{_fmt(i['end'])}締切）",
                                     **({"url": i["url"]} if i.get("url") else {})} for k, i in enumerate(rows)]}

    def write(path, lock, meta, subset, trail=None):
        p = out / path / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        meta["canonical"] = f"{site}/{path}" if site else None
        meta["site"], meta["verify"] = site, verify
        meta["prerender"] = prerender(subset)
        ld = [item_list(subset, meta["h1"])]
        if trail:
            meta["crumbs"], bl = crumbs(trail)
            ld.insert(0, bl)
        org = {"@type": "Organization", "@id": f"{site}/#organization", "name": "トレカ抽選ナビ", "url": f"{site}/",
               "logo": {"@type": "ImageObject", "url": f"{site}/apple-touch-icon.png"}}
        if not path:
            ld.insert(0, {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{site}/#website", "name": "トレカ抽選ナビ",
                          "url": f"{site}/", "inLanguage": "ja", "description": meta["desc"], "publisher": org})
        first = min([i.get("found_at") or "" for i in subset if i.get("found_at")] or [updated])
        ld.append({"@context": "https://schema.org", "@type": "WebPage", "name": meta["title"], "headline": meta["h1"],
                   "description": meta["desc"], "url": f"{site}/{path}", "inLanguage": "ja",
                   "datePublished": first, "dateModified": updated, "publisher": org})
        if meta.get("faq"):
            ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in meta["faq"]]})
            meta["faq_html"] = (meta.get("info_html", "") + '<section class="faq" aria-label="よくある質問"><h2>よくある質問</h2>' +
                                "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in meta["faq"]) +
                                "</section>")
        else:
            meta["faq_html"] = meta.get("info_html", "")
        meta["ld"] = ld
        # ページを軽くする：そのページのゲームの抽選だけを埋め込む（トップは最初のゲームだけ。ほかのゲームはタブで移動）
        g0 = lock.get("game") or games[0]
        if not path:  # トップ＝総合（3つのゲームの抽選を全部入れて「すべて」タブで開く）
            data = {**common_data, "lock": lock, "items": items, "gameCounts": game_counts, "allLoaded": True, "defaultGame": "all"}
        elif any(lock.get(k) for k in ("store", "chain", "series", "area", "subset")):
            # お店・チェーン・弾・地域・カレンダーのページは、そのページに出す抽選だけ（ページが数分の1の重さになる）
            data = {**common_data, "lock": lock, "items": list(subset), "gameCounts": game_counts, "subsetOnly": True,
                    "amazonInvites": {g0: (common_data.get("amazonInvites") or {}).get(g0, [])}}
        else:
            data = {**common_data, "lock": lock, "items": [i for i in items if i["game"] == g0], "gameCounts": game_counts,
                    "amazonInvites": {g0: (common_data.get("amazonInvites") or {}).get(g0, [])}}
        if meta.get("upd"):  # ページ上の「更新」を、そのページの中身の更新日時にする（BOX相場＝相場を読んだ日時）
            data = {**data, "updated": meta["upd"][1], "updLabel": meta["upd"][0]}
        p.write_text(page(data, meta), encoding="utf-8")
        last = max([i.get("found_at") or "" for i in subset] + [""]) or updated
        if not meta.get("noindex"):  # 中身のうすいページ（抽選も履歴もない）は検索に出さない・サイトマップにも入れない
            urls.append((f"{site}/{path}", (last or updated)[:10]))

    def prods_of(game):
        cnt = {}
        for i in items:
            if i["game"] == game and i.get("series"):
                cnt[i["series"]] = cnt.get(i["series"], 0) + 1
        rk_ = rk if sample is None else {}
        return [(GAME_SHORT[game], x, (rk_.get(f"{game}|{x}") or {}).get("image"), (rk_.get(f"{game}|{x}") or {}).get("url"), n)
                for x, n in sorted(cnt.items(), key=lambda kv: -kv[1])]

    for g in games:
        gi = [i for i in items if i["game"] == g]
        name, short, slug = s["game_names"][g], GAME_SHORT[g], GAME_SLUG[g]
        def in_ser(i, x):
            return x in (i.get("sers") or [i.get("series")])
        series = sorted({x for i in gi for x in (i.get("sers") or ([i["series"]] if i.get("series") else []))},
                        key=lambda x: -sum(1 for i in gi if in_ser(i, x)))
        areas = sorted({i["area"] for i in gi if i.get("channel") == "store" and i.get("area") in PREF},
                       key=lambda a: list(PREF).index(a))
        online = sum(1 for i in gi if i.get("channel") != "store")
        today = sum(1 for i in gi if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == now().date())
        meta = {"title": f"【{short}】抽選販売・予約の最新情報まとめ【{md}更新】受付中{len(gi)}件" + (f"・本日締切{today}件" if today else "") + "｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{name}（{short}）の抽選販売・予約・再販情報を締切が近い順にまとめ。受付中{len(gi)}件（ネット抽選{online}件・"
                        f"店頭抽選{len(gi) - online}件）。" + (f"「{'」「'.join(series[:3])}」など弾別、" if series else "") +
                        "都道府県別・本人確認や会員の有無で絞り込めます。30分ごとに自動更新。",
                "summary": summary(gi, f"{short}の抽選"),
                "faq": faq_for(gi, f"{short}の抽選"),
                "h1": f"【{short}】抽選販売・予約の最新情報まとめ",
                "lead": f"いま受付中の{name}の抽選を、ネット・店頭（都道府県別）に分けて締切が近い順に並べています。"
                        "30分ごとに自動で更新しています。",
                "links": _menu(items, games, g), "root": "/",
                "supply": _supply_ad(short, name, tag, raff, prices, g)}
        write(f"{slug}/", {"game": g}, dict(meta), gi, [("トップ", ""), (f"{short}の抽選", f"{slug}/")])
        if g == games[0]:
            top = dict(meta, title=f"トレカ抽選ナビ｜ポケカ・ワンピースカードの抽選情報まとめ【{md}更新】締切が近い順",
                       desc=f"【{md}更新】ポケカ（ポケモンカード）・ワンピースカード・フュージョンワールドの抽選販売をネットと店頭（都道府県別）に分けて"
                            f"締切が近い順に掲載。受付中{sum(game_counts.values())}件。本人確認・会員の有無でも絞り込めます。",
                       summary=summary(items, "トレカの抽選"), faq=faq_for(items, "トレカの抽選"),
                       h1="トレカの抽選情報まとめ",
                       lead="ポケカ・ワンピースカード・ドラゴンボール フュージョンワールドの抽選を、ネットと店頭（都道府県別）で"
                            "締切が近い順にまとめています。本人確認・会員カードの有無でも絞り込めます。")
            top["supply"] = _supply_ad(short, name, tag, raff, prices, g)
            write("", {}, top, items)

        al_g = {v: k for k, v in ((s.get("series_aliases") or {}).get(g) or {}).items()}
        # 抽選がまだない弾も、発売前〜発売後90日の弾と相場がある弾はページを作っておく（検索の評価は時間で積み上がるので早めに）
        today_d = now().date().isoformat()
        cut90 = (now().date() - __import__("datetime").timedelta(days=90)).isoformat()
        extra = [x for x, inf in ((_ser_cfg()["info"].get(g) or {}).items())
                 if x not in series and (str(inf.get("release") or "") >= cut90 or f"{g}|{x}" in souba_sm)]
        extra += [k.split("|", 1)[1] for k in souba_sm if k.startswith(g + "|") and k.split("|", 1)[1] not in series + extra]
        for x in series + extra:
            si = [i for i in gi if in_ser(i, x)]
            rk_ = rk if sample is None else {}
            rr = rk_.get(f"{g}|{x}") or next((v for k, v in rk_.items() if k.startswith(g + "|") and
                                               canon_series(g, k.split("|", 1)[1])[:1] == [x] and v.get("image")), {})
            sm = souba_sm.get(f"{g}|{x}")
            aff = souba_block(x, sm, souba_fx) + _product_ad(x, name, rr, tag, raff)
            alias = (s.get("rakuten_aliases") or {}).get(x) or al_g.get(x)
            info = (_ser_cfg()["info"].get(g) or {}).get(x) or {}
            on_ = sum(1 for i in si if i.get("channel") != "store")
            sts = stores_of(si)
            info_rows = [("商品名", f"{name} {info.get('type') or ''}「{x}」".replace("  ", " "))]
            if info.get("release"):
                info_rows.append(("発売日", jdate(info["release"])))
            if info.get("price"):
                info_rows.append(("希望小売価格", info["price"]))
            info_rows += [("受付中の抽選", f"{len(si)}件（ネット{on_}件・店頭{len(si) - on_}件）"), ("情報の最終更新", upd_hm)]
            info_html = ('<section class="sinfo" aria-label="基本情報"><h2>' + escape(x) + 'の基本情報</h2><table>' +
                         "".join(f"<tr><th>{escape(a)}</th><td>{escape(b)}</td></tr>" for a, b in info_rows) + "</table></section>")
            og_rel = "og/" + series_path(g, x).rstrip("/").replace("/", "-") + ".png"
            og_rows = [("いま受付中の抽選", f"{len(si)}件" if si else "これから", True)]
            if info.get("release"):
                og_rows.append(("発売日", jdate(info["release"]), False))
            if sm:
                og_rows.append((f"BOX相場（{_md(sm['date'])}）", _yen(sm["price"]), False))
                if sm.get("teika"):
                    og_rows.append(("定価", _yen(sm["teika"]), False))
            elif info.get("price"):
                og_rows.append(("希望小売価格", info["price"].split("／")[-1].replace("（税込）", ""), False))
            try:
                og_image(out / og_rel, GAME_SHORT[g], "#facc15" if g == "pokemon" else "#f87171" if g == "onepiece" else "#38bdf8",
                         x, og_rows, f"{name}の抽選販売・予約情報")
            except Exception as e:
                print("OGP画像を作れませんでした", x, e)
                og_rel = ""
            write(series_path(g, x), {"game": g, "series": x}, {
                "og_image": f"{site}/{og_rel}" if og_rel else None,
                "title": (f"【{short}】{x}の抽選販売・予約の最新情報まとめ【{md}更新】受付中{len(si)}件｜トレカ抽選ナビ" if si else
                          f"【{short}】{x}の抽選販売・予約情報まとめ" + ("｜発売日・定価" if info.get("release") else "") + "｜トレカ抽選ナビ"),
                "desc": (f"【{md}更新】{name}「{x}」" + (f"（{alias}）" if alias and alias != x else "") +
                         f"の抽選販売・予約・再販情報を30分ごとに更新。" + ("・".join(sts) + "など" if sts else "") +
                         f"受付中{len(si)}件（ネット{on_}件・店頭{len(si) - on_}件）を締切順に一覧。本人確認・会員の有無も分かります。") if si else
                        (f"{name}「{x}」の抽選販売・予約情報をまとめるページです。" +
                         (f"発売日は{jdate(info['release'])}" + (f"、希望小売価格は{info['price']}" if info.get("price") else "") + "。" if info.get("release") else "") +
                         "抽選・予約が始まり次第、お店ごとの締切・応募方法をここに自動で載せます。"),
                "summary": summary(si, f"「{x}」の抽選"),
                "faq": ([(f"「{x}」のBOXの相場はいくらですか？",
                          f"スニダンで{_md(sm['date'])}に成立した1個の取引の平均は{_yen(sm['price'])}です" +
                          (f"（定価{_yen(sm['teika'])}との差 {'+' if sm['price'] >= sm['teika'] else '−'}{abs(sm['price'] - sm['teika']):,}円）" if sm.get("teika") else "") +
                          "。相場は毎日変わります。")] if sm else []) + faq_for(si, f"「{x}」の抽選", info, f"「{x}」"),
                "info_html": info_html if si else "",  # 抽選がまだない弾は基本情報を上に出す
                "h1": f"【{short}】{x}の抽選販売・予約の最新情報まとめ",
                "lead": (f"{name}「{x}」の受付中の抽選は{len(si)}件です。新しい抽選が見つかり次第、自動で追加されます。" if si else
                         f"{name}「{x}」の抽選・予約は、いま受付中のものがありません。抽選が始まり次第、このページに自動で載ります（30分ごとに更新）。"),
                "aff": _ser_areas(g, slug, x, si) + (aff if si else souba_block(x, sm, souba_fx) + info_html + _product_ad(x, name, rr, tag, raff)),
                "links": _menu(items, games, g, "/" + series_path(g, x)),
                "root": "/"}, si, [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (x, series_path(g, x))])

        _hist0 = {} if sample is not None else load_json("store_history.json", {})
        _reg0 = {} if sample is not None else load_json("stores.json", {})
        _cut90 = (now() - __import__("datetime").timedelta(days=90)).isoformat()
        acnt_g = {}
        for i in gi:
            if i.get("channel") == "store" and i.get("area") in PREF:
                acnt_g[i["area"]] = acnt_g.get(i["area"], 0) + 1
        # ポケカ・ワンピースカードは47都道府県すべてにページを作る（0件の県も「近くの県」へ案内する）
        for a in (list(PREF) if g in ("pokemon", "onepiece") else areas):
            ai = [i for i in gi if i.get("channel") == "store" and i.get("area") == a]
            today_a = sum(1 for i in ai if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == now().date())
            new_a = sum(1 for i in ai if parse_dt(i.get("found_at")) and (now() - parse_dt(i["found_at"])).total_seconds() < 86400)
            near_l = [(f"{b}（{acnt_g.get(b, 0)}件）" if acnt_g.get(b) else b, f"/{slug}/area/{PREF[b]}/") for b in NEAR.get(a, [])]
            near_l.sort(key=lambda t: "（" not in t[0])  # 抽選がある県を先に
            # この県で抽選が多いお店（過去90日・お店ページの履歴から）
            rank_a = []
            for sp_, r_ in _reg0.items():
                if r_.get("area") != a:
                    continue
                n_ = sum(1 for v in ((_hist0.get(sp_) or {}).get("items") or {}).values() if v["g"] == g and (v["e"] or v["f"]) >= _cut90[:10])
                if n_:
                    rank_a.append((n_, r_["name"], sp_))
            rank_a.sort(key=lambda t: (-t[0], t[1]))
            area_html = ""
            if rank_a:
                area_html = (f'<section class="hist"><h2>{escape(a)}で{escape(short)}の抽選が多いお店<small>過去90日・トレカ抽選ナビ調べ</small></h2><ul>' +
                             "".join(f'<li><a href="/{sp_}">{escape(nm)}</a><small>{n_}件</small></li>' for n_, nm, sp_ in rank_a[:10]) +
                             f'</ul><p class="note">※{a}のお店で、この90日に見つかった{short}の抽選の数です（{sum(t[0] for t in rank_a)}件）。お店の名前を押すと、そのお店のこれまでの抽選が見られます。</p></section>')
            near_html = _links(f"{a}の近くの県の{short}抽選", near_l)
            write(f"{slug}/area/{PREF[a]}/", {"game": g, "channel": "store", "area": a}, {
                "info_html": area_html + (near_html if ai else ""),
                "title": f"{short} 抽選 {a}｜{a}の店頭抽選" + (f" 受付中{len(ai)}件" if ai else "") + f"【{md}更新】｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{short}（{name}）の抽選を{a}で探すなら。{a}のお店の店頭抽選・Web応募で店頭受け取りの抽選" +
                        (f"{len(ai)}件（今日締切{today_a}件・新着{new_a}件）を締切が近い順にまとめています。" if ai else
                         "をまとめています。いま受付中のものがない時は、近くの県の抽選を案内します。") + "30分ごとに自動更新。",
                "summary": summary(ai, f"{a}の{short}店頭抽選") if ai else "",
                "h1": f"{a}の{short}抽選（店頭抽選）",
                "lead": (f"{a}で受付中の{name}の店頭抽選は{len(ai)}件です（今日締切{today_a}件・24時間以内の新着{new_a}件）。"
                         "整理券・抽選券の配布時間や条件は店舗の告知で必ずご確認ください。" if ai else
                         f"{a}でいま受付中の{name}の店頭抽選はありません。新しい抽選が見つかり次第、このページに自動で載ります。近くの県の抽選も見てみてください。"),
                "aff": "" if ai else (f'<div class="none-area"><b>{escape(a)}でいま受付中の{escape(short)}の店頭抽選はありません。</b>'
                                      f'新しい抽選が見つかり次第、このページに自動で載ります。近くの県の抽選も見てみてください。</div>' + near_html + area_html),
                "links": _menu(items, games, g), "root": "/",
                "noindex": not ai and not rank_a}, ai,  # 受付中も過去90日の抽選もない県は、抽選が出るまで検索に出さない
                [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (f"{a}の店頭抽選", f"{slug}/area/{PREF[a]}/")])

    # --- 条件別のページ（「ポケカ 抽選 本人確認なし」「ポケカ ネット抽選」「ポケカ 抽選 今日締切」で探す人向け）---
    def how_of(i):
        m, tg = i.get("method") or "", " ".join(i.get("tags") or [])
        return ("SNS" if re.search("SNS|X抽選|ポスト|リポスト", m + tg) else "アプリ" if "アプリ" in m
                else "店頭" if re.search("店頭|整理券|抽選券", m + tg) else "Web")
    for g in games:
        gi = [i for i in items if i["game"] == g]
        if not gi:
            continue
        name, short, slug = s["game_names"][g], GAME_SHORT[g], GAME_SLUG[g]
        pages = [
            ("no-id", f"本人確認なしで応募できる{short}抽選", ["f-noid"], [i for i in gi if i.get("id_check") is False], None,
             f"運転免許証などの本人確認書類の提出がいらない{name}の抽選だけを集めました。会員登録だけで応募できるものや、SNSのフォロー＆リポストで応募できるものが中心です。"),
            ("online", f"{short}のネット抽選（Web応募・自宅に発送）", [], [i for i in gi if i.get("channel") != "store"], "online",
             f"お店に行かずにWeb・アプリ・SNSで応募でき、当選すると自宅に発送される{name}の抽選です。遠方の人や店頭に並べない人向けです。"),
            ("today", f"今日締切の{short}抽選", ["f-today"],
             [i for i in gi if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == now().date()], None,
             f"今日が応募締切の{name}の抽選です。締切時刻が近い順に並んでいます。応募し忘れがないか確認してください。"),
        ]
        for key, h1, checks, sub, ch, lead in pages:
            lock = {"game": g, "checks": checks}
            if ch:
                lock["channel"] = ch
            on_ = sum(1 for i in sub if i.get("channel") != "store")
            write(f"{slug}/{key}/", lock, {
                "title": f"【{md}更新】{h1}まとめ｜受付中{len(sub)}件｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{lead[:60]}… 受付中{len(sub)}件（ネット{on_}件・店頭{len(sub) - on_}件）を締切順に掲載。30分ごとに自動更新。",
                "summary": summary(sub, h1), "faq": faq_for(sub, h1), "h1": h1, "lead": lead,
                "links": _menu(items, games, g), "root": "/"}, sub,
                [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (h1, f"{slug}/{key}/")])

    # --- 解説ページ（/guide/）：抽選の種類・当たりやすい抽選の選び方・応募前の準備。数字は今の掲載データから ---
    if items:
        n_all = len(items)
        cnt_how = {}
        for i in items:
            cnt_how[how_of(i)] = cnt_how.get(how_of(i), 0) + 1
        noid = sum(1 for i in items if i.get("id_check") is False)
        card = sum(1 for i in items if i.get("member") == "card")
        nomem = sum(1 for i in items if i.get("member") == "none")
        on_all = sum(1 for i in items if i.get("channel") != "store")
        pct = lambda a: f"{round(a * 100 / n_all)}%"
        gl = lambda g, k: f"/{GAME_SLUG[g]}/{k}/"
        art = f"""<article class="guide">
<p>ポケカ（ポケモンカード）やワンピースカードの新弾BOXは、多くのお店で抽選販売になっています。このページでは、抽選の種類と、少しでも当たりやすい抽選の選び方、応募前にしておくと良い準備をまとめました。数字はトレカ抽選ナビに掲載中の{n_all}件（{upd_hm}時点）から出しています。</p>
<h2>抽選の種類</h2>
<ul>
<li><b>Web応募（{cnt_how.get("Web", 0)}件）</b>：お店のサイトや抽選サービスで応募します。会員登録が必要なことが多いです。</li>
<li><b>SNS応募（{cnt_how.get("SNS", 0)}件）</b>：お店のXをフォローして告知をリポストするなどで応募します。当選はDMで届くことが多いです。</li>
<li><b>アプリ応募（{cnt_how.get("アプリ", 0)}件）</b>：お店のアプリから応募します。アプリの会員証が必要です。</li>
<li><b>店頭応募（{cnt_how.get("店頭", 0)}件）</b>：お店で応募用紙を書く・抽選券を受け取るなどで応募します。</li>
</ul>
<p>受け取り方は「ネット抽選（自宅に発送）」が{on_all}件、「店頭抽選（お店で受け取り）」が{n_all - on_all}件です。</p>
<h2>当たりやすい抽選の選び方</h2>
<p>抽選の倍率は公表されないことがほとんどですが、応募できる人が限られる抽選ほど応募者は少なくなりやすいと考えられます。</p>
<h3>1. 地元のお店の店頭抽選</h3>
<p>店頭で応募・受け取りする抽選は、そのお店に行ける人しか応募しないため、全国から応募が集まるネット抽選より応募者が少なくなりやすいです。<a href="/store/">店舗一覧</a>や、ゲームごとのページの「地域でさがす」から近くのお店を探せます。</p>
<h3>2. 条件がある抽選</h3>
<p>会員カードが必要な抽選（{card}件・{pct(card)}）や、過去の購入実績が条件の抽選は、条件を満たす人だけが応募できます。普段使っているお店の抽選は見逃さないようにしましょう。</p>
<h3>3. 応募期間が短い・告知が少ない抽選</h3>
<p>受付が数時間〜1日だけの抽選や、お店のXだけで告知される抽選は、気づく人が少ないぶん応募者も少なくなりがちです。<a href="{gl("pokemon", "today")}">今日締切のポケカ抽選</a>・<a href="{gl("onepiece", "today")}">今日締切のワンピースカード抽選</a>をこまめに見るのがおすすめです。</p>
<h3>4. たくさん応募する</h3>
<p>1つ1つの当選確率は低いので、応募できる抽選にはできるだけ応募するのがいちばん確実です。一覧の「☐ 応募済」で、応募したものに印を付けておくと管理しやすくなります。</p>
<h2>応募前にしておく準備</h2>
<ul>
<li><b>会員登録</b>：Web抽選の多くは会員登録が必要です。会員登録がいらない抽選は{nomem}件（{pct(nomem)}）です。</li>
<li><b>本人確認書類</b>：当選後の受け取りで本人確認書類が必要な抽選もあります。本人確認がいらない抽選は{noid}件（{pct(noid)}）で、<a href="{gl("pokemon", "no-id")}">ポケカ</a>・<a href="{gl("onepiece", "no-id")}">ワンピースカード</a>のページにまとめています。</li>
<li><b>SNSの設定</b>：SNS応募は、当選のDMを受け取れるようにしておきましょう。</li>
<li><b>支払い方法</b>：当選後の支払い期限が短いことがあります。クレジットカードなどを事前に登録しておくと安心です。</li>
</ul>
<h2>注意すること</h2>
<ul>
<li>1人1回までの抽選に複数のアカウントで応募するなど、お店の規約に反する応募はやめましょう。当選が取り消されることがあります。</li>
<li>転売目的の購入を禁止しているお店が多いです。</li>
<li>応募条件や期間は変わることがあります。応募前に必ずお店の告知を確認してください。</li>
</ul>
<p class="note">ネット抽選だけを見たいときは<a href="{gl("pokemon", "online")}">ポケカのネット抽選</a>・<a href="{gl("onepiece", "online")}">ワンピースカードのネット抽選</a>をどうぞ。</p>
</article>"""
        write("guide/", {"game": games[0]}, {
            "title": "ポケカ・ワンピースカード抽選の当て方｜当たりやすい抽選の選び方と応募のコツ｜トレカ抽選ナビ",
            "desc": f"ポケカ・ワンピースカードの抽選の種類（Web・SNS・アプリ・店頭）、当たりやすい抽選の選び方、応募前の準備をまとめました。掲載中の抽選{n_all}件のデータ付き。",
            "summary": summary([i for i in items if i["game"] == games[0]], "ポケカの抽選"),
            "faq": [("抽選は何件くらいありますか？", f"{upd_hm}時点でトレカ抽選ナビに掲載中の抽選は{n_all}件です（ネット{on_all}件・店頭{n_all - on_all}件）。"),
                    ("当たりやすい抽選はありますか？", "倍率は公表されないことがほとんどですが、地元のお店の店頭抽選や、会員カード・購入実績が条件の抽選など、応募できる人が限られる抽選は応募者が少なくなりやすいと考えられます。"),
                    ("本人確認なしで応募できる抽選はありますか？", f"本人確認がいらない抽選は{noid}件あります。ゲームごとの「本人確認なし」のページにまとめています。")],
            "h1": "ポケカ・ワンピースカード抽選の当て方と応募のコツ",
            "lead": "抽選の種類・当たりやすい抽選の選び方・応募前の準備をまとめた解説ページです。下には今受付中のポケカの抽選を載せています。",
            "aff": art, "links": _menu(items, games, games[0]), "root": "/"}, [i for i in items if i["game"] == games[0]],
            [("トップ", ""), ("抽選の当て方", "guide/")])

    # --- BOXの相場の一覧（/souba/）：スニダンの取引の相場・定価との差・前日比・1週間比・30日のグラフ ---
    if souba_sm:
        have = {(i["game"], x) for i in items for x in (i.get("sers") or ([i["series"]] if i.get("series") else []))}
        secs, faq_s, latest = [], [], ""
        for g, old in [(g, o) for g in games for o in (False, True)]:
            rows = []
            for k, sm in souba_sm.items():
                gg, x = k.split("|", 1)
                if gg != g or bool(souba_raw["items"][k].get("past")) != old:
                    continue
                latest = max(latest, sm["date"])
                name_ = (souba_raw["items"][k].get("name") or x)
                t = sm.get("teika")
                gap = sm["price"] - t if t else None
                d1, c1 = _diff(sm["price"], sm["prev"][1] if sm.get("prev") else None)
                d7, c7 = _diff(sm["price"], sm["week"][1] if sm.get("week") else None)
                link = f'<a href="/{series_path(g, x)}">{escape(name_)}</a>'  # 相場がある弾はどれも弾ページがある
                nlot = sum(1 for i in items if i["game"] == g and x in (i.get("sers") or [i.get("series")]))
                us = ""
                if sm.get("us") and souba_fx:
                    us = f'<small>海外 ${sm["us"][1]:,.2f}（約{_yen(round(sm["us"][1] * souba_fx))}）</small>'
                rows.append((sm["price"], f'<tr><th>{link}' + (f'<small class="lot">抽選 受付中{nlot}件</small>' if nlot else "") + '</th>'
                            f'<td><b>{_yen(sm["price"])}</b><small>{_md(sm["date"])}</small>{us}</td>'
                            f'<td>{_yen(t) if t else "-"}' + (f'<small class="{"up" if gap > 0 else "down"}">{"+" if gap >= 0 else "−"}{abs(gap):,}円</small>' if t else "") + '</td>'
                            f'<td class="{c1}">{d1 or "-"}</td><td class="{c7}">{d7 or "-"}</td>'
                            f'<td>{spark(sm.get("points") or [], 160, 40)}</td></tr>'))
            if rows:
                rows.sort(key=lambda r: -r[0])
                secs.append(f'<section class="sb-list"><h2>{escape(GAME_SHORT[g])}の{"過去の弾の" if old else ""}BOX相場</h2>'
                            + ('<p class="sb-note">発売から時間がたった弾です。相場は1日1回（朝）更新しています。</p>' if old else "")
                            + '<div class="sb-scroll"><table>'
                            '<thead><tr><th>商品</th><th>相場</th><th>定価・差</th><th>前日比</th><th>1週間比</th><th>30日</th></tr></thead><tbody>'
                            + "".join(r[1] for r in rows) + '</tbody></table></div></section>')
        top_ = sorted(souba_sm.items(), key=lambda kv: -(kv[1]["price"] - (kv[1].get("teika") or kv[1]["price"])))[:1]
        if top_:
            k, sm = top_[0]
            faq_s.append(("定価との差がいちばん大きいBOXは？",
                          f"{_md(sm['date'])}の取引では「{souba_raw['items'][k].get('name')}」で、相場{_yen(sm['price'])}・定価{_yen(sm['teika'])}（差 +{sm['price'] - sm['teika']:,}円）です。"))
        faq_s += [("この相場は何の値段ですか？", "スニダン（スニーカーダンク）でその日に成立した「1個」の取引の平均です。お店の買取価格や販売価格ではありません。取引が少ない日は1件の取引で大きく動きます。"),
                  ("海外の相場とは？", "アメリカのTCGplayerで取引されている日本版BOXの相場（ドル）を、その日の為替で円にしたものです。送料・手数料は含みません。"),
                  ("相場はいつ更新されますか？", "毎日、朝と夜21時ごろの2回、スニダンの取引を読み込んで更新しています。朝は前日までの取引、夜はその日の21時ごろまでの取引です（その日の値は夜の時点の平均なので、翌朝に1日分の値に置き換わります）。過去の弾は1日1回（朝）の更新です。")]
        intro = ('<div class="guide"><p>ポケカ・ワンピースカードの未開封BOXの相場を、スニダンで実際に成立した取引の値段で毎日まとめています。'
                 '定価との差も一緒に並べています。商品名を押すと、その弾の抽選の一覧に進めます。</p></div>')
        write("souba/", {"game": games[0]}, {
            "title": f"ポケカ・ワンピースカードBOX相場一覧【{_md(latest) if latest else md}更新】定価との差・前日比・1週間の推移｜トレカ抽選ナビ",
            "desc": f"ポケカ・ワンピースカードの未開封BOXの相場（スニダンの取引価格）を毎日更新。定価との差、前日比、1週間比、30日の値動きのグラフ、海外（TCGplayer）の相場も一覧で比べられます。",
            "summary": "", "faq": faq_s,
            "h1": "ポケカ・ワンピースカード BOX相場一覧",
            "lead": "スニダンで成立した取引の値段（1個の取引のその日の平均）をもとにしたBOXの相場です。下には今受付中のポケカの抽選を載せています。",
            "aff": intro + "".join(secs), "links": _menu(items, games, games[0]), "root": "/",
            "upd": ("相場の更新 ", souba_raw["updated"]) if souba_raw.get("updated") else None},
            [i for i in items if i["game"] == games[0]], [("トップ", ""), ("BOX相場", "souba/")])

    # --- 新しく見つけた弾の一覧（Xの告知の予約作業が読む。検索には載せない）---
    if sample is None:
        ns = []
        for g_, m in (load_json("newsets.json", {}).get("series") or {}).items():
            for nm, v in m.items():
                x = (canon_series(g_, nm) or [nm])[0]
                inf = (_ser_cfg()["info"].get(g_) or {}).get(x) or {}
                ns.append({"game": g_, "game_name": GAME_SHORT.get(g_, g_), "name": x, "url": f"{site}/{series_path(g_, x)}",
                           "release": inf.get("release") or v.get("release"), "price": inf.get("price") or v.get("price"),
                           "type": inf.get("type") or v.get("type"), "first_seen": None if v.get("announce") in ("pending", "posted") else v.get("first_seen"),
                           "auto_announced": v.get("announce") in ("pending", "posted"),  # APIで自動告知する弾はブラウザの予約で二重に出さない
                           "lotteries": sum(1 for i in items if i["game"] == g_ and x in (i.get("sers") or [i.get("series")]))})
        (out / "newsets.json").write_text(json.dumps(sorted(ns, key=lambda r: r.get("first_seen") or ""), ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 今週のまとめ（/weekly/）：その週に見つかった抽選・多かった弾とお店・相場の動き。毎週のページを残す ---
    if sample is None:
        import datetime as _dt
        wk = load_json("weekly.json", {})
        for i in items:
            fd = parse_dt(i.get("found_at"))
            if not fd:
                continue
            fd = fd.astimezone(_dt.timezone(_dt.timedelta(hours=9))).date()
            ws = (fd - _dt.timedelta(days=fd.weekday())).isoformat()
            if ws < (now().date() - _dt.timedelta(days=84)).isoformat():
                continue
            wk.setdefault(ws, {})[i["key"]] = {k: i.get(k) for k in ("game", "store", "series", "channel", "area", "found_at", "chain")}
        wk = {w: v for w, v in wk.items() if w >= (now().date() - _dt.timedelta(days=84)).isoformat()}
        save_json("weekly.json", wk)
        weeks = sorted(wk, reverse=True)

        def wsum(ws):
            rows = list(wk[ws].values())
            we = (_dt.date.fromisoformat(ws) + _dt.timedelta(days=6)).isoformat()
            res = {"week": ws, "week_end": we, "total": len(rows), "games": {}}
            for g_ in games:
                gr = [r for r in rows if r.get("game") == g_]
                if not gr:
                    continue
                cnt = lambda key: sorted(((v, n) for v, n in __import__("collections").Counter(
                    r.get(key) for r in gr if r.get(key)).items()), key=lambda t: -t[1])[:5]
                chains = sorted(__import__("collections").Counter(CHAIN[r["chain"]][1] for r in gr if r.get("chain")).items(), key=lambda t: -t[1])[:5]
                mv = []
                for k, sm_ in souba_sm.items():
                    if not k.startswith(g_ + "|"):
                        continue
                    pts = [(d_, v_) for d_, v_ in (souba_raw["items"][k].get("jp") or {}).items()]
                    a = [v_ for d_, v_ in sorted(pts) if d_ < ws][-1:] or [None]
                    b = [v_ for d_, v_ in sorted(pts) if d_ <= we][-1:] or [None]
                    if a[0] and b[0]:
                        mv.append((souba_raw["items"][k].get("name") or k.split("|")[1], a[0], b[0]))
                mv.sort(key=lambda t: -abs(t[2] - t[1]) / t[1])
                res["games"][g_] = {"name": GAME_SHORT[g_], "total": len(gr),
                                    "online": sum(1 for r in gr if r.get("channel") != "store"),
                                    "series": cnt("series"), "areas": cnt("area"), "chains": chains,
                                    "souba": [{"name": n_, "start": a_, "end": b_} for n_, a_, b_ in mv[:4]]}
            return res

        def whtml(sm_):
            h = [f'<div class="guide"><p>{_md(sm_["week"])}〜{_md(sm_["week_end"])}にトレカ抽選ナビで見つかった抽選は<b>{sm_["total"]}件</b>でした。'
                 '新しく見つかった抽選・多かった弾とお店・BOX相場の動きをまとめています。</p>']
            for g_, v in sm_["games"].items():
                h.append(f'<h2>{escape(v["name"])}：{v["total"]}件（ネット{v["online"]}件・店頭{v["total"] - v["online"]}件）</h2><ul>')
                if v["series"]:
                    h.append("<li><b>多かった弾</b>：" + "、".join(
                        f'<a href="/{series_path(g_, n_)}">{escape(n_)}</a>（{c_}件）' for n_, c_ in v["series"]) + "</li>")
                if v["chains"]:
                    h.append("<li><b>多かったお店（チェーン）</b>：" + "、".join(f"{escape(n_)}（{c_}件）" for n_, c_ in v["chains"]) + "</li>")
                if v["areas"]:
                    h.append("<li><b>店頭抽選が多かった地域</b>：" + "、".join(f"{escape(n_)}（{c_}件）" for n_, c_ in v["areas"]) + "</li>")
                if v["souba"]:
                    h.append("<li><b>BOX相場の動き（週のはじめ→終わり）</b>：" + "、".join(
                        f'{escape(m_["name"])} {_yen(m_["start"])}→{_yen(m_["end"])}（{"+" if m_["end"] >= m_["start"] else "−"}{abs(m_["end"] - m_["start"]) * 100 / m_["start"]:.1f}%）'
                        for m_ in v["souba"]) + "</li>")
                h.append("</ul>")
            if len(weeks) > 1:
                h.append("<h2>これまでの週</h2><ul>" + "".join(
                    (f'<li><a href="/weekly/">' if w == weeks[0] else f'<li><a href="/weekly/{w}/">') + f'{_md(w)}〜{_md((_dt.date.fromisoformat(w) + _dt.timedelta(days=6)).isoformat())}のまとめ</a>（{len(wk[w])}件）</li>'
                    for w in weeks) + "</ul>")
            return "".join(h) + '<p class="note">※件数はトレカ抽選ナビが見つけた抽選の数です。すべての抽選を網羅しているわけではありません。</p></div>'

        for n_i, ws in enumerate(weeks):
            sm_ = wsum(ws)
            label = f"{_md(ws)}〜{_md(sm_['week_end'])}"
            sub = [i for i in items if i["key"] in wk[ws]]
            meta_w = {"title": f"今週のトレカ抽選まとめ（{label}）｜ポケカ・ワンピースカードの抽選{sm_['total']}件｜トレカ抽選ナビ",
                      "desc": f"{label}に見つかったポケカ・ワンピースカードの抽選{sm_['total']}件のまとめ。多かった弾・お店・地域とBOX相場の動き。",
                      "summary": "", "h1": f"今週のトレカ抽選まとめ（{label}）",
                      "lead": "その週に見つかった抽選のまとめです。下には、そのうち今も受付中の抽選を載せています。",
                      "aff": whtml(sm_), "links": _menu(items, games, games[0]), "root": "/"}
            if n_i == 0:
                write("weekly/", {"game": games[0]}, dict(meta_w), sub, [("トップ", ""), ("今週のまとめ", "weekly/")])
                # 来週（次の月曜〜日曜）に締切がある抽選：日曜夜の「来週締切の抽選」ポスト用
                jst_ = _dt.timezone(_dt.timedelta(hours=9))
                d0_ = now().astimezone(jst_).date()
                nm_ = d0_ + _dt.timedelta(days=7 - d0_.weekday())  # 次の月曜
                up = {"from": nm_.isoformat(), "to": (nm_ + _dt.timedelta(days=6)).isoformat(), "games": {}}
                for g_ in games:
                    rows_ = []
                    for i in items:
                        e_ = parse_dt(i.get("end"))
                        if i.get("game") != g_ or not e_ or not (up["from"] <= e_.astimezone(jst_).date().isoformat() <= up["to"]):
                            continue
                        if "amazon" in ((i.get("store") or "") + (i.get("url") or "")).lower():
                            continue
                        reqs = [w for w, ok in (("本人確認", i.get("id_check") is True), ("会員カード", i.get("member") == "card"),
                                                ("会員登録", i.get("member") == "account"),
                                                ("購入履歴", "購入履歴" in (i.get("tags") or []) or bool(re.search(r"購入(履歴|実績|歴)", i.get("conditions") or ""))),
                                                ("レシート", "レシート" in (i.get("tags") or []))) if ok]
                        rows_.append({"store": i.get("store"), "series": i.get("series") or (i.get("product") or "")[:30], "end": i.get("end"),
                                      "channel": "店頭受取" if i.get("channel") == "store" else "通販（発送）",
                                      "area": i.get("area") or "", "needs": reqs})
                    rows_.sort(key=lambda r: r["end"])
                    if rows_:
                        days_ = __import__("collections").Counter(parse_dt(r["end"]).astimezone(jst_).date().isoformat() for r in rows_)
                        up["games"][g_] = {"name": GAME_SHORT[g_], "total": len(rows_),
                                           "store": sum(1 for r in rows_ if r["channel"] == "店頭受取"),
                                           "by_day": dict(sorted(days_.items())), "items": rows_[:12]}
                sm_ = dict(sm_, next_week=up)
                (out / "weekly" / "data.json").write_text(json.dumps(sm_, ensure_ascii=False, indent=1), encoding="utf-8")
            if n_i == 0:
                continue  # いまの週は /weekly/ だけ（同じ内容のページを2つ作らない）
            write(f"weekly/{ws}/", {"game": games[0]}, dict(meta_w, title=meta_w["title"].replace("今週の", ""), h1=meta_w["h1"].replace("今週の", "")), sub,
                  [("トップ", ""), ("今週のまとめ", "weekly/"), (label, f"weekly/{ws}/")])

    # --- 抽選結果（/kekka/）：結果が出た抽選・これから結果が出る抽選を、お店・商品・日付・確かめ方だけにまとめる ---
    # （Xのポストは参考にするだけ。本文の写しや他人のX・Amazonへのリンクは出さない）
    if sample is None:
        import results as _rs
        import datetime as _dtk
        _sreg = load_json("stores.json", {})
        today_k = now().date()
        _cur = []
        for r in _rs.current():  # 弾の名前はサイトと同じ書き方に（Heroines Edition vol.2 → ヒロインズエディション vol.2）
            if r.get("series"):
                r = dict(r, series=(canon_series(r["game"], r["series"]) or [r["series"]])[0])
            _cur.append(r)
        done = [r for r in _cur if r["kind"] == "done"]
        _dk = {(r["game"], normalize(r["store"]), r["date"]) for r in done}
        for r in _rs.from_announce(raw_lots):  # 告知の発表日を過ぎた抽選も「結果が出た」に入れる（Xでは見つからないことが多い）
            if (r["game"], normalize(r["store"]), r["date"]) not in _dk:
                done.append(r)
        done.sort(key=lambda r: (r["date"], r.get("found_at") or ""), reverse=True)
        up = {}
        for r in _cur:
            if r["kind"] == "scheduled" and r["date"] >= today_k.isoformat():
                up[(r["game"], normalize(r["store"]), normalize(r.get("series") or ""), r["date"])] = dict(r)
        for it in raw_lots.values():  # お店の告知に書いてあった発表日（今日〜7日後）
            a_ = _rs.announce_date(it) or ""
            if it.get("status") in ("duplicate", "rejected") or it.get("game") not in GAME_SHORT or not a_:
                continue
            if not (today_k.isoformat() <= a_[:10] <= (today_k + _dtk.timedelta(days=7)).isoformat()):
                continue
            x_ = (canon_series(it["game"], it.get("series")) or [it.get("series")])[0] if it.get("series") else None
            up.setdefault((it["game"], normalize(it["store"]), normalize(x_ or ""), a_[:10]),
                          {"game": it["game"], "store": it["store"], "series": x_, "date": a_[:10], "check": None, "check_url": None})
        done_keys = {(r["game"], normalize(r["store"]), r["date"]) for r in done}
        upl = sorted((v for k, v in up.items() if (k[0], k[1], k[3]) not in done_keys), key=lambda r: (r["date"], r["store"]))

        def _wd(d):
            d = _dtk.date.fromisoformat(d)
            return f"{d.month}/{d.day}({WEEK[d.weekday()]})"

        def _row(r):
            sp = store_path(r["store"])
            name = f'<a href="/{sp}">{escape(r["store"])}</a>' if sp in _sreg else escape(r["store"])
            how = escape(r.get("check") or ("お店のお知らせ（告知の発表予定日）" if r.get("est") else "お店からの当落メール"))
            off = (f'<a href="{escape(r["check_url"])}" target="_blank" rel="noopener nofollow">確認ページ</a>'
                   if r.get("check_url") else "")
            return (f'<li><span class="kk-g kk-{escape(r["game"])}">{escape(GAME_SHORT.get(r["game"], ""))}</span>'
                    f'<b>{name}</b><span class="kk-s">{escape(r.get("series") or "")}</span>'
                    f'<small>確かめ方：{how}{(" ／ " + off) if off else ""}</small></li>')

        h = ['<div class="guide kekka"><p>ポケカ・ワンピースカードの抽選の<b>結果が出たお店</b>と、<b>これから結果が出るお店</b>をまとめています。'
             '当落はお店のメール・アプリ・お知らせで確かめてください。</p>']
        feed = {"updated": now().isoformat(), "results": [], "upcoming": [], "scheduled_today": _rs.scheduled_today()}

        def _group(rows, title, empty):
            h.append(f"<h2>{title}</h2>")
            if not rows:
                h.append(f'<p class="kk-none">{empty}</p>')
                return
            cur = None
            for r in rows:
                if r["date"] != cur:
                    if cur:
                        h.append("</ul>")
                    cur = r["date"]
                    lab = "今日" if cur == today_k.isoformat() else "明日" if cur == (today_k + _dtk.timedelta(days=1)).isoformat() else ""
                    h.append(f'<h3>{_wd(cur)}{"（" + lab + "）" if lab else ""}</h3><ul class="kk-list">')
                h.append(_row(r))
            h.append("</ul>")
        _group(upl[:60], "これから結果が出る抽選（7日以内）", "いまは見つかっていません。")
        _group(done[:60], "結果が出た抽選", "まだ見つかっていません。見つかりしだい、ここに載せます。")
        for r in done[:60]:
            if r.get("est"):  # 発表日から推測した分はXの予約作業には渡さない（本当に出たか分からないため）
                continue
            feed["results"].append({"found_at": r.get("found_at"), "date": r["date"], "game": r["game"],
                                    "game_name": GAME_SHORT.get(r["game"], r["game"]), "store": r["store"],
                                    "series": [r["series"]] if r.get("series") else [], "check": r.get("check"),
                                    "text": f"{r['store']}の抽選結果が出ました（確かめ方：{r.get('check') or 'お店のお知らせ'}）"})
        for r in upl[:60]:
            feed["upcoming"].append({"date": r["date"], "game": r["game"], "game_name": GAME_SHORT.get(r["game"], r["game"]),
                                     "store": r["store"], "series": r.get("series"), "check": r.get("check")})
        h.append('<p class="note">※トレカ抽選ナビが見つけた分だけです。すべての抽選の結果を載せているわけではありません。'
                 '発表日はお店の告知に書かれていた予定で、変わることがあります。</p></div>')
        write("kekka/", {"game": games[0]}, {
            "title": f"ポケカ・ワンピースカードの抽選結果・当選発表まとめ【{md}更新】｜トレカ抽選ナビ",
            "desc": "ポケカ・ワンピースカードの抽選結果（当選発表）が出たお店と、これから結果が出るお店を日付ごとにまとめています。確かめ方（メール・アプリなど）も。",
            "summary": "", "h1": "抽選結果・当選発表のまとめ",
            "lead": "結果が出たお店・これから結果が出るお店を日付ごとにまとめています。下には今受付中の抽選を載せています。",
            "aff": "".join(h), "links": _menu(items, games, games[0]), "root": "/"},
            [i for i in items if i["game"] == games[0]], [("トップ", ""), ("抽選結果", "kekka/")])
        (out / "results.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 発売カレンダー（/calendar/）：最近出た弾〜これから出る弾を月ごとに。発売日・定価・受付中の抽選の数 ---
    if items:
        import datetime as _dtm
        d0 = (now() - _dtm.timedelta(days=60)).date().isoformat()
        d1 = (now() + _dtm.timedelta(days=365)).date().isoformat()
        today_c = now().date().isoformat()
        rows_c = []
        for g in games:
            for x, inf in (_ser_cfg()["info"].get(g) or {}).items():
                r_ = str(inf.get("release") or "")
                if d0 <= r_ <= d1:
                    n_ = sum(1 for i in items if i["game"] == g and x in (i.get("sers") or [i.get("series")]))
                    rows_c.append((r_, g, x, inf, n_))
        rows_c.sort(key=lambda t: (t[0], t[1]))
        if rows_c:
            h = ['<div class="guide cal"><p>ポケカ・ワンピースカードの新弾・新商品の発売日と希望小売価格を、公式サイトの情報からまとめています。'
                 '受付中の抽選の数は30分ごとに更新しています。弾の名前を押すと、その弾の抽選の一覧に進めます。</p>']
            cur_m, faq_c = "", []
            for r_, g, x, inf, n_ in rows_c:
                m_ = r_[:7]
                if m_ != cur_m:
                    if cur_m:
                        h.append("</ul>")
                    h.append(f"<h2>{int(m_[:4])}年{int(m_[5:7])}月</h2><ul class=\"cal-list\">")
                    cur_m = m_
                d_ = _dtm.date.fromisoformat(r_)
                tag = '<span class="cal-new">発売前</span>' if r_ > today_c else ""
                lot = f'<a class="cal-n" href="/{series_path(g, x)}">抽選 受付中{n_}件</a>' if n_ else '<span class="cal-n none">抽選情報待ち</span>'
                h.append(f'<li><time datetime="{r_}">{d_.month}/{d_.day}({WEEK[d_.weekday()]})</time>'
                         f'<span class="badge gm g-{g}">{escape(GAME_SHORT[g])}</span>{tag}'
                         f'<a class="cal-t" href="/{series_path(g, x)}">{escape(x)}</a>'
                         f'<small>{escape(inf.get("type") or "")}' + (f'｜{escape(inf["price"])}' if inf.get("price") else "") + f'</small>{lot}</li>')
            h.append("</ul><p class=\"note\">※発売日・価格は変更になることがあります。最新の情報は公式サイトで確認してください。</p></div>")
            for g in games:
                up_ = [t for t in rows_c if t[1] == g and t[0] > today_c]
                if up_:
                    r_, _, x, inf, n_ = up_[0]
                    d_ = _dtm.date.fromisoformat(r_)
                    faq_c.append((f"次の{GAME_SHORT[g]}の新商品はいつ発売ですか？",
                                  f"次に発売されるのは{d_.year}年{d_.month}月{d_.day}日（{WEEK[d_.weekday()]}）の「{x}」です。"
                                  + (f"希望小売価格は{inf['price']}。" if inf.get("price") else "")
                                  + (f"いま受付中の抽選は{n_}件あります。" if n_ else "抽選・予約の情報が見つかり次第、弾のページに載せます。")))
            up_items = [i for i in items if any(t[0] > today_c and t[1] == i["game"] and t[2] in (i.get("sers") or [i.get("series")]) for t in rows_c)]
            write("calendar/", {"game": games[0], "subset": True}, {
                "title": f"ポケカ・ワンピースカード 発売日カレンダー【{now().year}年{now().month}月更新】新弾の発売日・定価・抽選情報｜トレカ抽選ナビ",
                "desc": "ポケカ・ワンピースカードの新弾・新商品の発売日と希望小売価格を月ごとにまとめたカレンダー。発売前の弾の抽選・予約の受付状況も30分ごとに更新。",
                "summary": "", "faq": faq_c or None, "h1": "ポケカ・ワンピースカード 発売日カレンダー",
                "lead": "新弾の発売日・定価・抽選の受付状況をまとめています。下には発売前の弾の受付中の抽選を載せています。",
                "aff": "".join(h), "links": _menu(items, games, games[0]), "root": "/"}, up_items,
                [("トップ", ""), ("発売日カレンダー", "calendar/")])

    # --- お店ごとのページ（/store/xxxx/）と店舗一覧（/store/）---
    # 受付中の抽選がなくなっても45日間はページを残す（検索から来た人が404にならないように）
    reg = {} if sample is not None else load_json("stores.json", {})
    # 前のアドレス（記号8けた）で残っているお店は、読めるアドレスに移す（転送は _redirects）
    store_moves = {}
    for k in list(reg):
        nk = store_path(reg[k].get("name") or "")
        if k != nk:
            store_moves["/" + k] = "/" + nk
            v = reg.pop(k)
            if nk in reg:
                reg[nk]["last"] = max(reg[nk].get("last") or "", v.get("last") or "")
            else:
                reg[nk] = v
    today_s = now().date().isoformat()
    for i in items:
        if not i.get("spath"):
            continue
        r = reg.setdefault(i["spath"], {})
        r.update(name=i["store"], last=today_s, game=r.get("game") or i["game"])
        if i.get("channel") == "store" and i.get("area"):
            r["area"] = i["area"]
    # お店ごとの抽選の履歴（終わった抽選も1年分残す。「〇〇店 抽選」で探す人に、前回いつ・何の抽選だったかを見せる）
    hist = {} if sample is not None else load_json("store_history.json", {})
    if sample is None:
        cut_h = (now() - __import__("datetime").timedelta(days=365)).isoformat()
        # 結果が出た日：お店・公式の「抽選結果を発表しました」のポストを見つけた日（なければ告知に書いてあった発表日）
        res_day = {}
        import results as _rs2
        _done = {}
        for r_ in _rs2.current():
            if r_["kind"] == "done":
                _done.setdefault(normalize(r_["store"]), []).append(r_["date"])
        for k_, it_ in load_json("lotteries.json", {}).items():
            e_ = str(it_.get("end") or "")[:10]
            ds_ = sorted(d_ for d_ in _done.get(normalize(it_.get("store") or ""), []) if e_ and e_ <= d_ <= (
                __import__("datetime").date.fromisoformat(e_) + __import__("datetime").timedelta(days=21)).isoformat())
            if ds_:
                res_day[k_] = ds_[0]
        for k, it in load_json("lotteries.json", {}).items():
            if it.get("status") in ("duplicate", "rejected") or not it.get("store") or it.get("game") not in GAME_SLUG:
                continue
            sp = store_path(it["store"])
            when = it.get("end") or it.get("found_at") or ""
            if when < cut_h:
                continue
            h = hist.setdefault(sp, {"name": it["store"], "items": {}})
            xs = canon_series(it["game"], it.get("series")) if it.get("series") else []
            if not xs and guess_series(it["game"], it.get("product")):
                xs = [guess_series(it["game"], it.get("product"))]
            old_a = (h["items"].get(k) or {}).get("a")
            h["items"][k] = {"p": "・".join(xs) or (it.get("product") or "")[:60], "g": it["game"],
                             "e": (it.get("end") or "")[:16], "f": (it.get("found_at") or "")[:10],
                             "c": "store" if it.get("channel") == "store" else "online"}
            a_ = res_day.get(k) or _rs2.announce_date(it) or ""
            if a_ or old_a:
                h["items"][k]["a"] = a_ or old_a
        for sp in list(hist):
            its = {k: v for k, v in hist[sp]["items"].items() if (v["e"] or v["f"]) >= cut_h[:10]}
            if not its:
                hist.pop(sp)
                continue
            hist[sp]["items"] = dict(sorted(its.items(), key=lambda kv: kv[1]["e"] or kv[1]["f"], reverse=True)[:40])
        save_json("store_history.json", hist)
        # 履歴のあるお店は、受付中の抽選がなくても半年はページを残す
        for sp, h in hist.items():
            last = max((v["e"] or v["f"])[:10] for v in h["items"].values())
            if sp not in reg and last >= (now() - __import__("datetime").timedelta(days=180)).date().isoformat():
                reg[sp] = {"name": h["name"], "last": min(last, today_s), "game": next(iter(h["items"].values()))["g"], "keep": True}
    reg = {k: v for k, v in reg.items()
           if (now().date() - __import__("datetime").date.fromisoformat(v["last"])).days <= (180 if k in hist else 45)}
    if sample is None:
        save_json("stores.json", reg)
    by_store = {}
    for i in items:
        by_store.setdefault(i.get("spath"), []).append(i)
    for path, r in reg.items():
        si = by_store.get(path, [])
        name = r["name"]
        gs = [g for g in games if any(i["game"] == g for i in si)] or [r.get("game") or games[0]]
        g0 = max(gs, key=lambda g: sum(1 for i in si if i["game"] == g))
        ch = "store" if sum(1 for i in si if i.get("channel") == "store") * 2 > len(si) or (not si and r.get("area")) else "online"
        words = "・".join(GAME_SHORT[g] for g in gs)
        area = r.get("area")
        where = f"（{area}）" if area else ""
        near = [(v["name"], "/" + k) for k, v in reg.items() if area and v.get("area") == area and k != path][:12]
        c = chain_of(name)
        links = _menu(items, games, g0) + (_links(f"{area}のほかのお店", near) if near else "") + (
            _links("同じチェーン", [(f"{CHAIN[c][1]}の抽選をすべて見る", f"/chain/{c}/")]) if c else "")
        rec = ""
        if si:
            lead = rec + f"{name}{where}で受付中の{words}の抽選は{len(si)}件です。締切・応募方法・本人確認や会員の条件をまとめています。"
        else:
            lead = (f"{name}{where}で現在受付中の抽選はありません。最近まで抽選がありました。"
                    "新しい抽選が見つかり次第、このページに自動で追加されます。")
        # これまでの抽選（終わったものだけ・新しい順）
        past, seen_p = [], set()
        for k, v in (hist.get(path) or {}).get("items", {}).items():
            if not (v["e"] and v["e"] < now().isoformat()[:16]) or k in {i.get("key") for i in si}:
                continue
            v = dict(v, p=re.sub(r"(ポケモンカードゲーム|ONE PIECEカードゲーム|ポケモンカード|MEGA|拡張パック|ブースターパック|エクストラブースター|1BOX|[「」『』／/])", " ", v["p"]).strip()
                     if not _ser_cfg()["slug"].get(v["g"], {}).get(v["p"]) else v["p"])
            v["p"] = re.sub(r"\s+", " ", v["p"]).strip() or "抽選"
            sk = (v["g"], v["e"][:10], normalize(v["p"])[:6])
            if sk in seen_p:
                continue  # 同じ日・同じ商品は1行に
            seen_p.add(sk)
            past.append(v)
        hist_html, faq_s = "", []
        ad = ann_days((hist.get(path) or {}).get("items", {}).values())
        ann_li = (f'<p class="ann"><b>結果発表の目安</b>：{escape(ann_text(ad))}</p>' if ad else "")
        if ad:
            faq_s.append((f"{name}の抽選結果はいつ発表されますか？",
                          f"トレカ抽選ナビで確認できた{ad[3]}回分では、{ann_text(ad).split('。')[0]}でした。抽選ごとに違うので、必ず告知を確認してください。"))
        if past:
            def _d(v):
                d = parse_dt(v["e"])
                return f"{d.month}/{d.day}" if d else ""
            rows = "".join(f'<li><time>{_d(v)}締切</time> {escape(GAME_SHORT.get(v["g"], ""))}「{escape(v["p"])}」'
                           f'<small>{"店頭抽選" if v["c"] == "store" else "ネット抽選"}</small></li>' for v in past[:15])
            hist_html = (f'<section class="hist"><h2>{escape(name)}のこれまでの抽選<small>直近{min(len(past), 15)}件</small></h2>'
                         f'{ann_li}<ul>{rows}</ul><p class="note">※トレカ抽選ナビが見つけた抽選です。次の抽選も見つかり次第このページに載せます。</p></section>')
            p0 = past[0]
            faq_s.append((f"{name}の前回の抽選はいつでしたか？",
                          f"トレカ抽選ナビで確認できた直近の抽選は、{_d(p0)}締切の{GAME_SHORT.get(p0['g'], '')}「{p0['p']}」でした。"
                          f"過去1年で{len(past)}件の抽選が見つかっています。"))
            if not si:
                lead += f"前回は{_d(p0)}締切の「{p0['p']}」の抽選でした。"
        elif ann_li:
            hist_html = f'<section class="hist"><h2>{escape(name)}の抽選結果の発表</h2>{ann_li}</section>'
        write(path, {"game": g0, "store": path, "channel": ch}, {
            "title": f"{name}の{words}抽選情報【{md}更新】" + (f"受付中{len(si)}件" if si else "受付状況") + "｜トレカ抽選ナビ",
            "desc": f"【{md}更新】{name}{where}の{words}の抽選販売・予約抽選" + (f"{len(si)}件" if si else "") +
                    "を締切順にまとめ。応募方法（Web・店頭）、受け取り方、本人確認・会員カードの有無もひと目で分かります。",
            "summary": summary(si, f"{name}の抽選"),
            "h1": f"{name}の抽選情報", "lead": lead,
            "aff": (_rec_note(CHAIN[c][1]) if c and CHAIN[c][3] else "") + ("" if si else hist_html),
            "info_html": hist_html if si else "",  # 受付中があれば一覧の下に、なければ上に
            "faq": faq_s or None,
            "links": links, "root": "/",
            "noindex": not si and not hist_html}, si,  # 受付中もこれまでの抽選もないお店は検索に出さない
            [("トップ", ""), ("店舗一覧", "store/"), (name, path)])

    # --- チェーンごとのページ（/chain/xxx/）---
    chain_stores = {}
    for path, r in reg.items():
        c = chain_of(r["name"])
        if c:
            chain_stores.setdefault(c, []).append((path, r))
    chain_links = []
    for slug, cname, pat, big in CHAINS:
        ci = [i for i in items if i.get("chain") == slug]
        if not ci and slug not in chain_stores:
            continue
        gs = [g for g in games if any(i["game"] == g for i in ci)] or [games[0]]
        g0 = max(gs, key=lambda g: sum(1 for i in ci if i["game"] == g))
        ch = "store" if sum(1 for i in ci if i.get("channel") == "store") * 2 > len(ci) else "online"
        words = "・".join(GAME_SHORT[g] for g in gs)
        sts = sorted(chain_stores.get(slug, []), key=lambda pr: (-len(by_store.get(pr[0], [])), pr[1]["name"]))
        rec = ""
        lead = (rec + f"いま受付中の{cname}の{words}の抽選は{len(ci)}件です。"
                if ci else rec + f"{cname}で現在受付中の抽選はありません。新しい抽選が見つかり次第、自動で追加されます。")
        stl = _links(f"{cname}の店舗（{len(sts)}店）", [(r["name"], "/" + p) for p, r in sts[:40]]) if sts else ""
        # チェーンの抽選の傾向（今のデータと最近30日の抽選から。事実だけ）
        craw = [v for v in (raw_lots.values() if sample is None else []) if v.get("status") not in ("duplicate", "rejected")
                and chain_of(v.get("store")) == slug and v.get("game") in GAME_SLUG]
        guide_c = ""
        if len(craw) >= 5:
            def _how(v):
                m_, tg_ = v.get("method") or "", " ".join(v.get("tags") or [])
                return ("SNS（フォロー・リポスト）" if re.search("SNS|X抽選|ポスト|リポスト", m_ + tg_) else "アプリ" if "アプリ" in m_ + tg_
                        else "店頭（抽選券・整理券）" if re.search("店頭|整理券|抽選券", m_ + tg_) else "Web（応募フォーム）")
            hw = {}
            for v in craw:
                hw[_how(v)] = hw.get(_how(v), 0) + 1
            hw_s = "・".join(f"{k}{n}件" for k, n in sorted(hw.items(), key=lambda kv: -kv[1]))
            idn = sum(1 for v in craw if v.get("id_check") is True)
            idk = sum(1 for v in craw if v.get("id_check") is not None)
            mem = sum(1 for v in craw if v.get("member") in ("card", "account"))
            memk = sum(1 for v in craw if v.get("member"))
            durs = [(parse_dt(v["end"]) - parse_dt(v["start"])).total_seconds() / 86400 for v in craw
                    if parse_dt(v.get("start")) and parse_dt(v.get("end")) and parse_dt(v["end"]) > parse_dt(v["start"])]
            sers = {}
            for v in craw:
                x_ = (canon_series(v["game"], v.get("series")) or [None])[0] if v.get("series") else None
                if x_:
                    sers[x_] = sers.get(x_, 0) + 1
            li = [f"<li><b>応募のしかた</b>：{escape(hw_s)}</li>"]
            if idk >= 3:
                li.append(f"<li><b>本人確認</b>：書いてあった{idk}件のうち{idn}件で必要（{idn * 100 // idk}%）</li>")
            if memk >= 3:
                li.append(f"<li><b>会員登録・会員カード</b>：書いてあった{memk}件のうち{mem}件で必要</li>")
            if len(durs) >= 3:
                durs.sort()
                li.append(f"<li><b>受付期間の長さ</b>：多くは{durs[len(durs) // 2]:.0f}日くらい（短いもので{durs[0]:.0f}日、長いもので{durs[-1]:.0f}日）</li>")
            ad_c = ann_days(v for h_ in hist.values() if chain_of(h_.get("name")) == slug for v in h_["items"].values())
            if ad_c:
                li.append(f"<li><b>結果発表の目安</b>：{escape(ann_text(ad_c))}</li>")
            if sers:
                li.append("<li><b>多かった弾</b>：" + "、".join(f"{escape(k)}（{n}件）" for k, n in sorted(sers.items(), key=lambda kv: -kv[1])[:4]) + "</li>")
            guide_c = (f'<section class="hist"><h2>{escape(cname)}の抽選の傾向<small>最近の{len(craw)}件から</small></h2><ul class="cg">' + "".join(li) +
                       '</ul><p class="note">※トレカ抽選ナビが見つけた最近の抽選から集計しています。応募の条件はお店・抽選ごとに違うので、必ず告知を確認してください。</p></section>')
        # チェーン全体のこれまでの抽選（お店ごとの履歴から）
        cpast, cseen = [], set()
        for sp_, h_ in hist.items():
            if chain_of(h_.get("name")) != slug:
                continue
            for v in h_["items"].values():
                if not (v["e"] and v["e"] < now().isoformat()[:16]):
                    continue
                p_ = re.sub(r"\s+", " ", re.sub(r"(ポケモンカードゲーム|ONE PIECEカードゲーム|ポケモンカード|MEGA|拡張パック|ブースターパック|エクストラブースター|1BOX|[「」『』／/])", " ", v["p"])).strip()
                sk = (h_["name"], v["g"], v["e"][:10], normalize(p_)[:6])
                if sk not in cseen:
                    cseen.add(sk)
                    cpast.append((v, h_["name"], sp_))
        cpast.sort(key=lambda t: t[0]["e"], reverse=True)
        chist = ""
        if cpast:
            def _cd(v):
                d = parse_dt(v["e"])
                return f"{d.month}/{d.day}" if d else ""
            def _cp(v):
                p_ = re.sub(r"(ポケモンカードゲーム|ONE PIECEカードゲーム|ポケモンカード|MEGA|拡張パック|ブースターパック|エクストラブースター|1BOX|[「」『』／/])", " ", v["p"])
                return re.sub(r"\s+", " ", p_).strip() or "抽選"
            chist = (f'<section class="hist"><h2>{escape(cname)}のこれまでの抽選<small>直近{min(len(cpast), 20)}件</small></h2><ul>' +
                     "".join(f'<li><time>{_cd(v)}締切</time> <a href="/{sp_}">{escape(n_)}</a>｜{escape(GAME_SHORT.get(v["g"], ""))}「{escape(_cp(v))}」</li>'
                             for v, n_, sp_ in cpast[:20]) +
                     '</ul><p class="note">※トレカ抽選ナビが見つけた抽選です。お店の名前を押すと、そのお店のこれまでの抽選が見られます。</p></section>')
        write(f"chain/{slug}/", {"game": g0, "chain": slug, "channel": ch}, {
            "title": f"{cname}の{words}抽選情報【{md}更新】" + (f"受付中{len(ci)}件・" if ci else "") + "店舗別・締切順｜トレカ抽選ナビ",
            "desc": f"【{md}更新】{cname}の{words}の抽選販売・予約抽選" + (f"{len(ci)}件" if ci else "") +
                    "を店舗別・締切順にまとめ。Web応募・店頭応募、受け取り方法、本人確認・会員の条件もひと目で分かります。",
            "summary": summary(ci, f"{cname}の抽選"), "h1": f"{cname}のポケカ・ワンピースカード抽選情報", "lead": lead,
            "aff": (_rec_note(cname) if big else "") + ("" if ci else guide_c + chist),
            "info_html": (guide_c + chist) if ci else "",
            "links": _menu(items, games, g0) + stl, "root": "/"}, ci,
            [("トップ", ""), ("店舗一覧", "store/"), (cname, f"chain/{slug}/")])
        chain_links.append((slug, cname, big, len(ci)))

    # 店舗一覧（都道府県別。ネット抽選のお店と複数地域のお店は最後）
    groups = {}
    for path, r in reg.items():
        groups.setdefault(r.get("area") or "ネット・複数地域", []).append((path, r))
    order = [p for p in PREF if p in groups] + (["ネット・複数地域"] if "ネット・複数地域" in groups else [])
    secs = []
    for a in order:
        lst = sorted(groups[a], key=lambda pr: (-len(by_store.get(pr[0], [])), pr[1]["name"]))
        chips = "".join(f'<li><a href="/{escape(p)}"{"" if by_store.get(p) else " class=\"zero\""}>{escape(r["name"])}'
                        f'<span>{len(by_store.get(p, []))}</span></a></li>' for p, r in lst)
        secs.append(f'<section><h2>{escape(a)}<small>{len(lst)}店舗</small></h2><ul>{chips}</ul></section>')
    write("store/", {"game": games[0]}, {
        "title": f"店舗一覧｜ポケカ・ワンピースカードの抽選をしているお店【{md}更新】｜トレカ抽選ナビ",
        "desc": f"【{md}更新】ポケカ・ワンピースカードの抽選をしている（最近していた）お店{len(reg)}店舗を都道府県別に一覧にしました。お店を選ぶと、そのお店の受付中の抽選が見られます。",
        "summary": f"最近抽選があったお店は{len(reg)}店舗です。数字は受付中の抽選の件数です。",
        "h1": "抽選をしているお店の一覧",
        "lead": "お店を選ぶと、そのお店で受付中の抽選（締切・応募方法・条件）が見られます。",
        "aff": '<div class="store-dir">' + (
            '<section><h2>チェーンからさがす<small>★＝おすすめ</small></h2><ul>' +
            "".join(f'<li><a href="/chain/{sl}/"{"" if n else " class=\"zero\""}>{"★" if bg else ""}{escape(nm)}<span>{n}</span></a></li>'
                    for sl, nm, bg, n in sorted(chain_links, key=lambda x: (not x[2], -x[3]))) + '</ul></section>'
            if chain_links else "") + f'{"".join(secs)}</div>',
        "links": _menu(items, games, games[0]), "root": "/"}, items,
        [("トップ", ""), ("店舗一覧", "store/")])

    # --- 抽選ごとの個別ページ（/l/xxxx/）---
    # Xに貼ったURLが切れないよう、受付が終わっても keep 日はページを残す（受付終了の表示＋ほかの抽選への案内）
    keep_days = s.get("lottery_page_keep_days", 30)
    lreg = {} if sample is not None else load_json("lottery_pages.json", {})
    active_paths = {}
    for i in items:
        if not i.get("key"):
            continue
        lp = i.get("lpath") or detail.lottery_path(i)
        active_paths[i["key"]] = lp
        lreg[lp] = {"d": detail.snapshot(dict(i, spath=i.get("spath"))), "last": today_s}
    lreg = {k: v for k, v in lreg.items()
            if (now().date() - __import__("datetime").date.fromisoformat(v["last"])).days <= keep_days}
    if sample is None:
        save_json("lottery_pages.json", lreg)
    raw = raw_lots if sample is None else {}
    for lp, r in lreg.items():
        d = r["d"]
        g = d.get("game") if d.get("game") in GAME_SLUG else games[0]
        short = GAME_SHORT[g]
        active = active_paths.get(d.get("key")) == lp
        redirect = None
        if not active:
            tgt = (raw.get(d.get("key")) or {}).get("duplicate_of")
            redirect = active_paths.get(tgt) if tgt else None
        if active and d.get("series"):
            aff = _product_ad(d["series"], s["game_names"][g], (rk if sample is None else {}).get(f"{g}|{d['series']}") or {}, tag, raff)
        else:
            aff = _supply_ad(short, s["game_names"][g], tag, raff, prices, g)
        rel = [(f"{short}の抽選をすべて見る", f"/{GAME_SLUG[g]}/")]
        if d.get("series"):
            rel.insert(0, (f"「{d['series']}」の抽選をすべて見る", "/" + series_path(g, d["series"])))
        if d.get("store"):
            d["spath"] = store_path(d["store"])
        if d.get("spath") and d["spath"] in reg:
            rel.append((f"{d.get('store')}の抽選", "/" + d["spath"]))
        c = chain_of(d.get("store"))
        if c:
            rel.append((f"{CHAIN[c][1]}の抽選", f"/chain/{c}/"))
        if d.get("channel") == "store" and d.get("area") in PREF:
            rel.append((f"{d['area']}の店頭抽選", f"/{GAME_SLUG[g]}/area/{PREF[d['area']]}/"))
        # 今はないページ（抽選がなくなった弾・地域など）へのリンクは出さない
        rel = [(t, u) for t, u in rel if (out / u.strip("/") / "index.html").exists()]
        p = out / lp / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(detail.render(d, site=site, path=lp, verify=verify, now_dt=now(), ended=not active,
                                   redirect=redirect, aff=aff, related=rel, updated=updated), encoding="utf-8")
        if active:
            urls.append((f"{site}/{lp}", (d.get("found_at") or updated)[:10]))

    # 応募したリスト（このブラウザの中だけの記録を一覧にする。検索・サイトマップには載せない）
    (out / "mylist").mkdir(parents=True, exist_ok=True)
    (out / "mylist" / "index.html").write_text(detail.mylist_page(site), encoding="utf-8")

    # 共通の画像（OGP・アイコン）と IndexNow の鍵ファイル
    import shutil
    for f in (ROOT / "src" / "static").glob("*"):
        shutil.copy(f, out / f.name)
    if s.get("indexnow_key"):
        (out / f"{s['indexnow_key']}.txt").write_text(s["indexnow_key"], encoding="utf-8")

    # X手動投稿用の下書きページ（検索に載せない・サイトマップにも入れない）
    from xdraft import build_x_draft
    build_x_draft(out, items, site, updated)

    # 弾ページのアドレスを読める形に変えた・別名のページをまとめたので、前のアドレスから転送する（Cloudflare Pages の _redirects）
    if sample is None:
        olds = {}
        names = {(r.get("game"), r.get("series")) for r in raw_lots.values() if r.get("game") in GAME_SLUG and r.get("series")}
        for g_, m in (s.get("series_aliases") or {}).items():
            names |= {(g_, k) for k in (m or {})} | {(g_, v) for v in (m or {}).values()}
        for g_, raw_x in names:
            for part in [raw_x] + canon_series(g_, raw_x):
                old, new = old_series_path(g_, part), series_path(g_, part)
                if old != new:
                    olds["/" + old] = "/" + new
        for r in reg.values():  # お店の前のアドレス（記号8けた）→ 読めるアドレス
            o, n = old_store_path(r.get("name") or ""), store_path(r.get("name") or "")
            if o != n:
                olds["/" + o] = "/" + n
        olds["/teika/"] = "/"  # 「定価で買えるBOX」のページはやめた
        both = len(olds) * 2 <= 1900  # Cloudflare Pages の転送は2000行まで。多いときは「/」付きだけにする
        (out / "_redirects").write_text("".join(f"{o} {n} 301\n" + (f"{o.rstrip('/')} {n} 301\n" if both else "") for o, n in sorted(olds.items())),
                                        encoding="utf-8")

    if site:
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u, lm in urls)
            + "</urlset>\n", encoding="utf-8")
        (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /x-draft.html\nSitemap: {site}/sitemap.xml\n", encoding="utf-8")

    inject_ga(out, os.environ.get("GA_ID") or s.get("ga_id"))  # Googleアナリティクス（IDがある時だけ）

    if sample is None:
        save_json("site_meta.json", {"digest": digest, "updated": updated})
    (out / ".changed").unlink(missing_ok=True)
    if changed:
        (out / ".changed").write_text(updated, encoding="utf-8")  # ワークフローはこれがある時だけ公開
    return out


GA_SKIP = {"x-draft.html", "site_preview.html"}  # 自分用のページは数えない
GA_NOTE = ("当サイトはアクセス解析にGoogleアナリティクスを使っています。データはCookieを使って匿名で集められ、"
           "個人を特定するものではありません（ブラウザの設定でCookieを無効にできます）。")


def ga_snippet(ga_id):
    return (f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>'
            '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
            f"gtag('js',new Date());gtag('config','{ga_id}');</script>")


def inject_ga(out, ga_id):
    """書き出したすべてのページの <head> に Googleアナリティクスのタグ、フッターに注意書きを入れる"""
    ga_id = (ga_id or "").strip()
    if not re.fullmatch(r"G-[A-Z0-9]{4,}", ga_id):
        return 0
    tag, n = ga_snippet(ga_id), 0
    for p in Path(out).rglob("*.html"):
        if p.name in GA_SKIP:
            continue
        h = p.read_text(encoding="utf-8")
        if "googletagmanager.com/gtag/js" in h or "</head>" not in h:
            continue
        h = h.replace("</head>", tag + "</head>", 1)
        if "</footer>" in h:
            h = h.replace("</footer>", f'<p class="ga-note">{GA_NOTE}</p></footer>', 1)
        p.write_text(h, encoding="utf-8")
        n += 1
    return n


def sample_items():
    P, O, D = "pokemon", "onepiece", "dragonball"
    rows = [
        (P, "ポケモンセンターオンライン", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 5.2, ["本人確認"], "ポケモンセンターオンライン会員・本人確認済みの方", "online", None, 30, True, "account"),
        (P, "ヨドバシ.com", "拡張パック「サンプル弾A」1BOX", "サンプル弾A", 30, ["購入履歴"], "ゴールドポイントカード・プラス会員、過去1年の購入履歴あり", "online", None, 3, False, "account"),
        (P, "セブンネットショッピング", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 52, [], "7iD会員", "online", None, 10, None, "account"),
        (P, "楽天ブックス", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 76, [], "楽天会員", "online", None, 2, False, "account"),
        (P, "Amazon（招待リクエスト）", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 120, [], "Amazonアカウントでリクエスト", "online", None, 60, False, "account"),
        (P, "ジョーシン", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 18, ["アプリ"], "ジョーシンアプリから応募", "online", None, 6, False, "account"),
        (P, "TSUTAYAオンライン", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 9, [], "応募条件なし", "online", None, 40, False, "none"),
        (P, "イオン なんば店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 26, ["整理券", "レシート"], "店頭で抽選券を配布（10:00〜）", "store", "大阪府", 4, False, "none"),
        (P, "カードショップ サンプル梅田店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 7.5, ["SNS応募"], "店舗Xアカウントをフォローしてリプライで応募", "store", "大阪府", 1, None, "none"),
        (P, "トイザらス 堺店", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 44, ["アプリ"], "トイザらスアプリ会員証を提示", "store", "大阪府", 12, False, "card"),
        (P, "ゲームショップ サンプル京都店", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 33, ["本人確認"], "身分証の提示が必要", "store", "京都府", 8, True, "card"),
        (P, "イオンモール 幕張新都心", "拡張パック「サンプル弾A」BOX", "サンプル弾A", 21, ["整理券"], "整理券配布後に抽選", "store", "千葉県", 20, False, "none"),
        (P, "カードショップ サンプル秋葉原店", "強化拡張パック「サンプル弾B」BOX", "サンプル弾B", 3.1, ["SNS応募"], "Xのポストへのリプライで応募", "store", "東京都", 2, None, None),
        (O, "プレミアムバンダイ", "ブースターパック「サンプル航海」BOX", "サンプル航海", 14, [], "バンダイナムコID", "online", None, 5, False, "account"),
        (O, "あみあみ", "ブースターパック「サンプル航海」BOX", "サンプル航海", 48, [], "あみあみ会員", "online", None, 30, False, "account"),
        (O, "カードショップ サンプル心斎橋店", "ブースターパック「サンプル航海」BOX", "サンプル航海", 22, ["SNS応募"], "Xで応募", "store", "大阪府", 3, False, "none"),
        (O, "ゲームショップ サンプル渋谷店", "ブースターパック「サンプル航海」BOX", "サンプル航海", 40, ["整理券"], "店頭で抽選券配布", "store", "東京都", 11, True, "card"),
        (D, "プレミアムバンダイ", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 36, [], "バンダイナムコID", "online", None, 7, False, "account"),
        (D, "駿河屋", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 90, [], "駿河屋会員", "online", None, 26, None, "account"),
        (D, "カードショップ サンプル天神店", "ブースターパック「サンプル覚醒」BOX", "サンプル覚醒", 28, ["整理券"], "店頭で抽選券配布", "store", "福岡県", 5, False, "none"),
    ]
    return [{"key": f"s{n}", "game": g, "store": st, "product": pr, "series": se, "end_h": h, "tags": tags,
             "conditions": cond, "url": "https://example.com/", "channel": ch, "area": area, "found_h": found,
             "id_check": idc, "member": mem}
            for n, (g, st, pr, se, h, tags, cond, ch, area, found, idc, mem) in enumerate(rows)]


if __name__ == "__main__":
    if "--sample" in sys.argv:
        items = sample_items()
        data = {"sample": True, "updated": now().isoformat(),
                "games": [{"id": g, "name": GAME_SHORT[g]} for g in GAME_SHORT], "items": items}
        meta = {"title": "トレカ抽選ナビ", "desc": "試作", "h1": "トレカの抽選・予約情報まとめ",
                "lead": "ポケカ・ワンピースカード・フュージョンワールドの抽選を、ネットと店頭（都道府県別）で締切が近い順にまとめています。",
                "links": _links("弾ごと", [("サンプル弾A", "#"), ("サンプル弾B", "#")]), "root": "#"}
        out = ROOT / "output"
        out.mkdir(exist_ok=True)
        (out / "site_preview.html").write_text(page(data, meta, standalone=False), encoding="utf-8")
        print(out / "site_preview.html")
    else:
        print(build())
