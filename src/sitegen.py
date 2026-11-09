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
          "start", "announce", "buy", "products", "manual", "address")
GAME_SLUG = {"pokemon": "pokeka", "onepiece": "onepiece", "dragonball": "fusionworld"}
GAME_SHORT = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "フュージョンワールド"}
GAME_TAB = {"onepiece": "ワンピース", "dragonball": "ドラゴンボール"}  # 上のタブ・一覧の小さなラベルだけ短く（スマホで横にはみ出さないように）
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
    ("dragonstar", "ドラゴンスター", r"ドラゴンスター|ドラスタ", False),
    ("sanyodo", "三洋堂", r"三洋堂", False),
    ("batoroco", "バトロコ", r"バトロコ", False),
    ("miraiya", "未来屋書店", r"未来屋", False),
    ("wondergoo", "WonderGOO", r"WonderGOO|ワンダーグー", False),
    ("jumpshop", "ジャンプショップ", r"ジャンプショップ|JUMP ?SHOP", False),
    ("dmm", "DMM", r"DMM", False),
    # 11/7 追加：解説ページ（guides.yaml）があり「〇〇 ポケカ 抽選」で探されるお店
    ("heiwado", "平和堂", r"平和堂", False),
    ("itoyokado", "イトーヨーカドー", r"イトーヨーカ[ドド]ー|ヨーカドー", False),
    ("famima", "ファミリーマート（ファミマオンライン）", r"ファミマ|ファミリーマート", False),
    ("lawson", "ローソン・HMV", r"ローソン|HMV", False),
    ("pokemoncardlounge", "ポケモンカードラウンジ", r"ポケモンカードラウンジ|ポケカラウンジ", False),
]


def _rec_note(cname):
    # 11/8 Fable：「★おすすめ」とだけ出る意味のない箱になっていたので、理由を書く
    return '<p class="rec-note"><b>★おすすめ</b>全国の多くの店舗で抽選があり、応募できるチャンスが多いお店です</p>'


def _ymall_box(s):
    """ヤマダモール（バリューコマース）のリンク。ヤマダの抽選ページ・チェーンページだけに出す"""
    v = s.get("yamada_mall_vc") or {}
    if not (v.get("sid") and v.get("pid")):
        return ""
    q = f"sid={v['sid']}&pid={v['pid']}"
    return (f'<aside class="ad ymall"><div class="ad-top"><span>ヤマダの抽選に外れても、ヤマダの通販で探せます</span></div>'
            f'<p style="margin:.4em 0">ヤマダデンキの公式通販「ヤマダモール」でも、ポケカ・ワンピースカードが販売されることがあります。</p>'
            f'<div class="ad-btns"><a class="b-ymd" href="https://ck.jp.ap.valuecommerce.com/servlet/referral?{q}" {_REL}>ヤマダモールで探す</a></div>'
            f'<img src="https://ad.jp.ap.valuecommerce.com/servlet/gifbanner?{q}" height="1" width="1" alt="" style="border:0;position:absolute"></aside>')


import functools as _ft
_CHAIN_RE = None


@_ft.lru_cache(maxsize=None)
def chain_of(store):
    """お店の名前からチェーンを決める。11/8 Fable：かっこ書きは見ない（「オリオンベース（旧TSUTAYA…）」がTSUTAYA扱いになっていた）
    同じ名前を何万回も調べるので結果を覚えておく（ビルドが約7秒短くなる）"""
    global _CHAIN_RE
    if _CHAIN_RE is None:
        _CHAIN_RE = [(slug, re.compile(pat, re.I)) for slug, name, pat, big in CHAINS]
    st_ = re.sub(r"[（(【［\[][^）)】］\]]*[）)】］\]]", "", store or "")
    for slug, rx in _CHAIN_RE:
        if rx.search(st_):
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


_SMALL_KANA = str.maketrans("ァィゥェォヵヶッャュョヮ", "アイウエオカケツヤユヨワ")
_STORE_ALIAS = {}


def store_key(name):
    """同じお店かどうかを決めるための名前（11/8 Fable：「店」の有無・かっこ書き・小さいカナの違いで別ページになっていた）"""
    k = normalize(name or "")
    k = re.sub(r"[（(【［\[][^）)】］\]]*[）)】］\]]", "", k)
    k = re.sub(r"[\s　・/／,、。\-–—~〜!！?？]", "", k).translate(_SMALL_KANA)
    k = re.sub(r"(各店|全店|店舗|店)$", "", k)
    return k


def _alias_of(store):
    """表記ゆれのお店の名前 → 代表の名前（state/store_alias.json。ビルドの最初に作る）"""
    if "m" not in _STORE_ALIAS:
        _STORE_ALIAS["m"] = load_json("store_alias.json", {})
    k = store_key(store)
    return _STORE_ALIAS["m"].get(k) or store


def update_store_alias(names_count):
    """表記ゆれをまとめる代表の名前を決める（一度決めた代表は変えない：アドレスが行ったり来たりしないように）
    names_count: {表記: 抽選の件数}"""
    al = load_json("store_alias.json", {})
    groups = {}
    for nm, n in names_count.items():
        k = store_key(nm)
        if len(k) < 2:
            continue
        groups.setdefault(k, []).append((nm, n))
    for k, lst in groups.items():
        if k in al or len({x for x, _ in lst}) < 2:
            continue
        lst.sort(key=lambda t: (-t[1], bool(re.search(r"[（(【［\[]", t[0])), len(t[0])))
        al[k] = lst[0][0]
    save_json("store_alias.json", al)
    _STORE_ALIAS["m"] = al
    return al


def store_path(store):
    """お店ごとのページ。店名（チェーン名）＋短い記号で読めるアドレスに（同じ店は同じページ）"""
    store = _alias_of(store)
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


GENERIC_SERIES = {"mega", "メガ"}  # 「MEGA」だけでは弾が決まらない（MEGAドリームex・スペシャルデッキセットMEGA など）


def item_series(game, series, product=None):
    """抽選の弾名（サイト用）。弾名が「MEGA」のようにあいまいな時は、商品名から弾を探す"""
    if series and normalize(series) in GENERIC_SERIES and product:
        g = guess_series(game, product)
        if g and normalize(g) not in GENERIC_SERIES:
            return canon_series(game, g) or [g]
    return canon_series(game, series)


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


def _series_stats(game, x, raw, short):
    """弾ページの「数字で見る」：トレカ抽選ナビがこれまでに見つけた、この弾の抽選の数（受付終了も含む）。事実だけ"""
    vs = []
    for v in raw.values():
        if v.get("game") != game or v.get("status") in ("duplicate", "rejected") or not (v.get("series") or v.get("product")):
            continue
        try:
            ss = item_series(game, v.get("series"), v.get("product")) or []
        except Exception:
            ss = []
        if x in ss or (canon_series(game, v.get("series")) or [None])[0] == x:
            vs.append(v)
    if len(vs) < 5:
        return ""
    t0 = now()
    ended = sum(1 for v in vs if parse_dt(v.get("end")) and parse_dt(v["end"]) < t0)
    net = sum(1 for v in vs if v.get("channel") != "store")
    areas = {}
    for v in vs:
        if v.get("channel") == "store" and v.get("area") in PREF:
            areas[v["area"]] = areas.get(v["area"], 0) + 1
    chains = {}
    for v in vs:
        c = chain_of(v.get("store"))
        if c:
            chains[CHAIN[c][1]] = chains.get(CHAIN[c][1], 0) + 1
    idk = [v for v in vs if v.get("id_check") is not None]
    week = sum(1 for v in vs if parse_dt(v.get("found_at")) and (t0 - parse_dt(v["found_at"])).days < 7)
    li = [f"<li><b>これまでに見つけた抽選</b>：{len(vs)}件（受付終了{ended}件）</li>",
          f"<li><b>ネットと店頭</b>：ネット抽選{net}件・店頭抽選{len(vs) - net}件</li>"]
    if week:
        li.append(f"<li><b>この7日に見つけた抽選</b>：{week}件</li>")
    if areas:
        top = sorted(areas.items(), key=lambda kv: -kv[1])[:3]
        li.append(f"<li><b>店頭抽選があった都道府県</b>：{len(areas)}都道府県（多い順に" + "、".join(f"{escape(a)}{n}件" for a, n in top) + "）</li>")
    if chains:
        top = sorted(chains.items(), key=lambda kv: -kv[1])[:3]
        li.append("<li><b>抽選が多かったお店</b>：" + "、".join(f"{escape(a)}（{n}件）" for a, n in top) + "</li>")
    if len(idk) >= 5:
        n_ = sum(1 for v in idk if v.get("id_check") is True)
        li.append(f"<li><b>本人確認が必要だった抽選</b>：書いてあった{len(idk)}件のうち{n_}件（{n_ * 100 // len(idk)}%）</li>")
    return (f'<section class="hist"><h2>数字で見る「{escape(x)}」の抽選<small>トレカ抽選ナビ調べ</small></h2><ul class="cg">' + "".join(li) +
            '</ul><p class="note">※トレカ抽選ナビがこれまでに見つけた抽選の数です（同じ抽選の重複はのぞいています）。1日6回更新します。</p></section>')


_SER_WRITTEN = set()  # このビルドで作った弾ページ（ページがない弾にリンクしないため）


def old_series_path(game, series):
    """前のアドレス（弾名の記号）。転送（_redirects）に使う"""
    return f"{GAME_SLUG[game]}/s-{sha(normalize(series))[:8]}/"


def _sname(st):
    """要約・説明文に出す店名（カッコの中の店舗一覧などを省く。11/8）"""
    return re.sub(r"\s*[（(][^）)]*[）)]", "", st or "").strip() or (st or "")


def _fmt(s):
    dt = parse_dt(s)
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}) {dt:%H:%M}" if dt else "締切 要確認"


def _soon(lst, n=20):
    """締切が近い順に n 件（相場・結果・ガイドなど、一覧が主役でないページの下に載せる分。11/7 ページを軽く・重複を減らす）"""
    return sorted(lst, key=lambda i: i.get("end") or "9999")[:n]


def _pname(i):
    """要約の文に入れる短い商品名（弾の名前。なければ商品名からゲーム名・カッコ書きを落として短く。11/7 ユーザー：長すぎて読みにくい）"""
    if i.get("series"):
        return i["series"]
    p = re.sub(r"ポケモンカードゲーム|ONE PIECEカードゲーム|スカーレット[＆&]バイオレット|[（(][^）)]*[）)]", "", i.get("product") or "")
    p = re.sub(r"[「」『』]", " ", p)
    p = re.sub(r"\s+", " ", p).strip()
    return p[:20] + ("…" if len(p) > 20 else "")


def _recent60(past):
    """60日以内に抽選があったか（店舗ページを検索に残すかの判断。11/7 Fable）"""
    import datetime as _d
    cut = (now() - _d.timedelta(days=60)).isoformat()[:10]
    return any((v.get("e") or "")[:10] >= cut for v in past)


def _cg_title(cname, sh, cig, hg, md, _cd, _cp):
    """チェーン＋ゲームのページのタイトル：店名・ゲーム・件数・更新を前に、受付中の弾名を後ろに（11/7 Fable）"""
    from collections import Counter
    if cig:
        top_x = [x for x, _ in Counter(i["series"] for i in cig if i.get("series")).most_common(2)]
        return (f"{cname}の{sh}抽選 受付中{len(cig)}件【{md}更新】" + ("「" + "」「".join(top_x) + "」ほか" if top_x else "")
                + "｜締切順・応募方法｜トレカ抽選ナビ")
    return (f"{cname}の{sh}抽選｜" + (f"前回{_cd(hg[0][0])}締切「{_cp(hg[0][0])}」・" if hg else "") + "応募のしかた・結果発表の目安｜トレカ抽選ナビ")


def _cg_desc(cname, sh, cig, hg, md, _cd, _cp):
    if cig:
        on = sum(1 for i in cig if i.get("channel") != "store")
        soon = min((i for i in cig if i.get("end")), key=lambda i: i["end"], default=None)
        return (f"【{md}更新】{cname}でいま受付中の{sh}抽選は{len(cig)}件（ネット{on}件・店頭{len(cig) - on}件）。"
                + (f"締切が一番近いのは{soon['store']}「{_pname(soon)}」（{_fmt(soon['end'])}締切）。" if soon else "")
                + "各店の締切・応募方法（Web・アプリ・店頭）・本人確認や会員の有無を一覧にしています。")
    return (f"【{md}更新】{cname}の{sh}抽選の情報。いま受付中の抽選はありません。"
            + (f"前回は{_cd(hg[0][0])}締切の「{_cp(hg[0][0])}」でした。" if hg else "")
            + "これまでの抽選・応募のしかた・結果発表の目安をまとめ、新しい抽選が始まり次第ここに載ります。")


CG_PAGES = set()  # (チェーン, ゲーム)：チェーン＋ゲームのページがあるもの（build の最初に決める）


def _cgp(c, g):
    """チェーンのリンク先：そのゲームのページ（/chain/x/onepiece/）があればそこ。「古本市場 ワンピースカード 抽選」で探す人にぴったりのページへ（11/7 Fable）"""
    return f"/chain/{c}/{GAME_SLUG[g]}/" if (c, g) in CG_PAGES else f"/chain/{c}/"


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
            link = f' <a href="{escape(i["url"])}" target="_blank" rel="nofollow noopener">応募ページ</a>' if i.get("url") else ""
            st_ = escape(where + i['store'])
            if i.get("spath"):  # 検索エンジンが最初に読む一覧から、お店ページへもリンク（11/7）
                st_ = f'<a href="/{escape(i["spath"])}">{st_}</a>'
            pr_ = escape(i.get('product') or '')
            if i.get("lpath"):  # 抽選ごとのページへもリンク（JSを動かさない検索エンジン・AIにも見えるように。11/7 Fable）
                pr_ = f'<a href="/{escape(i["lpath"])}">{pr_}</a>'
            rows.append(f"<li><b>{st_}</b> {pr_} ／ 締切 {when}{link}</li>")
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


def chart(points, h=170, us=None, fx=None):
    """弾ページの相場の大きいグラフ（30日）。横幅いっぱいに伸びる線＋面。高値・安値・日付の目盛り・最新の値段。
    us（[(日付, ドル)]）と fx があれば、海外の相場を円にした線を別の色で重ねる（ポケカ）"""
    if len(points) < 2:
        return ""
    vs = [v for _, v in points]
    idx = {d: i for i, (d, _) in enumerate(points)}
    usv = {d: round(u * fx) for d, u in (us or []) if fx and d in idx}  # 日本の線と同じ日の分だけ
    if len(usv) < 2:
        usv = {}
    lo, hi = min(vs), max(vs)
    slo, shi = min([lo] + list(usv.values())), max([hi] + list(usv.values()))  # 縦の目盛りは両方が入るように
    rng = (shi - slo) or 1
    W, H = 600, 200
    n = len(points)
    X = lambda i: round(i * W / (n - 1), 1)
    Y = lambda v: round(H - 12 - (v - slo) * (H - 24) / rng, 1)
    xs = [X(i) for i in range(n)]
    ys = [Y(v) for v in vs]
    pts = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    up = vs[-1] >= vs[0]
    col = "var(--red)" if up else "#2563eb"
    UC = "#16a34a"  # 海外の線の色（緑）
    grid = "".join(f'<line x1="0" x2="{W}" y1="{y}" y2="{y}" stroke="var(--rule)" stroke-width="1" vector-effect="non-scaling-stroke"/>'
                   for y in (12, H / 2, H - 12))
    us_line = ""
    if usv:
        up_ = " ".join(f"{X(idx[d])},{Y(v)}" for d, v in sorted(usv.items()))
        us_line = (f'<polyline fill="none" stroke="{UC}" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round" '
                   f'vector-effect="non-scaling-stroke" points="{up_}"/>')
    last_pct = (ys[-1] / H) * 100
    ticks = sorted({round(i * (n - 1) / 4) for i in range(5)})  # 日付の目盛り（はじめ〜終わりを5か所）
    ax = "".join(f'<span style="left:{xs[i] / W * 100:.1f}%">{_md(points[i][0])}</span>' for i in ticks)
    data = ";".join(f"{_md(d)},{v}" + (f",{usv[d]}" if d in usv else "") for d, v in points)  # さわると、その日の日付と値段を出す
    leg = (f'<div class="sb-leg"><span><i style="background:{col}"></i>日本（スニダン）</span>'
           f'<span><i class="dash" style="border-color:{UC}"></i>海外（TCGplayer・円にした値）</span></div>' if usv else "")
    return (f'<div class="sb-chart" style="--h:{h}px"><span class="sb-hi">高値 {_yen(hi)}</span><span class="sb-lo">安値 {_yen(lo)}</span>'
            f'<div class="sb-plot" data-p="{data}" data-lo="{slo}" data-hi="{shi}"><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="30日の値動き（{_yen(lo)}〜{_yen(hi)}）">{grid}'
            f'<polygon points="0,{H} {pts} {W},{H}" fill="{col}" opacity=".08"/>{us_line}'
            f'<polyline fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" points="{pts}"/></svg>'
            f'<i class="sb-dot" style="top:{last_pct:.1f}%;background:{col}"></i>'
            f'<span class="sb-last" style="top:{last_pct:.1f}%">{_md(points[-1][0])} {_yen(vs[-1])}</span>'
            f'<i class="sb-vl" hidden></i><i class="sb-pt" hidden style="background:{col}"></i><span class="sb-tip" hidden></span></div>'
            f'<div class="sb-ax">{ax}</div>{leg}</div>')


def _cmp(sm, k):
    """前と比べた差（相場の記録の "prev" / "week" / "month" / "year"）→ (文字, 色のclass)"""
    return _diff(sm["price"], sm[k][1] if sm.get(k) else None)


def _cmp_td(sm, k):
    """一覧の表の比較のマス：上に「−3.5%」、下に小さく「▼2,161円」（横に長くならないように）"""
    lab = "前日比" if k == "prev" else "1週間比"
    b = sm[k][1] if sm.get(k) else None
    if not b:
        return f'<td class="flat" data-l="{lab}">-</td>'
    d = sm["price"] - b
    cls = "up" if d > 0 else "down" if d < 0 else "flat"
    return (f'<td class="{cls}" data-l="{lab}"><b class="pct">{"+" if d > 0 else "−" if d < 0 else "±"}{abs(d) * 100 / b:.1f}%</b>'
            f'<small class="{cls}">{"▲" if d > 0 else "▼" if d < 0 else "±"}{abs(d):,}円</small></td>')


def _ymd(d):
    y, m, dd = d.split("-")
    return f"{y}/{int(m)}/{int(dd)}"


def _md(d):
    y, m, dd = d.split("-")
    return f"{int(m)}/{int(dd)}"


def _sb_buy(g, x, name_, rk, s, tag, raff):
    """BOX相場の一覧の行：楽天・Amazonで探すボタン（アフィリエイト）"""
    q = f'{s["game_names"][g]} {name_}'
    rak = (rk.get(f"{g}|{x}") or {}).get("url") or (_rak(q, raff) if raff else "")
    b = (f'<a class="sb-rk" href="{escape(rak)}" {_REL}>楽天</a>' if rak else "") + (f'<a class="sb-az" href="{escape(_amz(q, tag))}" {_REL}>Amazon</a>' if tag else "")
    return f'<span class="sb-buy">{b}</span>' if b else ""


def _sb_img(img, alt, cls="sb-img"):
    """相場の欄の商品写真（楽天のアフィリエイトリンク付き）。img = {"image":…, "url":…}"""
    if not img or not img.get("image"):
        return ""
    pic = f'<img src="{escape(img["image"])}" alt="{escape(alt)}" loading="lazy">'
    return (f'<a class="{cls}" href="{escape(img["url"])}" {_REL} title="楽天市場で見る">{pic}</a>' if img.get("url")
            else f'<span class="{cls}">{pic}</span>')


REGION_OF = {}
for _r, _ps in (("北海道・東北", "北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県"), ("関東", "東京都 神奈川県 埼玉県 千葉県 茨城県 栃木県 群馬県"),
                 ("中部", "新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県"), ("近畿", "三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県"),
                 ("中国・四国", "鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県"), ("九州・沖縄", "福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県")):
    for _p in _ps.split():
        REGION_OF[_p] = _r


def line_room(area):
    """都道府県 → (地方, オープンチャットのURL)。ルームがなければ None"""
    r = REGION_OF.get(area or "")
    u = ((load_settings().get("line_rooms") or {}).get(r) or "").strip() if r else ""
    return (r, u) if u.startswith("https://") else None


def line_box(area):
    """都道府県ページ・店頭抽選のページ：その地方のオープンチャットの案内"""
    lr = line_room(area)
    if not lr:
        return ""
    r, u = lr
    return (f'<a class="line-room" href="{escape(u)}" target="_blank" rel="noopener"><b>LINE</b>'
            f'<span><strong>{escape(r)}のオプチャに参加する</strong><small>近くの人と「どこで買えた・抽選やってる」をリアルタイムで共有（テスト中）。'
            f'参加後、サブトークルームから【{escape(r)}】のルームを選んでください</small></span></a>')


_SNS_CACHE = {}


def _sns_bar():
    """サイト上部：Xのフォローと、LINEオープンチャット（テスト中）の案内（毎ページ同じなので1回だけ作る。11/8）"""
    if "v" not in _SNS_CACHE:
        _SNS_CACHE["v"] = _sns_bar_make()
    return _SNS_CACHE["v"]


def _sns_bar_make():
    st = load_settings()
    xa, ln = (st.get("x_account") or "").strip().lstrip("@"), (st.get("line_openchat_url") or "").strip()
    b = []
    if xa:
        b.append(f'<a class="sns-x" href="https://x.com/{escape(xa)}" target="_blank" rel="noopener" title="フォローすると、最新情報・新着抽選の速報・締切間近のお知らせが届きます"><b>𝕏</b> 新着速報・締切通知<small>フォローで受け取る</small></a>')
    if ln.startswith("https://") or any((v or "").startswith("https://") for v in (st.get("line_rooms") or {}).values()):
        b.append(f'<a class="sns-line" href="/line/" title="地域ごとのオープンチャットで、近くの人と「どこで買えた・どこで抽選をやっている」をリアルタイムで共有できます（テスト中）"><b>LINE</b> リアルタイム販売情報<small>オプチャ（テスト中）</small></a>')
    return f'<div class="sns">{"".join(b)}</div>' if b else ""


def souba_strip(pairs, link, g=""):
    """一覧ページの上：今日のBOX相場を3つだけ（押すと相場の一覧へ）。pairs = [(弾名, 相場のまとめ)]"""
    if not pairs:
        return ""
    def one(x, sm):
        b = sm["prev"][1] if sm.get("prev") else None
        d = c = ""
        if b:
            v = (sm["price"] - b) * 100 / b
            c = "up" if v > 0 else "down" if v < 0 else "flat"
            d = f'前日比 {"+" if v > 0 else "−" if v < 0 else "±"}{abs(v):.1f}%'
        return (f'<span class="sq-i"><small>{escape(x)}</small><b>{_yen(sm["price"])}</b>'
                + (f'<em class="{c}">{d}</em>' if d else "") + '</span>')
    return (f'<a class="sq" data-g="{g}" href="{link}"><span class="sq-h">📈 今日のBOX相場<i>相場を見る ›</i></span>'
            f'<span class="sq-row">{"".join(one(x, sm) for x, sm in pairs[:3])}</span></a>')


def _sb_tabs(gs):
    """相場の一覧の上：ポケカ／ワンピースの切り替え（全部の相場はページに載せたまま、見せる方だけ切り替える）"""
    if len(gs) < 2:
        return ""
    btn = "".join(f'<button type="button" data-g="{g}" aria-pressed="{str(k == 0).lower()}">{escape(GAME_TAB.get(g, GAME_SHORT[g]))}</button>'
                  for k, g in enumerate(gs))
    return ('<nav class="sb-tabs" id="sb-tabs" aria-label="ゲームを選ぶ">' + btn + '</nav>'
            '<script>document.addEventListener("DOMContentLoaded",function(){var n=document.getElementById("sb-tabs");function show(g){'
            'document.querySelectorAll(".sb-list[data-g]").forEach(function(s){s.hidden=s.dataset.g!==g;});'
            'n.querySelectorAll("button").forEach(function(b){b.setAttribute("aria-pressed",b.dataset.g===g);});}'
            'var h=(location.hash||"").slice(1);show(n.querySelector("button[data-g=\\""+h+"\\"]")?h:n.querySelector("button").dataset.g);'
            'n.addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;show(b.dataset.g);'
            'try{history.replaceState(null,"","#"+b.dataset.g);}catch(x){}});});</script>')


def souba_block(x, sm, fx=None, link=True, us_line=False, img=None):
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
    for k_, lab_, fmt_ in (("month", "1か月前", _md), ("year", "1年前", _ymd)):
        d_, c_ = _cmp(sm, k_)
        rows.append(f'<div><span>{lab_}（{fmt_(sm[k_][0])}）比</span><b class="{c_}">{d_}</b></div>' if d_
                    else f'<div><span>{lab_}比</span><b class="flat">-</b></div>')
    us = ""
    if sm.get("us"):
        ud, uv = sm["us"]
        yen = f"（約{_yen(round(uv * fx))}）" if fx else ""
        us = (f'<p class="sb-us">海外（アメリカ TCGplayer・{_md(ud)}）：${uv:,.2f}{yen}'
              + (f"　前日比 {'+' if uv >= sm['us_prev'][1] else '−'}{abs(uv - sm['us_prev'][1]) * 100 / sm['us_prev'][1]:.1f}%" if sm.get("us_prev") else "")
              + "</p>")
    src = f'https://snkrdunk.com/apparels/{sm["snkr"]}' if sm.get("snkr") else ""
    return (f'<section class="souba" id="souba" aria-label="{escape(x)}の相場"><div class="sb-h"><b>{escape(x)}の相場</b>'
            f'<small>スニダン・{_md(sm["date"])}の取引</small></div>'
            f'<div class="sb-main">{_sb_img(img, x + " BOX", "sb-pic")}<div class="sb-now"><em>{_yen(sm["price"])}</em>'
            + (f'<span>定価より <b>{abs(gap):,}円</b> 高い相場です</span>' if t and gap > 0 else "")
            + f'</div></div>{chart(sm.get("points") or [], us=sm.get("us_points") if us_line else None, fx=fx)}<div class="sb-grid">{"".join(rows)}</div>{us}'
            f'<p class="sb-note">※スニダンでその日に成立した「1個」の取引の平均です（買取価格ではありません）。取引が少ない日は1件で大きく動きます。'
            + (f' <a href="{src}" rel="nofollow noopener" target="_blank">スニダンで見る</a>' if src else "")
            + ("　<a href=\"/souba/\">ほかのBOXの相場</a>" if link else "") + "</p></section>")


def cards_block(x, cards, tag=None):
    """弾ページの「主要カードの相場」：楽天の商品写真・スニダンの状態Aの相場・前日比・1週間比・楽天/メルカリ/スニダンへのリンク
    cards: [(カード設定, 相場の記録, card_summary の結果)]（相場の高い順）"""
    from urllib.parse import quote
    rows = []
    for c, rec, sm in cards:
        if not sm:
            continue
        rk = rec.get("rk") or {}
        d1, c1 = _diff(sm["price"], sm["prev"][1] if sm.get("prev") else None)
        d7, c7 = _diff(sm["price"], sm["week"][1] if sm.get("week") else None)
        q = re.sub(r"\s*[(:（].*$", "", c["label"]).strip() + " " + (re.search(r"([A-Z]{2,4}\d{0,2}-\d{3}|\d{3}/\d{3})", c.get("num") or "") or [None, ""])[1]
        img = (f'<img src="{escape(rk["image"])}" alt="{escape(c["label"])}" loading="lazy" width="96" height="96">' if rk.get("image")
               else '<span class="cd-noimg" aria-hidden="true"></span>')
        links = ((f'<a class="cd-rk" href="{escape(rk["url"])}" target="_blank" rel="nofollow sponsored noopener">{"楽天で探す" if rk.get("search") else "楽天で見る"}</a>' if rk.get("url") else "")
                 + f'<a class="cd-mc" href="https://jp.mercari.com/search?keyword={quote(q.strip())}&amp;afid=1350793153" target="_blank" rel="nofollow sponsored noopener">メルカリで探す</a>'
                 + (f'<a class="cd-az" href="{escape(_amz(q.strip(), tag))}" target="_blank" rel="nofollow sponsored noopener">Amazonで探す</a>' if tag else ""))
        rows.append(f'<li><div class="cd-img">{img}</div><div class="cd-body"><b>{escape(c["label"])}</b>'
                    + (f'<small>{escape(c["num"])}</small>' if c.get("num") else "")
                    + f'<p class="cd-p"><em>{_yen(sm["price"])}</em><small>{_md(sm["date"])}</small></p>'
                    + (f'<p class="cd-psa"><span>PSA10</span><b>{_yen(sm["psa"][1])}</b><small>{_md(sm["psa"][0])}</small></p>' if sm.get("psa") else "")
                    + spark(sm.get("points") or [], w=160, h=40).replace('class="spark"', 'class="spark cd-spark"', 1)  # 30日の小さいグラフ
                    + '<p class="cd-d">' + "".join(f'<span class="{_cmp(sm, k_)[1]}">{lab_} {_cmp(sm, k_)[0] or "-"}</span>'
                                                   for k_, lab_ in (("prev", "前日比"), ("month", "1か月"), ("year", "1年"))) + '</p>'
                    + f'<div class="cd-links">{links}</div></div></li>')
    if not rows:
        return ""
    return (f'<section class="cards" aria-label="{escape(x)}の主要カードの相場"><h2>{escape(x)}の主要カードの相場</h2><ul>{"".join(rows)}</ul>'
            '<p class="sb-note">※スニダンでその日に成立した、状態A（未鑑定の美品）のカード1枚の取引の平均です。PSA10は鑑定品PSA10の、いちばん新しい取引の日の平均（90日以内）です。'
            + ('写真は楽天市場の商品の写真です。' if any((r_.get("rk") or {}).get("image") for _, r_, _s in cards) else "")
            + ('楽天市場・Amazonへのリンクは広告（PR）です。' if tag or any((r_.get("rk") or {}).get("url") for _, r_, _s in cards) else "") + '</p></section>')


_OG_PHOTO = {}


def _og_photo(url):
    """共有画像に入れる商品写真（楽天の写真を大きめで取る。取れなければ None）"""
    if not url:
        return None
    if url in _OG_PHOTO:
        return _OG_PHOTO[url]
    im = None
    try:
        import hashlib
        import io
        import requests
        from PIL import Image
        cdir = Path(".cache/ogphoto")  # 前回の実行で取った写真を使い回す（GitHub Actions の時間を減らす。11/7）
        cf = cdir / (hashlib.md5(url.encode()).hexdigest() + ".jpg")
        if cf.exists():
            im = Image.open(cf).convert("RGB")
        else:
            u = re.sub(r"\?_ex=\d+x\d+", "", url) + "?_ex=500x500" if "thumbnail.image.rakuten" in url else url
            r = requests.get(u, timeout=6, headers={"User-Agent": "tcg-chusen-bot/1.0 (+https://tcg-chusen.com)"})
            if r.ok:
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                cdir.mkdir(parents=True, exist_ok=True)
                im.save(cf, quality=88)
    except Exception:
        im = None
    _OG_PHOTO[url] = im
    return im


def og_image(path, game_label, color, title, rows, sub="", photo=None, brand=None):
    """弾ページの共有画像（XやLINEにリンクを貼ったときに出る画像）。1200×630。
    商品写真があれば右上に入れる（Googleの「おすすめ（Discover）」やXで目に止まりやすくする・11/7）
    brand … (サイト名, ドメイン)。省略＝トレカ抽選ナビ（姉妹サイトは sitegen_game から渡す）"""
    import hashlib
    import shutil
    bname, bdom = brand or ("トレカ抽選ナビ", "tcg-chusen.com")
    ck = Path(".cache/og") / (hashlib.md5(repr(("v2", game_label, color, title, rows, sub, photo) + ((bname, bdom) if brand else ())).encode()).hexdigest() + ".png")
    if ck.exists():  # 中身が前回と同じなら作り直さない（GitHub Actions の時間を減らす。11/7）
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ck, path)
        os.utime(ck)  # 使った印（古いものは消すため）
        return
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
    ph = _og_photo(photo) if photo else None
    tw_max = W - 120
    if ph is not None:
        box = 236
        p2 = ph.copy()
        p2.thumbnail((box - 16, box - 16))
        bx, by = W - 60 - box, 36
        d.rounded_rectangle([bx, by, bx + box, by + box], radius=18, fill="#ffffff")
        im.paste(p2, (bx + (box - p2.width) // 2, by + (box - p2.height) // 2))
        tw_max = bx - 30 - 60
    size = 76
    while size > 34 and d.textlength(title, font=F("Black", size)) > tw_max:
        size -= 4
    d.text((60, 175), title, font=F("Black", size), fill="#ffffff", anchor="lm")
    if sub:
        fs = 32
        while fs > 22 and d.textlength(sub, font=F("Medium", fs)) > tw_max:
            fs -= 2
        d.text((60, 250), sub, font=F("Medium", fs), fill="#cbd5e1", anchor="lm")
    y = 298
    for k, v, hl in rows[:4]:
        d.rounded_rectangle([60, y, W - 60, y + 52], radius=14, fill="#1e293b")
        d.text((88, y + 26), k, font=F("Bold", 27), fill="#94a3b8", anchor="lm")
        d.text((W - 88, y + 26), v, font=F("Black", 32), fill=color if hl else "#f8fafc", anchor="rm")
        y += 62
    d.text((60, H - 26), bname, font=F("Black", 28), fill="#ffffff", anchor="ls")
    d.text((W - 60, H - 26), bdom, font=F("Bold", 26), fill=color, anchor="rs")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)
    try:
        ck.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, ck)
    except Exception:
        pass


def today_image(path, td, dlabel):
    """今日締切の抽選の画像（1200×630）：締切の近い順に7件まで。Xの朝の投稿と /today/ の共有画像に使う（11/7）"""
    from PIL import Image, ImageDraw, ImageFont
    fdir = Path(__file__).with_name("fonts")
    F = lambda w, n: ImageFont.truetype(str(fdir / f"ZenKakuGothicNew-{w}.ttf"), n)
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#0f172a")
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(15 + 15 * t), int(23 + 8 * t), int(42 + 20 * t)))
    d.rectangle([0, 0, 14, H], fill="#c8102e")
    d.text((60, 70), "今日締切", font=F("Black", 64), fill="#ffffff", anchor="lm")
    d.text((60 + d.textlength("今日締切", font=F("Black", 64)) + 16, 78), f"の抽選　{dlabel}", font=F("Bold", 36), fill="#cbd5e1", anchor="lm")
    n = len(td)
    d.rounded_rectangle([W - 60 - 220, 34, W - 60, 106], radius=36, fill="#c8102e")
    d.text((W - 60 - 110, 70), f"{n}件", font=F("Black", 44), fill="#ffffff", anchor="mm")
    col = {"pokemon": "#facc15", "onepiece": "#f87171", "dragonball": "#38bdf8"}
    gs = {"pokemon": "ポケカ", "onepiece": "ワンピ", "dragonball": "DB"}
    y = 132
    show = td[:7]
    if not show:
        d.text((W // 2, 330), "今日締切の抽選はありません", font=F("Bold", 40), fill="#cbd5e1", anchor="mm")
    for i in show:
        e = parse_dt(i["end"])
        d.rounded_rectangle([60, y, W - 60, y + 54], radius=12, fill="#1e293b")
        d.text((84, y + 27), f"{e:%H:%M}", font=F("Black", 30), fill="#ffffff", anchor="lm")
        g = i.get("game")
        tag = gs.get(g, "")
        d.rounded_rectangle([190, y + 12, 190 + 86, y + 42], radius=15, fill=col.get(g, "#94a3b8"))
        d.text((233, y + 27), tag, font=F("Bold", 20), fill="#111827", anchor="mm")
        pr = re.sub(r"ポケモンカードゲーム|ONE PIECEカードゲーム|スカーレット[＆&]バイオレット|[「」『』]", " ", i.get("series") or i.get("product") or "")
        txt = f"{i.get('store') or ''}　{re.sub(r'\s+', ' ', pr).strip()}"
        f = F("Bold", 28)
        while d.textlength(txt, font=f) > W - 60 - 24 - 292 and len(txt) > 4:
            txt = txt[:-2] + "…"
            txt = txt.replace("……", "…")
        d.text((292, y + 27), txt, font=f, fill="#e2e8f0", anchor="lm")
        y += 62
    if n > len(show):
        d.text((W // 2, H - 26), f"＋ほか{n - len(show)}件", font=F("Bold", 28), fill="#cbd5e1", anchor="ms")
    d.text((60, H - 26), "トレカ抽選ナビ", font=F("Black", 28), fill="#ffffff", anchor="ls")
    d.text((W - 60, H - 26), "tcg-chusen.com/today/", font=F("Bold", 26), fill="#facc15", anchor="rs")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def countdown_image(path, d):
    """毎日19:15のX「新弾カウントダウン」の画像（1200×675・白ベース。11/7 Fable案）。公式のロゴ・パッケージ写真は使わない"""
    from PIL import Image, ImageDraw, ImageFont
    fdir = Path(__file__).with_name("fonts")
    F = lambda w, n: ImageFont.truetype(str(fdir / f"ZenKakuGothicNew-{w}.ttf"), n)
    W, H = 1200, 675
    col = "#E8B400" if d["game"] == "pokemon" else "#D7263D"
    im = Image.new("RGB", (W, H), "#ffffff")
    g = ImageDraw.Draw(im)
    g.rectangle([0, 0, 22, H], fill=col)
    g.rounded_rectangle([60, 40, 60 + g.textlength(d["gname"], font=F("Bold", 26)) + 40, 84], radius=22, fill=col)
    g.text((80, 62), d["gname"], font=F("Bold", 26), fill="#111111" if d["game"] == "pokemon" else "#ffffff", anchor="lm")
    title = d["title"]
    fs = 56
    while fs > 32 and g.textlength(title, font=F("Black", fs)) > W - 120:
        fs -= 2
    g.text((60, 140), title, font=F("Black", fs), fill="#111111", anchor="lm")
    g.text((60, 200), d["sub"], font=F("Bold", 30), fill="#6b7280", anchor="lm")
    # 左：大きい日数
    lx, ly = 60, 250
    if d["mode"] == "pre":
        g.text((lx, ly + 40), "発売まで あと", font=F("Bold", 34), fill="#374151", anchor="lm")
        num, unit = str(d["days"]), "日"
        ncol = "#D7263D" if d["days"] <= 3 else "#111111"
    else:
        g.text((lx, ly + 40), "発売から", font=F("Bold", 34), fill="#374151", anchor="lm")
        num, unit = str(d["days"]), "日目"
        ncol = "#111111"
    nf = F("Black", 210 if len(num) <= 2 else 160)
    g.text((lx - 6, ly + 190), num, font=nf, fill=ncol, anchor="lm")
    g.text((lx + g.textlength(num, font=nf) + 10, ly + 268), unit, font=F("Black", 64), fill=ncol, anchor="ls")
    # 右：3つのタイル
    tx, tw, th = 620, 520, 106
    for k, (lab, val, sub, scol) in enumerate(d["tiles"][:3]):
        ty = 245 + k * (th + 14)
        g.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=16, fill="#f3f4f6")
        g.rounded_rectangle([tx, ty, tx + 8, ty + th], radius=4, fill=col)
        g.text((tx + 30, ty + 28), lab, font=F("Bold", 24), fill="#6b7280", anchor="lm")
        vf = 44
        while vf > 28 and g.textlength(val, font=F("Black", vf)) > tw - 60:
            vf -= 2
        g.text((tx + 30, ty + 74), val, font=F("Black", vf), fill="#111111", anchor="lm")
        if sub:
            g.text((tx + tw - 24, ty + 28), sub, font=F("Bold", 24), fill=scol or "#6b7280", anchor="rm")
    g.text((60, H - 34), d["foot"], font=F("Medium", 20), fill="#6b7280", anchor="lm")
    g.text((W - 40, H - 34), "トレカ抽選ナビ  tcg-chusen.com", font=F("Bold", 22), fill="#111111", anchor="rm")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


ASSETS = {}  # {"assets/app.<hash>.css": 中身} 全ページ共通のCSS・JS（11/7 監査：毎ページに100KBインラインで入っていた→別ファイルで長くキャッシュ）


def _externalize(tpl):
    import hashlib
    for pat, ext, tag in ((r"<style>\n(.*?)</style>", "css", '<link rel="stylesheet" href="/assets/app.{h}.css">'),
                          (r"(?<=</script>\n)<script>\n(.*?)</script>", "js", '<script defer src="/assets/app.{h}.js"></script>')):
        m = re.search(pat, tpl, re.S)
        if m:
            h = hashlib.sha1(m.group(1).encode("utf-8")).hexdigest()[:10]
            ASSETS[f"assets/app.{h}.{ext}"] = m.group(1)
            tpl = tpl.replace(m.group(0), tag.format(h=h), 1)
    return tpl


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
    head += meta.get("head_extra") or []  # 11/8：トップの hreflang など、ページ固有の <head> タグ
    for ld in meta.get("ld") or []:
        head.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    body = TEMPLATE.read_text(encoding="utf-8")
    if standalone:
        body = _externalize(body)
    for k, v in {"__TITLE__": escape(meta["title"]), "__DESC__": escape(meta["desc"]),
                 "__HEADMETA__": "\n".join(head), "__ROOT__": escape(base), "__H1__": escape(meta["h1"]) + ('<span class="h1-tag">' + escape(meta["h1_tag"]) + "</span>" if meta.get("h1_tag") else ""),
                 "__LEAD__": escape(meta["lead"]), "__SUMMARY__": escape(meta.get("summary", "")),
                 "__CRUMBS__": meta.get("crumbs", ""),
                 "__LINKS__": meta.get("links", ""), "__AFF__": meta.get("aff", ""), "__TOPSQ__": meta.get("topsq", ""), "__SNS__": _sns_bar(), "__SUPPLY__": meta.get("supply", ""),
                 "__PRERENDER__": meta.get("prerender", ""), "__FAQ__": meta.get("faq_html", ""),
                 # 更新時刻と要約の1〜2文をHTMLに最初から入れる（JSを動かさない検索エンジン・AIにも見えるように。11/7 Fable）
                 "__UPDATED__": escape(f"{meta['upd'][0]}{_fmt(meta['upd'][1])}" if meta.get("upd") else ""),
                 "__SUMSHORT__": escape("。".join((meta.get("summary") or "").split("。")[:2]).strip() + ("。" if meta.get("summary") else "")),
                 "__SUPPLY_BOTTOM__": meta.get("supply_bottom", "")}.items():
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


_LIKELY = {}


_SERHIST = {}


def _serhist_load():
    if not _SERHIST:
        h = load_json("store_history.json", {})
        _SERHIST["_"] = True
        for sp, v in h.items():
            for it in (v.get("items") or {}).values():
                if not it.get("e") or it.get("g") not in GAME_SLUG:
                    continue
                gx = guess_series(it["g"], it.get("p") or "")
                xs = canon_series(it["g"], gx) if gx else []
                for x_ in xs[:1]:
                    _SERHIST.setdefault((it["g"], x_), []).append((it, v.get("name") or "", sp))


def ser_past(game, x, chain=None):
    """この弾の受付が終わった抽選（同じお店・同じ締切日は1つ）。新しい順。chain を渡すとそのチェーンだけ（11/8）"""
    _serhist_load()
    t0 = now().isoformat()[:16]
    seen, out = set(), []
    for t in sorted(_SERHIST.get((game, x), []), key=lambda t: t[0]["e"], reverse=True):
        if t[0]["e"][:16] >= t0 or (chain and chain_of(t[1]) != chain):
            continue
        k = (t[1], t[0]["e"][:10])
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _md_(iso):
    return f"{int(iso[5:7])}/{int(iso[8:10])}" if iso and len(iso) >= 10 else ""


def hist_table(rows, show_store=True, limit=30):
    """これまでの抽選の表（締切・お店・受け取り・結果発表）。11/8 Fable：一覧より表のほうが「いつ・どこで」が読みやすい"""
    if not rows:
        return ""
    th = "<tr><th>締切</th><th>結果</th><th>受取</th>" + ("<th>お店</th>" if show_store else "") + "</tr>"
    tr = "".join(f'<tr><td>{_md_(t[0]["e"])}</td><td>{_md_(t[0].get("a") or "") or "–"}</td><td>{"ネット" if t[0].get("c") != "store" else "店頭"}</td>'
                 + (f'<td><a href="/{escape(t[2])}">{escape(_sname(t[1]))}</a></td>' if show_store else "") + '</tr>' for t in rows[:limit])
    more = f'<p class="note">ほか{len(rows) - limit}件</p>' if len(rows) > limit else ""
    return f'<div class="htw"><table class="htab">{th}{tr}</table></div>{more}'


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


CS_PAGES = {}  # (チェーン, ゲーム, 弾) → アドレス：チェーン×弾のページ（受付中＋これまでが3件以上の組だけ。11/8）


def cs_path(c, g, x):
    return f"chain/{c}/{GAME_SLUG[g]}/{series_path(g, x).rstrip('/').split('/')[-1]}/"


def plan_cs_pages(items):
    """チェーン×弾のページを作る組を先に決める（弾ページからリンクするため）。
    11/8 Fable：「TSUTAYA ハドウシーカー」のような探し方の受け皿。薄いページを量産しないよう、受付中＋これまでの抽選が3件以上の組だけ"""
    import datetime as _d
    CS_PAGES.clear()
    act = {}
    for i in items:
        if i.get("chain") and i["game"] in ("pokemon", "onepiece"):
            for x_ in (i.get("sers") or ([i["series"]] if i.get("series") else [])):
                act[(i["chain"], i["game"], x_)] = act.get((i["chain"], i["game"], x_), 0) + 1
    _serhist_load()
    cut = (now() - _d.timedelta(days=120)).isoformat()[:10]
    pastc = {}
    for key_, lst in _SERHIST.items():
        if not isinstance(key_, tuple) or not isinstance(lst, list) or key_[0] not in ("pokemon", "onepiece"):
            continue
        g_, x_ = key_
        for c in {chain_of(t[1]) for t in lst if t[0]["e"][:10] >= cut} - {None}:
            pastc[(c, g_, x_)] = len(ser_past(g_, x_, c))
    for k in set(act) | set(pastc):
        if act.get(k, 0) + pastc.get(k, 0) >= 3 and k[0] in CHAIN:
            CS_PAGES[k] = cs_path(*k)
    return CS_PAGES


def ser_hist_html(game, x, release=""):
    """弾ページ：受付が終わった抽選の履歴と、発売後の追加抽選・再販の流れ（store_history.json から。11/7）"""
    _serhist_load()
    rows = [t for t in _SERHIST.get((game, x), []) if t[0]["e"][:16] < now().isoformat()[:16]]
    if len(rows) < 2:
        return ""
    seen, uniq = set(), []
    for t in sorted(rows, key=lambda t: t[0]["e"], reverse=True):
        k = (t[1], t[0]["e"][:10])
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    rel = str(release or "")[:10]
    pre = [t for t in uniq if rel and t[0]["e"][:10] < rel]
    post = [t for t in uniq if rel and t[0]["e"][:10] >= rel]
    flow = ""
    if rel:
        # 記録を始める前に発売された弾は「発売前の件数」が少なく見えるので出さない
        rec0 = min((t[0]["e"] for ts in _SERHIST.values() if isinstance(ts, list) for t in ts), default="9")[:10]
        flow = ('<p>' + (f'発売日（{int(rel[5:7])}/{int(rel[8:10])}）より前に締切の抽選が<b>{len(pre)}件</b>、' if rec0 < rel else
                         f'発売日（{int(rel[5:7])}/{int(rel[8:10])}）のあと、トレカ抽選ナビが記録を始めてから') +
                f'発売日以降の<b>追加抽選・再販の抽選が{len(post)}件</b>見つかっています。')
        if post:
            d0 = post[0][0]["e"]
            flow += f'直近の発売後の抽選は{int(d0[5:7])}/{int(d0[8:10])}締切（{escape(post[0][1])}）です。'
        flow += "人気の弾は、発売後もお店ごとに追加の抽選がしばらく続くことがあります。</p>"
    li = "".join(f'<li><time>{int(t[0]["e"][5:7])}/{int(t[0]["e"][8:10])}締切</time> <a href="/{escape(t[2])}">{escape(t[1])}</a>'
                 f'｜{"ネット" if t[0].get("c") != "store" else "店頭"}' + (f'｜結果 {int(t[0]["a"][5:7])}/{int(t[0]["a"][8:10])}' if t[0].get("a") else "")
                 + '</li>' for t in uniq[:40])
    return (f'<section class="hist"><h2>「{escape(x)}」のこれまでの抽選と再販の流れ<small>受付終了 {len(uniq)}件</small></h2>{flow}<ul>{li}</ul>'
            '<p class="note">※トレカ抽選ナビが見つけた抽選です。お店の名前を押すと、そのお店のこれまでの抽選が見られます。</p></section>')


def guide_links_html():
    """/guide/ に出す「お店ごとの応募のしかた」の一覧（config/guides.yaml）"""
    import yaml
    gp = Path(__file__).resolve().parent.parent / "config" / "guides.yaml"
    gl = ((yaml.safe_load(gp.read_text(encoding="utf-8")) or {}).get("guides") or []) if gp.exists() else []
    if not gl:
        return ""
    return ('<h2>お店ごとの応募のしかた・結果の確かめ方</h2><ul>' +
            "".join(f'<li><a href="/guide/{escape(g["slug"])}/">{escape(g.get("short") or g["h1"])}</a></li>' for g in gl) + "</ul>")


def likely_chains_html(game, series):
    """発売前・受付前の弾のページに「抽選をしそうなお店」：過去60日に、同じゲームで抽選が多かったチェーン（お店ページの履歴から）"""
    from datetime import timedelta
    if game not in _LIKELY:
        hist = load_json("store_history.json", {})
        cut = (now() - timedelta(days=60)).date().isoformat()
        cnt = {}
        for v in hist.values():
            c = chain_of(v.get("name"))
            if not c:
                continue
            n = sum(1 for it in (v.get("items") or {}).values() if it.get("g") == game and (it.get("f") or "") >= cut)
            if n:
                cnt[c] = cnt.get(c, 0) + n
        _LIKELY[game] = sorted(cnt, key=lambda c: (-cnt[c], not CHAIN[c][3]))[:12], cnt
    top, cnt = _LIKELY[game]
    if not top:
        return ""
    return (f'<section class="m-sec"><h3>「{escape(series)}」の抽選をしそうなお店<small>過去60日の実績</small></h3>'
            '<p class="note">前の弾で抽選をすることが多かったお店です。お店のページを見ておくと、抽選が始まった時にすぐ分かります。</p>'
            '<div class="m-area">' +
            "".join(f'<a href="{_cgp(c, game)}">{"★" if CHAIN[c][3] else ""}{escape(CHAIN[c][1])}<span>{cnt[c]}件</span></a>' for c in top) +
            '</div></section>')


def _ser_areas(game, slug, series, si):
    """弾のページに「この弾の店頭抽選がある都道府県」へのリンク"""
    cnt = {}
    for i in si:
        if i.get("channel") == "store" and i.get("area") in PREF:
            cnt[i["area"]] = cnt.get(i["area"], 0) + 1
    if not cnt or game not in ("pokemon", "onepiece"):
        return ""
    order = list(PREF)
    # 11/8 Fable：一覧に着くまでが長いので閉じて始める（中のリンクはそのまま）
    return (f'<details class="ser-areas"><summary>「{escape(series)}」の店頭抽選がある都道府県（{len(cnt)}）</summary><nav aria-label="店頭抽選がある都道府県">' +
            "".join(f'<a href="/{slug}/area/{PREF[a]}/">{escape(a)}<span>{n}</span></a>' for a, n in sorted(cnt.items(), key=lambda kv: order.index(kv[0]))) +
            "</nav></details>")


def _ser_chains(game, series, si):
    """弾のページに「この弾の抽選があるチェーン」→ チェーン＋ゲームのページ（「ツタヤ ハドウシーカー」などで探す人向け。11/7 Fable）"""
    from collections import Counter
    cnt = Counter(i["chain"] for i in si if i.get("chain"))
    if not cnt or game not in ("pokemon", "onepiece"):
        return ""
    top = sorted(cnt, key=lambda c: (not CHAIN[c][3], -cnt[c]))[:10]
    return (f'<details class="ser-areas"><summary>「{escape(series)}」の抽選があるお店（{len(top)}）</summary><nav aria-label="抽選があるお店（チェーン）">' +
            "".join(f'<a href="{("/" + CS_PAGES[(c, game, series)]) if (c, game, series) in CS_PAGES else _cgp(c, game)}">{"★" if CHAIN[c][3] else ""}{escape(CHAIN[c][1])}<span>{cnt[c]}</span></a>' for c in top) +
            "</nav></details>")


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
                  "".join(f'<a href="{_cgp(c, g)}">{"★" if CHAIN[c][3] else ""}{escape(CHAIN[c][1])}<span>{ccnt[c]}</span></a>' for c in top) +
                  '</div></section>')
    today_d = now().date().isoformat()
    up = sorted([(inf.get("release"), x) for x, inf in (_ser_cfg()["info"].get(g) or {}).items()
                 if str(inf.get("release") or "") > today_d])
    up_html = ('<section class="m-sec"><h3>発売予定の弾<small>抽選・予約はここに載ります</small></h3><div class="m-area">' +
               "".join(f'<a href="/{series_path(g, x)}">{escape(x)}<span>{int(r[5:7])}/{int(r[8:10])}</span></a>' for r, x in up) +
               '</div></section>') if up else ""
    cond_html = up_html + ('<section class="m-sec"><h3>条件でさがす</h3><div class="m-area">' +
                 (f'<a href="/{slug}/no-id/">本人確認なし</a><a href="/{slug}/online/">ネット抽選</a><a href="/{slug}/today/">今日締切</a>' if gi else "") +
                 '<a href="/today/">今日締切（全タイトル）</a><a href="/guide/">抽選の当て方・コツ</a><a href="/souba/">BOXの相場</a><a href="/weekly/">今週のまとめ</a><a href="/kekka/">抽選結果</a><a href="/tousenritsu/">当選率</a><a href="/calendar/">発売日カレンダー</a><a href="/mylist/">応募したリスト</a></div></section>')
    return (f'<nav class="menu" aria-label="抽選をさがす"><section class="m-sec"><h3>タイトルで選ぶ</h3>'
            f'<div class="m-games">{"".join(cards)}</div></section>{ser_html}{cond_html}{area_html}{store_html}</nav>')


def _amz(q, tag):
    return f"https://www.amazon.co.jp/s?k={quote(q)}&tag={quote(tag)}"


def _rak(q, aff):
    """楽天の検索結果ページへのアフィリエイトリンク（楽天アフィリエイトの公式の形式）"""
    u = f"https://search.rakuten.co.jp/search/mall/{quote(q)}/"
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(u, safe='')}&m={quote(u, safe='')}" if aff else u


def _rakb(q, aff):
    """楽天ブックスの検索結果へのアフィリエイトリンク（ポケカ・ワンピのBOXは楽天ブックスで定価販売・予約になることが多い）"""
    u = f"https://books.rakuten.co.jp/search?sitem={quote(q)}"
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(u, safe='')}&m={quote(u, safe='')}" if aff else u


PR_B = '<span class="ad-pr">PR</span>'
_STOCK = {}


def stock_for(game, x):
    """いま楽天ブックス・Amazon.co.jp本体で買える（招待リクエスト含む）その弾の商品。[(店, 状態, 名前, URL)]、確認した時刻（JST HH:MM）"""
    if not _STOCK:
        d = load_json("stock.json", {})
        _STOCK["_t"] = d.get("fetched") or ""
        for src, lst in (("rakuten", d.get("rakuten") or []), ("amazon", d.get("amazon") or [])):
            for it in lst:
                g_ = it.get("g") if it.get("g") in GAME_SLUG else None
                if not g_:
                    continue
                gx = guess_series(g_, it.get("n") or "")
                for x_ in (canon_series(g_, gx) if gx else [])[:1]:
                    _STOCK.setdefault((g_, x_), []).append((src, it.get("a"), it.get("n") or "", it.get("u") or ""))
    from common import JST
    t = parse_dt(_STOCK.get("_t"))
    hm = (t.astimezone(JST) if t and t.tzinfo else t)
    return _STOCK.get((game, x), []), (f"{hm.month}/{hm.day} {hm:%H:%M}" if hm else "")


def _stock_rows(game, x, aff, pl):
    """「いま買える」の行（在庫を確認できた時だけ。確認した時刻を書く）"""
    lst, when = stock_for(game, x)
    out = []
    for src, a, n, u in lst[:3]:
        if src == "rakuten":
            href = f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(u, safe='')}&m={quote(u, safe='')}" if aff else u
            out.append(("✅ 楽天ブックスで販売中", f"{n}（{when}時点）", href, "楽天ブックスで買う", "rakb"))
        else:
            out.append(("✅ Amazon.co.jp " + ("で販売中" if a == "buy" else "で招待リクエスト受付中"), f"{n}（{when}時点）", u,
                        "Amazonで見る" if a == "buy" else "リクエストする", "amz"))
    return out


def _after_lose_ad(x, name, sm, tag, aff, invite_url=None, game=None):
    """受付が終わった抽選・落選したとき：「まだ買える方法」（11/7 ユーザー心理：落選直後がいちばん買いたい瞬間）。
    在庫はWorkerで確認できた時だけ「販売中（時刻）」と出す。それ以外は断定しない"""
    q = f"{name} {x}"
    rows = _stock_rows(game, x, aff, "after_lose") if game else []
    if invite_url:
        rows.append(("Amazon 招待リクエスト", "無料で申し込んで、招待が届いたら定価で買えます", invite_url, "リクエストする", "amz"))
    rows.append(("楽天ブックス", "売り切れでも、キャンセル分などで在庫が復活することがあります", _rakb(q, aff), "在庫をチェック", "rakb"))
    if tag:
        rows.append(("Amazon", "Amazon.co.jp 本体の販売・招待リクエストが急に始まることがあります", _amz(q, tag), "在庫をチェック", "amz"))
    rows.append(("通販でさがす", (f"いまの相場は {_yen(sm['price'])}（スニダン {_md(sm['date'])}）" if sm else "楽天市場のショップをまとめて検索"),
                 _rak(q, aff), "楽天市場でさがす", "rak"))
    li = "".join(f'<li><div><b>{escape(t)}</b><small>{escape(sub)}</small></div><a class="b-{c}" href="{escape(u)}" {_REL} data-pl="after_lose">{escape(btn)}</a></li>'
                 for t, sub, u, btn, c in rows)
    return (f'<aside class="ad lose"><div class="ad-top"><span>抽選に外れても、まだ買える可能性があります</span>{PR_B}</div>'
            f'<p class="lose-sub">「{escape(x)}」をいま手に入れる方法。<b>在庫はタッチの差で復活することがあるので、こまめにチェックがおすすめです。</b></p><ul class="lose-l">{li}</ul>'
            '<p class="ad-note">楽天・Amazonへのリンクは広告です。在庫・価格はリンク先で確認してください。</p></aside>')


def _price_anchor(x, name, sm, tag, aff, release="", game=None):
    """相場の横に「定価・相場」と、定価で買える店をさがすリンク（価格のものさしを見せる）。いま買える店があれば一番上に"""
    if not sm or not sm.get("teika"):
        return ""
    st_ = _stock_rows(game, x, aff, "souba_anchor") if game else []
    st_html = "".join(f'<a class="b-{c} st" href="{escape(u)}" {_REL} data-pl="stock">{escape(t)}（{escape(sub.split("（")[-1])}</a>' for t, sub, u, b, c in st_)
    q = f"{name} {x}"
    pre = bool(release) and str(release) > now().date().isoformat()
    return (f'<div class="anchor"><div class="an-p"><span>定価 <b>{_yen(sm["teika"])}</b></span><span>相場 <b>{_yen(sm["price"])}</b></span></div>'
            + (f'<div class="an-st">{st_html}</div>' if st_html else
               '<p class="an-re">🔄 売り切れでも、キャンセル分などで<b>在庫がすぐ復活する</b>ことがあります。こまめにチェックしてみてください。</p>') +
            f'<div class="an-b"><a class="b-rak" href="{escape(_rakb(q, aff))}" {_REL} data-pl="souba_anchor">{"定価で予約できるか見る（楽天ブックス）" if pre else "楽天ブックスで在庫・予約をチェック"}</a>'
            + (f'<a class="b-amz" href="{escape(_amz(q, tag))}" {_REL} data-pl="souba_anchor">Amazonで見る</a>' if tag else "") + '</div></div>')


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


def _product_ad(x, name, rr, tag, aff, release=""):
    """弾ページの広告：商品写真＋楽天／Amazonのボタン＋一緒に使うサプライ。発売前は「予約」の言い方にする"""
    if not (tag or aff or rr.get("url")):
        return ""
    import datetime as _d
    days = None
    if release and str(release) > now().date().isoformat():
        try:
            days = (_d.date.fromisoformat(str(release)[:10]) - now().date()).days
        except ValueError:
            days = None
    rak = rr.get("url") or _rak(f"{name} {x}", aff)
    amz = _amz(f"{name} {x}", tag) if tag else ""
    img = (f'<img src="{escape(rr["image"])}" alt="{escape(x)}" loading="lazy">' if rr.get("image")
           else f'<span class="ph">{_icon("ストレージ")}</span>')
    btns = ((f'<a class="b-rak" href="{escape(_rakb(f"{name} {x}", aff))}" {_REL} data-pl="product_ad">楽天ブックスで予約</a>' +
             (f'<a class="b-amz" href="{escape(amz)}" {_REL} data-pl="product_ad">Amazonで予約</a>' if amz else "")) if days is not None else
            (f'<a class="b-rak" href="{escape(rak)}" {_REL} data-pl="product_ad">楽天市場で見る</a>' +
             (f'<a class="b-amz" href="{escape(amz)}" {_REL} data-pl="product_ad">Amazonで見る</a>' if amz else "")))
    sup = "".join(f'<a href="{escape(_amz(f"{name} {k}", tag) if tag else _rak(f"{name} {k}", aff))}" {_REL}>{_icon(k)}<span>{k}</span></a>'
                  for k in ("スリーブ", "ローダー", "デッキケース"))
    top_ = (f"発売まであと{days}日｜定価で予約できる店" if days else "発売日です｜定価で買える店" if days == 0 else "抽選に外れても、通販で探せます")
    return (f'<aside class="ad"><div class="ad-top"><span>{top_}</span>{PR_B}</div>'
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
    return (f'<aside class="ad ad-flow"><div class="ad-top"><span>{escape(title)}</span>{PR_B}</div>'
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
    return (f'<aside class="ad"><div class="ad-top"><span>{escape(short)}のサプライをさがす</span>{PR_B}</div>'
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
    out = {g: sorted(c, key=lambda x: -c[x]) for g, c in cnt.items() if g in s["game_names"]}
    # 相場を載せている弾（抽選がない過去の弾も）も、楽天の写真を探す（相場の一覧・弾ページに写真を出すため）
    for k in (load_json("souba.json", {}).get("items") or {}):
        g, _, x = k.partition("|")
        if g in s["game_names"] and x not in out.setdefault(g, []):
            out[g].append(x)
    return out


def build(settings=None, out_dir=None, sample=None, force=False):
    _SER_WRITTEN.clear()
    s = settings or load_settings()
    site = (s.get("site_public_url") or os.environ.get("SITE_URL") or "").rstrip("/")
    tag = os.environ.get("AMAZON_TAG") or s.get("amazon_tag")
    raff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or s.get("rakuten_affiliate_id") or "").strip()
    out = Path(out_dir or ROOT / "site")
    games = [g for g in s["game_names"]]
    if sample is None:  # 11/8 Fable：お店の表記ゆれ（「店」の有無・かっこ書き）を1つのページにまとめる代表の名前を先に決める
        _cnt = {}
        for h_ in load_json("store_history.json", {}).values():
            if h_.get("name"):
                _cnt[h_["name"]] = _cnt.get(h_["name"], 0) + len(h_.get("items") or {})
        for r_ in load_json("stores.json", {}).values():
            if r_.get("name"):
                _cnt.setdefault(r_["name"], 0)
        update_store_alias(_cnt)

    prices = load_json("rakuten_prices.json", {}) if sample is None else {}  # サプライの楽天最安値
    import souba as souba_mod
    souba_raw = load_json("souba.json", {}) if sample is None else {}
    souba_fx = souba_raw.get("fx")
    souba_sm = {k: souba_mod.summary(v) for k, v in (souba_raw.get("items") or {}).items()}
    souba_sm = {k: v for k, v in souba_sm.items() if v}
    card_raw = load_json("souba_cards.json", {}) if sample is None else {}
    cards_by = {}  # {"game|弾": [(カード設定, 記録, 相場)]}（相場の高い順）
    for k_, cs_ in souba_mod.card_cfg().items():
        lst_ = [(c_, card_raw.get(str(c_["snkr"])) or {}, souba_mod.card_summary(card_raw.get(str(c_["snkr"])) or {})) for c_ in cs_]
        lst_ = sorted([t_ for t_ in lst_ if t_[2]], key=lambda t_: -t_[2]["price"])
        if lst_:
            cards_by[k_] = lst_
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
            # 絞り込み用：LIVE Pocketの抽選・SNS（X・インスタのフォロー/リポスト）で応募する抽選（11/7 ユーザー）
            _src = " ".join(str(i.get(k) or "") for k in ("url", "apply_url", "method", "conditions"))
            if re.search(r"livepocket|ライブポケット|LIVE ?POCKET", _src, re.I):
                row["lp"] = 1
            if "SNS応募" in (i.get("tags") or []) or re.search(r"SNS|Instagram|インスタ|X（旧Twitter）|Twitter|ツイッター|リポスト|リツイート|フォロー.{0,6}(応募|いいね)", str(i.get("method") or "") + str(i.get("conditions") or "")):
                row["sns"] = 1
            row["image"] = row.get("image") or images.get(i.get("series") or "")
            row["url"] = own_amazon_url(row.get("url"), row.get("product") or row.get("series") or "", tag)
            if tag and re.search(r"amazon|アマゾン", row.get("store") or "", re.I) and "amazon." not in (row.get("url") or ""):
                row["url"] = _amz(row.get("series") or row.get("product") or "", tag)  # XのURL（t.co）などは自分のタグ付きの検索に
            _cs = item_series(i.get("game"), i.get("series"), i.get("product"))  # 弾名はサイトでそろえた名前で（表記ゆれの別の写真を使わない）
            r = (rk.get(f"{i.get('game')}|{_cs[0]}") if _cs else None) or rk.get(f"{i.get('game')}|{i.get('series')}") or {}
            if not row["image"] and r.get("image"):
                row["image"], row["img_url"] = r["image"], r.get("url")
            # 商品名からも画像を探す（弾名が空の抽選・複数の商品をまとめた抽選）
            found = match_images(i.get("game"), [i.get("series"), i.get("product")] + list(i.get("products") or []),
                                 rk, images, s.get("image_aliases"), i.get("series"))
            if found:
                row["image"], row["img_url"] = found[0]
                if len(found) > 1:
                    row["images"] = [{"src": a, "url": b} for a, b in found[:4]]
            sers = item_series(i.get("game"), i.get("series"), i.get("product"))  # 別名をまとめる・「A / B」は両方の弾に出す
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
    digest = sha(digest + "".join(sorted(f.name + sha(f.read_bytes().decode("latin-1")) for f in (ROOT / "src" / "static").glob("*"))))  # 共通のファイル（規約・確認用ファイルなど）を変えたら公開し直す
    digest = sha(digest + str(load_json("souba.json", {}).get("updated")) + str(load_json("souba.json", {}).get("cards_updated")))  # BOX相場を読み直したら（朝・夜21時ごろ）公開し直す  # 話題ネタが更新されたら下書きページも出し直す
    digest = sha(digest + now().date().isoformat())  # 日付が変わったら作り直す（今日締切のページ・朝の投稿文のため。11/7）
    changed = meta_state.get("digest") != digest
    force = force or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"  # 手動で実行した時はいつも作り直して公開
    if not changed and not force and sample is None and out_dir is None:
        # 中身が前回と同じ → ページを作り直さない（公開もしない。実行時間を短くするため）
        (out / ".changed").unlink(missing_ok=True)
        print("サイト: 変化なしなので作り直さない")
        return out
    updated = now().isoformat() if changed or not meta_state.get("updated") else meta_state["updated"]

    common_data = {"sample": False, "updated": updated,
                   "games": [{"id": g, "name": GAME_SHORT[g], "tab": GAME_TAB.get(g, GAME_SHORT[g])} for g in games],
                   "gameUrls": {"all": "/", **{g: f"/{GAME_SLUG[g]}/" for g in games}}, "items": items,
                   "gameNames": {g: s["game_names"][g] for g in games},
                   "chains": {c[0]: [c[1], bool(c[3])] for c in CHAINS}, "amazonTag": tag or "", "rakAff": raff or "", "amazonInvites": amazon_invites(items, tag) if tag else {},
                   "souba": {k: [v.get("teika"), v["price"]] for k, v in souba_sm.items() if v.get("price")}}
    urls = []
    # 11/7 監査：中身が本当に変わった日を lastmod・dateModified にする（毎回「今日」だとGoogleがlastmodを信用しなくなる）
    pmod = load_json("page_lastmod.json", {}) if sample is None else {}  # {path: [中身の指紋, 変わった日, 最初の日]}
    today_iso = now().date().isoformat()
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
            txt += f"締切が一番近いのは{_sname(i['store'])}の「{_pname(i)}」（{_fmt(i['end'])}締切）。"
        cnt = {}
        for i in sub:
            if i.get("channel") == "store" and i.get("area"):
                cnt[i["area"]] = cnt.get(i["area"], 0) + 1
        top3 = sorted(cnt, key=lambda a: -cnt[a])[:3]
        if top3:
            txt += "店頭抽選が多い地域は" + "・".join(f"{a}（{cnt[a]}件）" for a in top3) + "です。"
        return txt

    upd_hm = f"{upd.month}/{upd.day} {upd:%H:%M}"
    try:  # 共有画像の使い回し用の置き場から、10日使っていないものを消す
        import time as _t
        for _f in list(Path(".cache/og").glob("*.png")) + list(Path(".cache/ogphoto").glob("*.jpg")):
            if _t.time() - _f.stat().st_mtime > 10 * 86400:
                _f.unlink()
    except Exception:
        pass
    # チェーン＋ゲームのページができる組み合わせ（受付中がある・これまでに抽選があった）→ リンクをそこへ集める（11/7 Fable）
    CG_PAGES.clear()
    for i in items:
        if i.get("chain") and i.get("game") in ("pokemon", "onepiece"):
            CG_PAGES.add((i["chain"], i["game"]))
    if sample is None:
        _nowiso = now().isoformat()[:16]
        for h_ in load_json("store_history.json", {}).values():
            c_h = chain_of(h_.get("name"))
            if c_h:
                for v in (h_.get("items") or {}).values():
                    if v.get("g") in ("pokemon", "onepiece") and v.get("e") and v["e"] < _nowiso:
                        CG_PAGES.add((c_h, v["g"]))

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
                       f"{upd.month}/{upd.day}時点で受付中の{what}は{n}件です（ネット抽選{on}件・店頭抽選{n - on}件）。"
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
                           f"いちばん締切が近いのは{_sname(i['store'])}の「{i.get('series') or i.get('product')}」で、{_fmt(i['end'])}締切です。"
                           "一覧は締切が近い順に並んでいます。"))
        qa.append(("抽選情報はいつ更新されますか？",
                   f"1日6回（朝7時〜夜22時）自動で更新しています。新しい抽選は見つかり次第追加し、締切を過ぎた抽選は一覧から外します。"))
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
                                     **({"url": f"{site}/{i['lpath']}"} if i.get("lpath") and site else
                                        {"url": i["url"]} if i.get("url") else {})} for k, i in enumerate(rows)]}

    def write(path, lock, meta, subset, trail=None):
        p = out / path / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        meta["canonical"] = f"{site}/{path}" if site else None
        meta["site"], meta["verify"] = site, verify
        meta.setdefault("upd", ("更新 ", updated))  # 11/8 Fable：文字列を入れていて画面の更新時刻が「11/1 00:00」になっていた
        meta["prerender"] = prerender(subset)
        ld = []  # ItemList は外部の応募ページを含みリッチリザルトの対象外なので出さない（11/7 監査）
        if trail:
            meta["crumbs"], bl = crumbs(trail)
            ld.insert(0, bl)
        org = {"@type": "Organization", "@id": f"{site}/#organization", "name": "トレカ抽選ナビ", "url": f"{site}/",
               "logo": {"@type": "ImageObject", "url": f"{site}/apple-touch-icon.png"},
               "sameAs": [f"https://x.com/{(s.get('x_account') or 'pokepi_tcg').lstrip('@')}"]}  # 11/8 Fable技術：公式Xとの結びつき
        if not path:
            ld.insert(0, {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{site}/#website", "name": "トレカ抽選ナビ",
                          "url": f"{site}/", "inLanguage": "ja", "description": meta["desc"], "publisher": org})
            if site:  # 11/8：海外ページ（/en/ /zh-tw/ /ko/）からの hreflang に日本語トップが返す（双方向でないと Google が無視する）。中国語の言語コードは intl.py と同じ3つ
                meta["head_extra"] = [f'<link rel="alternate" hreflang="{hl}" href="{site}/{sub}">' for hl, sub in
                                      (("ja", ""), ("en", "en/"), ("zh-Hant", "zh-tw/"), ("zh-TW", "zh-tw/"), ("zh-HK", "zh-tw/"),
                                       ("ko", "ko/"), ("x-default", "en/"))]  # 海外ページ側と同じ（/en/）にそろえる
        _nz = lambda t: re.sub(r"¥[\d,]+|\d{1,2}/\d{1,2}|\d{1,2}:\d{2}|\d+件", "", str(t or ""))  # 11/8 Fable：日付・値段・件数だけの違いは「更新」にしない
        sig = sha(json.dumps([re.sub(r"【[^】]*更新】", "", meta["title"]), meta.get("h1"), meta.get("lead"),
                              _nz(meta.get("info_html")), _nz(meta.get("aff")),
                              sorted((i.get("key") or "", i.get("end") or "", str(i.get("conditions") or "")) for i in subset)],
                             ensure_ascii=False, default=str))
        prev = pmod.get(path) or []
        lm = prev[1] if prev[:1] == [sig] and len(prev) > 1 else today_iso
        first = prev[2] if len(prev) > 2 else (min([i["found_at"] for i in subset if i.get("found_at")] or [today_iso])[:10])
        pmod[path] = [sig, lm, first]
        ld.append({"@context": "https://schema.org", "@type": "WebPage", "name": meta["title"], "headline": meta["h1"],
                   "description": meta["desc"], "url": f"{site}/{path}", "inLanguage": "ja",
                   "datePublished": first, "dateModified": lm, "publisher": org})
        if meta.get("og_image"):  # ページの代表の画像（Googleの「おすすめ（Discover）」などで使われる・11/7）
            ld[-1]["primaryImageOfPage"] = {"@type": "ImageObject", "url": meta["og_image"], "width": 1200, "height": 630}
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
        elif lock.get("all_subset"):  # 今日締切：全部のゲームの分を入れて「すべて」で開く（11/8：ポケカの分しか入っていなかった）
            data = {**common_data, "lock": lock, "items": list(subset), "allLoaded": True, "defaultGame": "all",
                    "gameCounts": {g_: sum(1 for i in subset if i["game"] == g_) for g_ in games}}
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
        if not meta.get("noindex"):  # 中身のうすいページ（抽選も履歴もない）は検索に出さない・サイトマップにも入れない
            urls.append((f"{site}/{path}", lm))

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
        # ゲームのページの共有画像（XやLINEにリンクを貼ったときの画像）：受付中・今日締切の件数など
        og_g = f"og/game-{slug}.png"
        try:
            og_image(out / og_g, short, "#facc15" if g == "pokemon" else "#f87171" if g == "onepiece" else "#38bdf8",
                     f"{short}の抽選まとめ",
                     [("いま受付中の抽選", f"{len(gi)}件", True), ("今日が締切", f"{today}件", bool(today)),
                      ("ネット抽選／店頭抽選", f"{online}件／{len(gi) - online}件", False)]
                     + ([("受付中がいちばん多い弾", series[0], False)] if series else []),
                     "締切が近い順に・1日6回更新")
        except Exception as e:
            print("OGP画像を作れませんでした", g, e)
            og_g = ""
        def _upcoming(gs, k=8):
            """11/8：トップ・ゲームのページから、これから発売の新弾ページへ（新しいページを早く見つけてもらう・順位を上げる）"""
            td_ = now().date().isoformat()
            rows_ = sorted(((v.get("release"), gg, xx, v) for gg in gs for xx, v in ((_ser_cfg()["info"].get(gg) or {}).items())
                            if str(v.get("release") or "") > td_), key=lambda t: t[0])[:k]
            if not rows_:
                return ""
            return ('<section class="sinfo snext" aria-label="これから発売の新弾"><h2>これから発売の新弾</h2><ul>'
                    + "".join(f'<li><a href="/{series_path(gg, xx)}">{escape(GAME_SHORT[gg]) + " " if len(gs) > 1 else ""}{escape(xx)}</a>'
                              + f'<span>{escape((re.search(r"【([A-Z]{2,4}-[0-9]{2})】", v.get("type") or "") or [None, ""])[1])}</span>'
                              + f'<b>{escape(jdate(r_))}</b></li>' for r_, gg, xx, v in rows_)
                    + '</ul><p class="more"><a href="/calendar/">発売日カレンダーをすべて見る ›</a></p></section>')

        meta = {"og_image": f"{site}/{og_g}" if og_g else None,
                # 「ポケモンカード 抽選」のように正式名で探す人にも届くよう、略称と正式名の両方を入れる（11/3）
                "title": (f"{name}（{short}）の" if name != short else f"【{short}】") + f"抽選販売・予約の最新情報まとめ【{md}更新】受付中{len(gi)}件" + (f"・本日締切{today}件" if today else "") + "｜トレカ抽選ナビ",
                "desc": f"【{md}更新】" + (f"{name}（{short}）" if name != short else name) + f"の抽選販売・予約・再販情報を締切が近い順にまとめ。受付中{len(gi)}件（ネット抽選{online}件・"
                        f"店頭抽選{len(gi) - online}件）。" + (f"「{'」「'.join(series[:3])}」など弾別、" if series else "") +
                        "都道府県別・本人確認や会員の有無で絞り込めます。1日6回自動更新。",
                "summary": summary(gi, f"{short}の抽選"),
                "faq": faq_for(gi, f"{short}の抽選"),
                "h1": f"【{short}】抽選販売・予約の最新情報まとめ",
                "lead": f"いま受付中の{name}の抽選を、ネット・店頭（都道府県別）に分けて締切が近い順に並べています。"
                        "1日6回（朝7時〜夜22時）自動で更新しています。",
                "links": _menu(items, games, g), "root": "/",
                "supply_bottom": _supply_ad(short, name, tag, raff, prices, g) + (_upcoming([g]) if g in ("pokemon", "onepiece") else ""),  # 11/8 Fable：一覧の後へ
                "topsq": souba_strip([(x, souba_sm[f"{g}|{x}"]) for x in series if f"{g}|{x}" in souba_sm], f"/souba/#{g}", g)}
        write(f"{slug}/", {"game": g}, dict(meta), gi, [("トップ", ""), (f"{short}の抽選", f"{slug}/")])
        if g == games[0]:
            top = dict(meta, title=f"トレカ抽選ナビ｜ポケカ・ワンピースカードの抽選情報まとめ【{md}更新】締切が近い順",
                       desc=f"【{md}更新】ポケカ（ポケモンカード）・ワンピースカード・フュージョンワールドの抽選販売をネットと店頭（都道府県別）に分けて"
                            f"締切が近い順に掲載。受付中{sum(game_counts.values())}件。本人確認・会員の有無でも絞り込めます。",
                       summary=summary(items, "トレカの抽選"), faq=faq_for(items, "トレカの抽選"),
                       h1="トレカの抽選情報まとめ",
                       lead="ポケカ・ワンピースカード・ドラゴンボール フュージョンワールドの抽選を、ネットと店頭（都道府県別）で"
                            "締切が近い順にまとめています。本人確認・会員カードの有無でも絞り込めます。")
            top["supply_bottom"] = _supply_ad(short, name, tag, raff, prices, g) + _upcoming([gg for gg in ("pokemon", "onepiece") if gg in games])
            # トップ：ゲームごとの相場の枠を全部入れておき、上のタブで選んだゲームの枠だけ見せる
            strips = []
            for gg in games:
                cnt = {}
                for i_ in items:
                    if i_["game"] == gg:
                        for x_ in (i_.get("sers") or ([i_["series"]] if i_.get("series") else [])):
                            cnt[x_] = cnt.get(x_, 0) + 1
                xs = sorted(cnt, key=lambda x_: -cnt[x_])
                strips.append(souba_strip([(x_, souba_sm[f"{gg}|{x_}"]) for x_ in xs if f"{gg}|{x_}" in souba_sm], f"/souba/#{gg}", gg))
            top["topsq"] = "".join(strips)
            write("", {}, top, items)

        if sample is None and not CS_PAGES:
            plan_cs_pages(items)

        def write_saihan(g, x, si, info, sm, rr, post_x, pre_mode, rel_x):
            """弾ごとの「予約・再販・在庫」ページ（/pokeka/<弾>/saihan/）。11/8 Fable（ライバル比較）：
            「〇〇 再販」「〇〇 予約」で探す人の受け皿。予想は書かず、在庫の確認時刻・これまでの抽選の数字だけ"""
            from collections import Counter
            path = series_path(g, x) + "saihan/"
            on_ = sum(1 for i in si if i.get("channel") != "store")
            teika = (sm or {}).get("teika") or (int(re.findall(r"([\d,]+)円", info.get("price") or "")[-1].replace(",", "")) if re.findall(r"([\d,]+)円", info.get("price") or "") else None)
            stock, when = stock_for(g, x)
            # 1) いま定価で買える（Workerが1〜2分おきに確認。確認できた時だけ「販売中」）
            rows = _stock_rows(g, x, raff, "saihan")
            q = f"{name} {x}"
            if rows:
                # 11/8：招待リクエストだけのときは「すぐ買える」ではないので言い分ける
                buy_now = any(src == "rakuten" or a_ == "buy" for src, a_, _, _ in stock)
                head_ = (f'<p class="sh-ok">✅ いま定価で買える通販があります（{escape(when)}時点）</p>' if buy_now else
                         f'<p class="sh-ok">✅ Amazon.co.jp 本体（定価）の招待リクエストを受付中です（{escape(when)}時点）</p>'
                         '<p class="sh-ng">リクエストして、招待メールが届いた人だけが定価で買えます（全員が買えるわけではありません）。</p>')
            else:
                head_ = (f'<p class="sh-ng">いま楽天ブックス・Amazon.co.jp本体で定価の在庫は確認できていません（{escape(when)}時点）。'
                         '在庫が戻ったら、Xの速報ですぐお知らせします（見張りは1〜2分おき。このページは1日6回更新）。</p>' if when else "")
                rows = [("楽天ブックス", ("予約・発売日の在庫をチェック" if pre_mode else "売り切れでも、キャンセル分などで在庫が戻ることがあります"), _rakb(q, raff), "楽天ブックスで見る", "rakb")]
                if tag:
                    rows.append(("Amazon", ("予約・招待リクエストが急に始まることがあります" if pre_mode else "Amazon.co.jp 本体の販売・招待リクエストが急に始まることがあります"), _amz(q, tag), "Amazonで見る", "amz"))
            li = "".join(f'<li><div><b>{escape(t)}</b><small>{escape(sub)}</small></div><a class="b-{c}" href="{escape(u)}" {_REL} data-pl="saihan">{escape(btn)}</a></li>'
                         for t, sub, u, btn, c in rows)
            can_buy = any(src == "rakuten" or a_ == "buy" for src, a_, _, _ in stock)
            box_t = ("定価で予約・購入できるところ" if pre_mode else "いま定価で買えるところ" if can_buy
                     else "定価で申し込めるところ（招待制）" if stock else "定価の在庫が戻ったら買えるところ")
            buy = (f'<aside class="ad lose"><div class="ad-top"><span>{box_t}</span>{PR_B}</div>'
                   f'{head_}<ul class="lose-l">{li}</ul><p class="ad-note">楽天・Amazonへのリンクは広告です。在庫・価格はリンク先で確認してください。</p></aside>')
            # 2) 数字（事実だけ）
            facts = []
            if rel_x:
                facts.append(("発売日", jdate(rel_x)))
            if teika:
                facts.append(("定価（BOX）", _yen(teika)))
            if sm:
                facts.append((f"BOX相場（{_md(sm['date'])}・スニダン）", _yen(sm["price"]) + (f"（定価の{sm['price'] / teika:.1f}倍）" if teika else "")))
            facts.append(("いま受付中の抽選", f"{len(si)}件（ネット{on_}件・店頭{len(si) - on_}件）"))
            chain_post = Counter(chain_of(t[1]) for t in post_x if chain_of(t[1]))
            if not pre_mode:
                facts.append(("発売後に見つけた追加抽選・再販", f"{len(post_x)}件" + (f"（直近 {_md_(post_x[0][0]['e'])}締切・{_sname(post_x[0][1])}）" if post_x else "")))
                if chain_post:
                    facts.append(("発売後の抽選が多いお店", "、".join(f"{CHAIN[c][1]}（{n}件）" for c, n in chain_post.most_common(4))))
            fact_html = ('<section class="sinfo"><h2>「' + escape(x) + ('」の予約・抽選の状況' if pre_mode else '」の再販・追加抽選の状況') +
                         f'<small>{escape(upd_hm)}時点</small></h2><table>' + "".join(f"<tr><th>{escape(a_)}</th><td>{escape(b_)}</td></tr>" for a_, b_ in facts) + "</table></section>")
            # 3) お店ごとの間隔（発売後3件以上のお店だけ。予想ではなく「これまでの間隔」）
            iv = []
            for c, n in chain_post.most_common(6):
                if n < 3:
                    continue
                ds = sorted({t[0]["e"][:10] for t in post_x if chain_of(t[1]) == c})
                import datetime as _dd
                gaps = [(_dd.date.fromisoformat(b2) - _dd.date.fromisoformat(a2)).days for a2, b2 in zip(ds, ds[1:])]
                gaps = [g2 for g2 in gaps if g2 > 0]
                link = CS_PAGES.get((c, g, x))
                nm_c = f'<a href="/{link}">{escape(CHAIN[c][1])}</a>' if link else escape(CHAIN[c][1])
                iv.append(f"<li>{nm_c}：発売後の抽選{n}件" + (f"、締切日の間隔はふつう{_median(gaps)}日ほど" if len(gaps) >= 2 else "") + f"（直近 {_md_(ds[-1])}）</li>")
            iv_html = (f'<section class="hist"><h2>お店ごとの発売後の抽選<small>トレカ抽選ナビ調べ</small></h2><ul>{"".join(iv)}</ul>'
                       '<p class="note">※これまでの記録です。次の抽選の日を予想するものではありません。</p></section>') if iv else ""
            # 4) チェーン×弾のページへ
            cs_links = [(CHAIN[c][1], "/" + pth) for (c, g2, x2), pth in CS_PAGES.items() if g2 == g and x2 == x]
            cs_html = _links(f"お店ごとの「{x}」の抽選", cs_links) if cs_links else ""
            # 5) これまでの抽選の表（発売後のぶん）
            past_all = ser_past(g, x)
            tab_rows = post_x if (post_x and not pre_mode) else past_all
            tab_html = (f'<section class="hist"><h2>{"発売後の追加抽選・再販の記録" if (post_x and not pre_mode) else "これまでの抽選"}<small>{len(tab_rows)}件</small></h2>'
                        + hist_table(tab_rows) + '<p class="note">※トレカ抽選ナビが見つけた抽選（受付終了）です。お店の名前を押すと、そのお店のこれまでの抽選が見られます。</p></section>') if tab_rows else ""
            # FAQ（数字が変わる答え）
            faq = []
            if pre_mode:
                faq.append((f"「{x}」の発売日と定価は？", f"発売日は{jdate(rel_x)}" + (f"、BOXの定価は{_yen(teika)}" if teika else "") + "です。"))
                faq.append((f"「{x}」はどこで予約できますか？",
                            (f"いま受付中の抽選・予約は{len(si)}件（ネット{on_}件・店頭{len(si) - on_}件）です。このページの一覧で締切順に見られます。" if si else
                             "いま受付中の抽選・予約は見つかっていません。始まり次第、このページに自動で載ります。")
                            + "楽天ブックスやAmazonで予約が始まることもあるので、上のリンクから確認できます。"))
            else:
                faq.append((f"「{x}」の再販はありますか？",
                            f"トレカ抽選ナビでは、発売日（{jdate(rel_x)}）のあとに{len(post_x)}件の追加抽選・再販の抽選を見つけています"
                            + (f"（直近は{_md_(post_x[0][0]['e'])}締切の{_sname(post_x[0][1])}）" if post_x else "")
                            + "。メーカーの再販の予定は、公式の発表をご確認ください。"))
                faq.append((f"「{x}」は今どこで買えますか？",
                            ((f"{when}時点で、楽天ブックスかAmazon.co.jp本体の販売を確認できています。" if any(src == "rakuten" or a_ == "buy" for src, a_, _, _ in stock)
                              else f"{when}時点で、Amazon.co.jp本体の招待リクエスト（招待された人が定価で買える方式）を受付中です。") if stock else
                             (f"{when}時点で、楽天ブックス・Amazon.co.jp本体の在庫は確認できていません。" if when else ""))
                            + (f"いま受付中の抽選は{len(si)}件です。" if si else "")))
                if sm:
                    faq.append((f"「{x}」のBOXの相場は？", f"スニダンで{_md(sm['date'])}に成立した取引の平均は{_yen(sm['price'])}" + (f"で、定価{_yen(teika)}の{sm['price'] / teika:.1f}倍" if teika else "") + "です。"))
            ttl = (f"【{short}】{x}の予約・抽選はどこ？定価で買える店と発売日{_md_(rel_x)}【{md}更新】｜トレカ抽選ナビ" if pre_mode else
                   f"【{short}】{x}の再販・追加抽選・在庫情報【{md}更新】" + (f"受付中{len(si)}件・" if si else "") + "定価で買える店｜トレカ抽選ナビ")
            desc = ((f"【{md}更新】{name}「{x}」（{jdate(rel_x)}発売" + (f"・定価{_yen(teika)}" if teika else "") + f"）の予約・抽選の受付状況。受付中{len(si)}件、"
                     "楽天ブックス・Amazonの在庫を1〜2分おきに確認しています。") if pre_mode else
                    (f"【{md}更新】{name}「{x}」の再販・追加抽選・在庫情報。発売後に見つけた抽選{len(post_x)}件、受付中{len(si)}件。"
                     "楽天ブックス・Amazonの在庫を1〜2分おきに確認し、相場（スニダン）も載せています。"))
            lead = ((f"「{x}」は{jdate(rel_x)}発売です。予約・抽選の受付中のものと、定価で買えるところをまとめています。" if pre_mode else
                     f"「{x}」の発売後の追加抽選・再販と、いま定価で買えるところをまとめています。")
                    + "数字はトレカ抽選ナビの記録で、予想ではありません。")
            write(path, {"game": g, "series": x, "channel": "store" if sum(1 for i in si if i.get("channel") == "store") * 2 > len(si) else "online"}, {
                "title": ttl, "desc": desc, "h1": (f"「{x}」の予約・抽選・定価で買える店" if pre_mode else f"「{x}」の再販・追加抽選・在庫情報"),
                "lead": lead, "summary": summary(si, f"「{x}」の抽選"), "faq": faq or None,
                "aff": buy + fact_html + (iv_html + cs_html if not si else ""),
                "info_html": (iv_html + cs_html if si else "") + tab_html,
                "supply_bottom": _price_anchor(x, name, sm, tag, raff, rel_x, g) + cards_block(x, cards_by.get(f"{g}|{x}") or [], tag),
                "links": _menu(items, games, g, "/" + series_path(g, x)), "root": "/"}, si,
                [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (x, series_path(g, x)), ("予約・再販" if pre_mode else "再販・在庫", path)])

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
            sb_img = rr if rr.get("image") else None
            info0 = (_ser_cfg()["info"].get(g) or {}).get(x) or {}
            aff = (_product_ad(x, name, rr, tag, raff, info0.get("release")) + souba_block(x, sm, souba_fx, us_line=(g == "pokemon"), img=sb_img)
                   + _price_anchor(x, name, sm, tag, raff, info0.get("release"), g) + cards_block(x, cards_by.get(f"{g}|{x}") or [], tag))
            alias = (s.get("rakuten_aliases") or {}).get(x) or al_g.get(x)
            info = (_ser_cfg()["info"].get(g) or {}).get(x) or {}
            rel_x0 = str(info.get("release") or "")[:10]
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
            # 11/8：新弾ページを強く。settings.yaml の series_info に about（説明）・points（ポイント）・faq を書いた弾は、その説明を出す
            code_x = (re.search(r"【([A-Z]{2,4}-\d{2})】", info.get("type") or "") or [None, None])[1]
            code_b = f"【{code_x}】" if code_x and code_x not in x else ""
            about_html = ""
            if info.get("about") or info.get("points"):
                about_html = ('<section class="sinfo sabout" aria-label="どんな弾か"><h2>' + escape(x) + code_b + 'ってどんな弾？</h2>'
                              + "".join(f"<p>{escape(t)}</p>" for t in (info.get("about") or []))
                              + ("<ul>" + "".join(f"<li>{escape(t)}</li>" for t in info["points"]) + "</ul>" if info.get("points") else "")
                              + "</section>")
            # これから発売の同じゲームの弾（新弾どうしをつないで、まとめて読まれるように）
            up_ = sorted(((v.get("release"), k) for k, v in ((_ser_cfg()["info"].get(g) or {}).items())
                          if str(v.get("release") or "") > today_d and k != x), key=lambda t: t[0])[:6]
            next_html = ""
            if up_ and (not rel_x0 or rel_x0 > (now().date() - __import__("datetime").timedelta(days=60)).isoformat()):
                next_html = ('<section class="sinfo snext" aria-label="これから発売の弾"><h2>これから発売の' + escape(short) + 'の新弾</h2><ul>'
                             + "".join(f'<li><a href="/{series_path(g, k)}">{escape(k)}</a>'
                                       + (f'<span>{escape(((re.search(r"【([A-Z]{2,4}-[0-9]{2})】", (_ser_cfg()["info"][g][k].get("type") or "")) or [None, ""])[1]))}</span>')
                                       + f'<b>{escape(jdate(r_))}</b></li>' for r_, k in up_)
                             + f'</ul><p class="more"><a href="/calendar/">発売日カレンダーをすべて見る ›</a></p></section>')
            # ページの一番上：発売日・定価・相場・受付中の抽選をひと目で（相場は下の相場の欄へ飛ぶ）
            q_ = []
            if info.get("release"):
                q_.append(("発売日", escape(jdate(info["release"])), ""))
            if sm and sm.get("teika"):
                q_.append(("定価", _yen(sm["teika"]), ""))
            elif info.get("price"):
                q_.append(("定価", escape(info["price"].split("／")[-1].replace("（税込）", "")), ""))
            if sm:
                q_.append((f"BOX相場（{_md(sm['date'])}）", _yen(sm["price"]), "#souba"))
            q_.append(("受付中の抽選", f"{len(si)}件" if si else "これから", "#list" if si else ""))
            quick_html = ('<div class="squick">' + "".join(
                (f'<a href="{h}">' if h else "<div>") + f"<span>{escape(a)}</span><b>{b}</b>" + ("<i>相場を見る ›</i>" if h == "#souba" else "")
                + ("</a>" if h else "</div>") for a, b, h in q_) + "</div>") if len(q_) > 1 else ""
            stat_html = _series_stats(g, x, raw_lots if sample is None else {}, short)
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
                         x, og_rows, f"{name}の抽選販売・予約情報", photo=rr.get("image"))
            except Exception as e:
                print("OGP画像を作れませんでした", x, e)
                og_rel = ""
            _SER_WRITTEN.add(series_path(g, x))
            # 11/8 Fable：弾ごとの「予約・再販・在庫」ページ（発売前は予約・定価で買える店、発売後は再販・追加抽選・在庫）
            rel_x = str(info.get("release") or "")[:10]
            post_x = [t for t in ser_past(g, x) if rel_x and t[0]["e"][:10] >= rel_x] if sample is None else []
            pre_mode = bool(rel_x) and rel_x > today_d
            make_sh = sample is None and g in ("pokemon", "onepiece") and bool(rel_x) and (
                (pre_mode and rel_x <= (now().date() + __import__("datetime").timedelta(days=150)).isoformat())
                or (not pre_mode and rel_x >= (now().date() - __import__("datetime").timedelta(days=365)).isoformat()
                    and (len(post_x) + sum(1 for i in si if True) >= 3 or sm)))
            sh_path = series_path(g, x) + "saihan/"
            sh_link = (f'<a class="shlink" href="/{sh_path}">{"🛒 予約・定価で買える店を見る" if pre_mode else "🔁 再販・追加抽選・在庫の情報を見る"} ›</a>'
                       if make_sh else "")
            # 11/8 Fable：店頭が9割の弾でも「ネット抽選」から開いて数件しか見えなかったので、多いほうから開く
            write(series_path(g, x), {"game": g, "series": x, "channel": "store" if sum(1 for i in si if i.get("channel") == "store") * 2 > len(si) else "online"}, {
                "og_image": f"{site}/{og_rel}" if og_rel else None,
                "title": (f"【{short}】{x}{code_b}の抽選販売・予約の最新情報まとめ【{md}更新】受付中{len(si)}件｜トレカ抽選ナビ" if si else
                          f"【{short}】{x}{code_b}の予約・抽選情報まとめ｜{int(rel_x0[5:7])}月{int(rel_x0[8:10])}日発売・定価｜トレカ抽選ナビ" if rel_x0 > today_d else
                          (f"【{short}】{x}のBOX相場・高額カード" + ("｜発売日・定価" if info.get("release") else "") + "｜トレカ抽選ナビ"
                           if sm and str(info.get("release") or "") < cut90 else  # 古い弾は「抽選」より「相場」で探される（11/7）
                           f"【{short}】{x}の抽選販売・予約情報まとめ" + ("｜発売日・定価" if info.get("release") else "") + "｜トレカ抽選ナビ")),
                "desc": (f"【{md}更新】{name}「{x}」" + (f"（{alias}）" if alias and alias != x else "") +
                         f"の抽選販売・予約・再販情報を1日6回更新。" + ("・".join(sts) + "など" if sts else "") +
                         f"受付中{len(si)}件（ネット{on_}件・店頭{len(si) - on_}件）を締切順に一覧。本人確認・会員の有無も分かります。") if si else
                        (f"{name}「{x}」{code_b}の予約・抽選情報をまとめるページです。" + (info.get("hook") or ((info.get("about") or [""])[0].split("。")[0] + "。" if info.get("about") else "")) +
                         (f"発売日は{jdate(info['release'])}" + (f"、希望小売価格は{info['price']}" if info.get("price") else "") + "。" if info.get("release") else "") +
                         "抽選・予約が始まり次第、お店ごとの締切・応募方法をここに自動で載せます。"),
                "summary": summary(si, f"「{x}」の抽選"),
                "faq": [tuple(q) for q in (info.get("faq") or [])] + ([(f"「{x}」のBOXの相場はいくらですか？",
                          f"スニダンで{_md(sm['date'])}に成立した1個の取引の平均は{_yen(sm['price'])}です" +
                          (f"（定価{_yen(sm['teika'])}との差 {'+' if sm['price'] >= sm['teika'] else '−'}{abs(sm['price'] - sm['teika']):,}円）" if sm.get("teika") else "") +
                          "。相場は毎日変わります。")] if sm else []) + faq_for(si, f"「{x}」の抽選", info, f"「{x}」"),
                "info_html": (about_html + info_html + stat_html + ser_hist_html(g, x, info.get("release")) + next_html) if si else "",  # 抽選がまだない弾は基本情報を上に出す（数字で見るも、受付中があれば一覧の下）
                "h1": f"【{short}】{x}{code_b}の抽選販売・予約の最新情報まとめ",
                "lead": (f"{name}「{x}」の受付中の抽選は{len(si)}件です。新しい抽選が見つかり次第、自動で追加されます。" if si else
                         f"{name}「{x}」の抽選・予約は、いま受付中のものがありません。抽選が始まり次第、このページに自動で載ります（1日6回更新）。"),
                "aff": quick_html + sh_link + ("" if si else about_html) + _ser_areas(g, slug, x, si) + _ser_chains(g, x, si) + ("" if si else likely_chains_html(g, x)) + (aff if si else _product_ad(x, name, rr, tag, raff, info.get("release"))
                                                     + souba_block(x, sm, souba_fx, us_line=(g == "pokemon"), img=sb_img) + _price_anchor(x, name, sm, tag, raff, info.get("release"), g)
                                                     + cards_block(x, cards_by.get(f"{g}|{x}") or [], tag) + info_html + stat_html + ser_hist_html(g, x, info.get("release")) + next_html),
                "links": _menu(items, games, g, "/" + series_path(g, x)),
                "root": "/"}, si, [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (x, series_path(g, x))])


            if make_sh:
                write_saihan(g, x, si, info, sm, rr, post_x, pre_mode, rel_x)

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
            near_l = [(f"{b}（{acnt_g.get(b, 0)}件）" if acnt_g.get(b) else b, f"/{slug}/area/{PREF[b]}/") for b in NEAR.get(a, [])
                      if g in ("pokemon", "onepiece") or acnt_g.get(b)]  # ページがない県にはリンクしない（フュージョンワールドは抽選がある県だけページがある）
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
                "topsq": line_box(a),
                "info_html": area_html + (near_html if ai else ""),
                "title": f"{short} 抽選 {a}｜{a}の店頭抽選" + (f" 受付中{len(ai)}件" if ai else "") + f"【{md}更新】｜トレカ抽選ナビ",
                "desc": f"【{md}更新】{short}{f'（{name}）' if short != name else ''}の抽選を{a}で探すなら。{a}のお店の店頭抽選・Web応募で店頭受け取りの抽選" +
                        (f"{len(ai)}件（今日締切{today_a}件・新着{new_a}件）を締切が近い順にまとめています。" if ai else
                         "をまとめています。いま受付中のものがない時は、近くの県の抽選を案内します。") + "1日6回自動更新。",
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
                "desc": f"【{md}更新】{lead[:60]}… 受付中{len(sub)}件（ネット{on_}件・店頭{len(sub) - on_}件）を締切順に掲載。1日6回自動更新。",
                "summary": summary(sub, h1), "faq": faq_for(sub, h1), "h1": h1, "lead": lead,
                "links": _menu(items, games, g), "root": "/"}, sub,
                [("トップ", ""), (f"{short}の抽選", f"{slug}/"), (h1, f"{slug}/{key}/")])

    # --- 今日締切の抽選（全ゲーム）：/today/ と、その日の画像（Xの朝の投稿・共有画像に使う。11/7）---
    if items and sample is None:
        td = [i for i in items if parse_dt(i.get("end")) and parse_dt(i["end"]).date() == now().date()]
        td.sort(key=lambda i: parse_dt(i["end"]))
        t0 = now()
        dlabel = f"{t0.month}/{t0.day}（{'月火水木金土日'[t0.weekday()]}）"
        og_t = ""
        try:
            today_image(out / "og" / "today.png", td, dlabel)
            og_t = f"{site}/og/today.png?d={t0:%Y%m%d}"
        except Exception as e:
            print("今日締切の画像を作れませんでした", e)
        try:  # 朝のX投稿（Xのサイトで予約投稿する）用の文章（11/7）
            from xpost import compose_today
            (out / "x").mkdir(exist_ok=True)
            tdf = [i for i in td if parse_dt(i["end"]) > now()]
            (out / "x" / "today.json").write_text(json.dumps({"date": t0.date().isoformat(), "n": len(tdf),
                "text": compose_today(tdf, s) if len(tdf) >= 2 else "", "img": f"/og/today.png?d={t0:%Y%m%d}"}, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print("今日締切の投稿文を作れませんでした", e)
        h1 = f"今日締切のトレカ抽選（{dlabel}）"
        lead = ("今日が応募締切のポケカ・ワンピースカードなどの抽選です。締切時刻が近い順に並んでいます。"
                "「☐ 応募した」を押しておくと、締切の3時間前に通知でお知らせすることもできます（応募したリストのページから）。")
        on_ = sum(1 for i in td if i.get("channel") != "store")
        write("today/", {"checks": ["f-today"], "all_subset": True}, {
            "og_image": og_t or None,
            "title": f"【{md}】今日締切のトレカ抽選まとめ｜ポケカ・ワンピ{len(td)}件｜トレカ抽選ナビ",
            "desc": f"【{md}更新】今日が締切のポケカ・ワンピースカードの抽選{len(td)}件（ネット{on_}件・店頭{len(td) - on_}件）を締切が近い順に。応募し忘れのチェックに。",
            "summary": summary(td, h1), "faq": faq_for(td, h1), "h1": h1, "lead": lead,
            "links": _menu(items, games, games[0]), "root": "/"}, td,
            [("トップ", ""), ("今日締切の抽選", "today/")])

    # --- 毎日19:15のX「新弾カウントダウン」の画像と文（/x/countdown.json・/og/countdown.png。11/7 Fable案）---
    if items and sample is None:
        try:
            import datetime as _dt
            t0 = now()
            td0 = t0.date()
            WD = "月火水木金土日"
            def _teika(g_, x_, inf_):
                sm0 = souba_sm.get(f"{g_}|{x_}") or {}
                if sm0.get("teika"):
                    return int(sm0["teika"])
                p_ = str(inf_.get("price") or "")
                m_ = re.search(r"BOX[^0-9円]*?([\d,]{3,})円", p_) or re.search(r"([\d,]{4,})円", p_)
                return int(m_.group(1).replace(",", "")) if m_ else None
            def _pick(g_):
                inf = _ser_cfg()["info"].get(g_) or {}
                up = sorted((str(v.get("release"))[:10], x_) for x_, v in inf.items() if v.get("release") and str(v["release"])[:10] > td0.isoformat())
                up = [(r, x_) for r, x_ in up if (_dt.date.fromisoformat(r) - td0).days <= 60]
                if up:
                    return "pre", up[0][1], up[0][0], inf[up[0][1]]
                done = sorted(((str(v.get("release"))[:10], x_) for x_, v in inf.items() if v.get("release") and str(v["release"])[:10] <= td0.isoformat()), reverse=True)
                done = [(r, x_) for r, x_ in done if (td0 - _dt.date.fromisoformat(r)).days <= 14]
                return ("post", done[0][1], done[0][0], inf[done[0][1]]) if done else None
            order = ["pokemon", "onepiece"] if td0.day % 2 else ["onepiece", "pokemon"]
            cd = None
            for g_ in order:
                pk = _pick(g_)
                if pk:
                    cd = (g_,) + pk
                    break
            if cd:
                g_, mode, x_, rel, inf_ = cd
                rd = _dt.date.fromisoformat(rel)
                days = (rd - td0).days if mode == "pre" else (td0 - rd).days + 1
                si_ = [i for i in items if i["game"] == g_ and in_ser(i, x_)]
                noid = sum(1 for i in si_ if i.get("id_check") is False)
                onl = sum(1 for i in si_ if i.get("channel") != "store")
                sm0 = souba_sm.get(f"{g_}|{x_}") or {}
                tk = _teika(g_, x_, inf_)
                tiles = [("定価（税込）", f"¥{tk:,}" if tk else "公式で確認", "", "")]
                if sm0.get("price"):
                    pv = (sm0.get("prev") or [None, None])[1]
                    df = sm0["price"] - pv if pv else None
                    tiles.append((f"スニダン相場（{_md(sm0['date'])}）", f"¥{sm0['price']:,}",
                                  (f"前日比 {'+' if df > 0 else '−' if df < 0 else '±'}{abs(df):,}" if df is not None else ""),
                                  "#D7263D" if df and df > 0 else "#2563eb" if df and df < 0 else "#6b7280"))
                else:
                    tiles.append(("スニダン相場", "まだ取引なし", "", ""))
                tiles.append(("受付中の抽選（当サイト掲載）", f"{len(si_)}件", (f"本人確認なし {noid}件" if noid else f"ネット応募 {onl}件" if onl else ""), "#374151"))
                gname = "ポケカ" if g_ == "pokemon" else "ワンピースカード"
                sub = f"発売日 {rd.month}/{rd.day}（{WD[rd.weekday()]}）"
                foot = (f"相場はスニダンの日別相場（1個）{_md(sm0['date'])}時点" if sm0.get("price") else "相場はスニダンの日別相場（1個）") + "｜抽選は当サイトに掲載中の件数"
                countdown_image(out / "og" / "countdown.png", {"game": g_, "gname": gname, "title": x_, "sub": sub, "mode": mode,
                                                               "days": days, "tiles": tiles, "foot": foot})
                emo = "🎴" if g_ == "pokemon" else "🏴‍☠️"
                tags = "#ポケモンカード #ポケカ" if g_ == "pokemon" else "#ワンピースカード #ワンピカード抽選".replace("ワンピカード抽選", "ワンピースカード抽選")
                lines = [(f"【あと{days}日】「{x_}」{rd.month}/{rd.day}発売{emo}" if mode == "pre" else f"【発売{days}日目】「{x_}」のいま{emo}")]
                if tk and mode == "pre":
                    lines.append(f"定価 ¥{tk:,}（税込）")
                if sm0.get("price"):
                    pv = (sm0.get("prev") or [None, None])[1]
                    df = sm0["price"] - pv if pv else None
                    lines.append(f"スニダン相場 ¥{sm0['price']:,}" + (f"（前日比 {'+' if df > 0 else '−' if df < 0 else '±'}{abs(df):,}）" if df is not None else ""))
                lines.append(f"受付中の抽選 {len(si_)}件" + (f"（本人確認なし {noid}件）" if noid else f"（ネット応募 {onl}件）" if onl else ""))
                ask = (["応募するお店、もう決めた？", "定価で確保できそうな人、どれくらいいる？", "今回は何箱ねらってる？"][td0.day % 3] if mode == "pre"
                       else ["再販や抽選、拾えた人いる？", "もう開封した？", "定価で買えた人いる？"][td0.day % 3])
                text = "\n".join(lines) + "\n\n" + ask + "\n\n" + tags
                reply = (f"受付中の抽選の一覧と締切はこちら（締切前の通知・カレンダー登録もできます）👇\n{site}/{series_path(g_, x_)}?utm_source=x&utm_campaign=countdown")
                (out / "x").mkdir(exist_ok=True)
                (out / "x" / "countdown.json").write_text(json.dumps({"date": td0.isoformat(), "game": g_, "series": x_, "mode": mode, "days": days,
                    "text": text, "reply": reply, "img": f"/og/countdown.png?d={t0:%Y%m%d}"}, ensure_ascii=False), encoding="utf-8")
                (out / "x" / "countdown.html").write_text(
                    '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><title>countdown</title><body>'
                    '<img id="i" style="max-width:100%"><script>(async()=>{const j=await fetch("/x/countdown.json?"+Date.now(),{cache:"no-store"}).then(r=>r.json());'
                    'const b=await fetch(j.img+"&t="+Date.now(),{cache:"no-store"}).then(r=>r.blob());const u=await new Promise(r=>{const f=new FileReader();f.onload=()=>r(f.result);f.readAsDataURL(b)});'
                    'document.getElementById("i").src=u;window.__json=j;window.name=JSON.stringify({type:"tcg-imgs",list:[{name:"countdown.png",dataURL:u}],text:j.text,reply:j.reply,date:j.date});window.__done=true;})();</script>',
                    encoding="utf-8")
        except Exception as e:
            print("カウントダウンの画像を作れませんでした", e)

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
{guide_links_html()}
<p class="note">ネット抽選だけを見たいときは<a href="{gl("pokemon", "online")}">ポケカのネット抽選</a>・<a href="{gl("onepiece", "online")}">ワンピースカードのネット抽選</a>をどうぞ。</p>
</article>"""
        write("guide/", {"game": games[0], "subset": True}, {
            "title": "ポケカ・ワンピースカード抽選の当て方｜当たりやすい抽選の選び方と応募のコツ｜トレカ抽選ナビ",
            "desc": f"ポケカ・ワンピースカードの抽選の種類（Web・SNS・アプリ・店頭）、当たりやすい抽選の選び方、応募前の準備をまとめました。掲載中の抽選{n_all}件のデータ付き。",
            "summary": summary([i for i in items if i["game"] == games[0]], "ポケカの抽選"),
            "faq": [("抽選は何件くらいありますか？", f"{upd_hm}時点でトレカ抽選ナビに掲載中の抽選は{n_all}件です（ネット{on_all}件・店頭{n_all - on_all}件）。"),
                    ("当たりやすい抽選はありますか？", "倍率は公表されないことがほとんどですが、地元のお店の店頭抽選や、会員カード・購入実績が条件の抽選など、応募できる人が限られる抽選は応募者が少なくなりやすいと考えられます。"),
                    ("本人確認なしで応募できる抽選はありますか？", f"本人確認がいらない抽選は{noid}件あります。ゲームごとの「本人確認なし」のページにまとめています。")],
            "h1": "ポケカ・ワンピースカード抽選の当て方と応募のコツ",
            "lead": "抽選の種類・当たりやすい抽選の選び方・応募前の準備をまとめた解説ページです。下には締切が近いポケカの抽選を載せています。",
            "aff": art, "links": _menu(items, games, games[0]), "root": "/"}, _soon([i for i in items if i["game"] == games[0]]),
            [("トップ", ""), ("抽選の当て方", "guide/")])

    # --- お店ごとの解説ページ（/guide/xxx/）：応募のしかた・結果の確かめ方・当選後の購入。中身は config/guides.yaml（公式の告知で確かめた事実だけ）。
    #     下には、いま受付中のそのお店の抽選（データから）を載せる ---
    if items:
        import yaml
        gp = Path(__file__).resolve().parent.parent / "config" / "guides.yaml"
        guides = ((yaml.safe_load(gp.read_text(encoding="utf-8")) or {}).get("guides") or []) if gp.exists() else []
        for gd in guides:
            rx = re.compile(gd["store_re"], re.I)
            sub = [i for i in items if rx.search(i.get("store") or "")]
            n_on = sum(1 for i in sub if i.get("channel") != "store")
            live = (f'<p class="lead2">いま受付中の{escape(gd["name"])}の抽選は<b>{len(sub)}件</b>です（{upd_hm}時点・下の一覧）。'
                    '新しい抽選が見つかり次第、自動で追加されます。</p>') if sub else (
                    f'<p class="lead2">いま受付中の{escape(gd["name"])}の抽選はありません（{upd_hm}時点）。始まり次第、このページの下に自動で載ります。</p>')
            body = "".join(f'<h2>{escape(sec["h"])}</h2>{sec["html"]}' for sec in gd.get("sections") or [])
            src_html = ('<p class="note">参考：' + "・".join(f'<a href="{escape(u)}" target="_blank" rel="noopener nofollow">{escape(t)}</a>'
                                                          for t, u in (gd.get("sources") or [])) + '。条件は抽選ごとに変わることがあるため、応募前に必ずお店の告知をご確認ください。</p>')
            art = (f'<article class="guide">{live}<p>{gd["intro"]}</p>{body}{src_html}'
                   '<p class="note"><a href="/guide/">抽選の当て方・コツ（全体）</a>もあわせてどうぞ。</p></article>')
            g0 = gd.get("game") or games[0]
            write(f"guide/{gd['slug']}/", {"game": g0}, {
                "title": gd["title"] + "｜トレカ抽選ナビ", "desc": gd["desc"],
                "summary": summary([i for i in sub if i["game"] == g0] or [i for i in items if i["game"] == g0], gd["name"] + "の抽選"),
                "faq": [tuple(q) for q in gd.get("faq") or []], "h1": gd["h1"],
                "lead": gd.get("lead") or "", "aff": art, "links": _menu(items, games, g0), "root": "/"},
                sub, [("トップ", ""), ("抽選の当て方", "guide/"), (gd["name"], f"guide/{gd['slug']}/")])

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
                rimg = (rk if sample is None else {}).get(f"{g}|{x}") or {}
                rows.append((sm["price"], f'<tr><th>{_sb_img(rimg, name_ + " BOX", "sb-li")}{link}' + (f'<small class="lot">抽選 受付中{nlot}件</small>' if nlot else "")
                            + _sb_buy(g, x, name_, rk if sample is None else {}, s, tag, raff) + '</th>'
                            f'<td class="sb-p" data-l="相場"><b>{_yen(sm["price"])}</b><small>{_md(sm["date"])}</small>{us}</td>'
                            f'<td data-l="定価・差">{_yen(t) if t else "-"}' + (f'<small class="{"up" if gap > 0 else "down"}">{"+" if gap >= 0 else "−"}{abs(gap):,}円</small>' if t else "") + '</td>'
                            + "".join(_cmp_td(sm, k_) for k_ in ("prev", "week")) +
                            f'<td class="sb-sp" data-l="30日">{spark(sm.get("points") or [], 160, 40)}'
                            f'<a class="sb-more" href="/{series_path(g, x)}#souba">詳しい相場<span aria-hidden="true"> ›</span></a></td></tr>'))
            if rows:
                rows.sort(key=lambda r: -r[0])
                secs.append(f'<section class="sb-list" data-g="{g}"><h2>{escape(GAME_SHORT[g])}の{"過去の弾の" if old else ""}BOX相場</h2>'
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
                 '定価との差も一緒に並べています。「詳しい相場」を押すと、1か月前・1年前との比較、大きいグラフ、その弾の主要カードの相場を見られます。</p></div>')
        # --- LINEオープンチャットの案内（/line/）：全国の入口ルームと地方ごとのルーム ---
        st_ = load_settings()
        rooms = [(r, (u or "").strip()) for r, u in (st_.get("line_rooms") or {}).items()]
        main_u = (st_.get("line_openchat_url") or "").strip()
        if any(u.startswith("https://") for _, u in rooms) or main_u.startswith("https://"):
            cards = "".join(
                (f'<a class="line-room" href="{escape(u)}" target="_blank" rel="noopener"><b>LINE</b><span><strong>【{escape(r)}】トレカ販売情報共有</strong>'
                 f'<small>{escape("・".join(p_.replace("県", "").replace("府", "").replace("都", "") for p_, rr in REGION_OF.items() if rr == r))}</small></span></a>')
                if u.startswith("https://") else f'<div class="line-room off"><b>LINE</b><span><strong>【{escape(r)}】</strong><small>準備中</small></span></div>'
                for r, u in rooms)
            main_c = (f'<a class="line-room main" href="{escape(main_u)}" target="_blank" rel="noopener"><b>LINE</b><span><strong>【ポケモン&amp;ワンピース】トレカ販売情報ナビ</strong>'
                      f'<small>全国向け。どの地域のルームに入るか迷ったらここ</small></span></a>') if main_u.startswith("https://") else ""
            body_l = ('<div class="guide"><p>地域ごとのLINEオープンチャットで、近くの人と「どこで買えた」「どこで抽選をやっている」を<b>リアルタイムで共有</b>できます（テスト中）。'
                      '住んでいる地域のルームに参加してください。</p>'
                      '<p><b>参加のしかた</b>：ボタンを押すと「トレカ販売情報ナビ」が開きます。参加したあと、<b>サブトークルームから参加したい地域のルーム</b>を選んでください。</p></div>'
                      f'<div class="line-rooms">{main_c}{cards}</div>'
                      '<p class="ch-note">※オープンチャットはLINEのサービスです。ルールを守って参加してください。転売目的の売買の呼びかけはご遠慮ください。</p>')
            write("line/", {"game": games[0], "channel": "store", "subset": True}, {
                "title": "地域ごとのLINEオープンチャット（トレカ販売情報共有）｜トレカ抽選ナビ",
                "desc": "ポケカ・ワンピースカードの販売・抽選情報を、北海道・東北／関東／中部／近畿／中国・四国／九州・沖縄の地域ごとのLINEオープンチャットでリアルタイムに共有できます。",
                "summary": "", "h1": "地域ごとのLINEオープンチャット", "h1_tag": "現在テスト運行中",
                "lead": "地域ごとのLINEオープンチャットの一覧です。下には、締切が近い店頭抽選を載せています。",
                "aff": body_l, "links": _menu(items, games, games[0]), "root": "/"},
                _soon([i for i in items if i["game"] == games[0] and i.get("channel") == "store"]), [("トップ", ""), ("LINEオープンチャット", "line/")])
        write("souba/", {"game": games[0], "subset": True}, {
            "title": f"ポケカ・ワンピースカードBOX相場一覧【{_md(latest) if latest else md}更新】定価との差・前日比・1週間の推移｜トレカ抽選ナビ",
            "desc": f"ポケカ・ワンピースカードの未開封BOXの相場（スニダンの取引価格）を毎日更新。定価との差、前日比、1週間比、30日の値動きのグラフ、海外（TCGplayer）の相場も一覧で比べられます。",
            "summary": "", "faq": faq_s,
            "h1": "ポケカ・ワンピースカード BOX相場一覧",
            "lead": "スニダンで成立した取引の値段（1個の取引のその日の平均）をもとにしたBOXの相場です。下には締切が近いポケカの抽選を載せています。",
            "aff": intro + _sb_tabs([g for g in games if any(f'data-g="{g}"' in x_ for x_ in secs)]) + "".join(secs), "links": _menu(items, games, games[0]), "root": "/",
            "upd": ("相場の更新 ", souba_raw["updated"]) if souba_raw.get("updated") else None},
            _soon([i for i in items if i["game"] == games[0]]), [("トップ", ""), ("BOX相場", "souba/")])

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
                        (f'<a href="/{series_path(g_, n_)}">{escape(n_)}</a>（{c_}件）' if series_path(g_, n_) in _SER_WRITTEN else f'{escape(n_)}（{c_}件）') for n_, c_ in v["series"]) + "</li>")
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
                                                ("レシート", "レシート" in (i.get("tags") or [])),
                                                ("お店のクレカ", "お店のクレジットカード" in __import__("common").needs_of(i)[0])) if ok]
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
            c_k = chain_of(r["store"])
            name = (f'<a href="/{sp}">{escape(r["store"])}</a>' if sp in _sreg else
                    f'<a href="{_cgp(c_k, r["game"]) if r.get("game") in GAME_SLUG else f"/chain/{c_k}/"}">{escape(r["store"])}</a>' if c_k else escape(r["store"]))
            if r.get("series") and r.get("game") in GAME_SLUG:  # 結果の行から、その弾のページ（いま買える方法・次の抽選）へ（11/7 Fable：/kekka/ が行き止まり）
                x_k = (canon_series(r["game"], r["series"]) or [r["series"]])[0]
                if series_path(r["game"], x_k) in _SER_WRITTEN:
                    r = dict(r, _sl=f'<a href="/{series_path(r["game"], x_k)}">{escape(r["series"])} ›</a>')
            how = escape(r.get("check") or ("お店のお知らせ（告知の発表予定日）" if r.get("est") else "お店からの当落メール"))
            off = (f'<a href="{escape(r["check_url"])}" target="_blank" rel="noopener nofollow">確認ページ</a>'
                   if r.get("check_url") else "")
            return (f'<li><span class="kk-g kk-{escape(r["game"])}">{escape(GAME_SHORT.get(r["game"], ""))}</span>'
                    f'<b>{name}</b><span class="kk-s">{r.get("_sl") or escape(r.get("series") or "")}</span>'
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
        write("kekka/", {"game": games[0], "subset": True}, {
            "title": f"ポケカ・ワンピースカードの抽選結果・当選発表まとめ【{md}更新】｜トレカ抽選ナビ",
            "desc": "ポケカ・ワンピースカードの抽選結果（当選発表）が出たお店と、これから結果が出るお店を日付ごとにまとめています。確かめ方（メール・アプリなど）も。",
            "summary": "", "h1": "抽選結果・当選発表のまとめ",
            "lead": "結果が出たお店・これから結果が出るお店を日付ごとにまとめています。下には締切が近い抽選を載せています。",
            "aff": "".join(h), "links": _menu(items, games, games[0]), "root": "/"},
            _soon([i for i in items if i["game"] == games[0]]), [("トップ", ""), ("抽選結果", "kekka/")])
        (out / "results.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 当選率（/tousenritsu/）：応募したリストの「当選した／落選した」の報告から（11/7）---
    if items and sample is None:
        wr = load_json("winrates.json", {})
        by_c, by_x, tot_w, tot_n = {}, {}, 0, 0
        for k_, v_ in wr.items():
            n_, w_ = int(v_.get("n") or 0), int(v_.get("w") or 0)
            if not n_:
                continue
            tot_w, tot_n = tot_w + w_, tot_n + n_
            c_ = chain_of(v_.get("s")) or ""
            nm_ = CHAIN[c_][1] if c_ else (v_.get("s") or "その他")
            a_ = by_c.setdefault(nm_, [0, 0, set()])
            a_[0] += w_; a_[1] += n_; a_[2].add(k_)
            if v_.get("x"):
                b_ = by_x.setdefault(v_["x"][:40], [0, 0])
                b_[0] += w_; b_[1] += n_
        def _tbl(d, head):
            rs = sorted(((k_, w_, n_) for k_, (w_, n_, *_r) in d.items() if n_ >= 3), key=lambda t: (-t[2], t[0]))
            if not rs:
                return ""
            return (f'<h2>{head}</h2><table class="wr"><tr><th>{"お店" if "お店" in head else "商品"}</th><th>報告</th><th>当選率</th></tr>' +
                    "".join(f'<tr><td>{escape(k_)}</td><td>{n_}人</td><td>' + (f'<b>{w_ * 100 // n_}%</b>（{w_}人）' if n_ >= 5 else '<small>報告5人から表示</small>') + '</td></tr>'
                            for k_, w_, n_ in rs[:60]) + '</table>')
        body_w = (f'<article class="guide"><p>「応募したリスト」で<b>当選した／落選した</b>を押してもらった報告から、お店・商品ごとの当選率を出しています。'
                  f'いまの報告は<b>{tot_n}人分</b>（当選{tot_w}人）です。報告が5人以上集まったものから当選率を表示します。</p>'
                  + _tbl(by_c, "お店（チェーン）ごとの当選率") + _tbl(by_x, "商品ごとの当選率") +
                  '<h2>報告のしかた</h2><ol><li>抽選の一覧や個別ページで「☐ 応募した」を押す</li><li>結果が出たら<a href="/mylist/">応募したリスト</a>を開いて「🎉 当選した」か「落選した」を押す</li></ol>'
                  '<p class="note">※報告は名前やメールアドレスなしで、抽選ごとの人数だけを数えています。応募した人のうち報告してくれた人の割合なので、実際の倍率とは違います。目安としてご覧ください。</p></article>')
        write("tousenritsu/", {"game": games[0], "subset": True}, {
            "title": "ポケカ・ワンピースカード抽選の当選率（お店別・商品別）｜みんなの当選報告から｜トレカ抽選ナビ",
            "desc": f"ポケカ・ワンピースカードの抽選の当選率を、応募した人の当選・落選の報告からお店（チェーン）別・商品別にまとめています。いまの報告は{tot_n}人分。",
            "summary": "", "h1": "抽選の当選率（みんなの当選報告から）",
            "lead": "お店・商品ごとの当選率を、応募した人の報告から集計しています。下には締切が近い抽選を載せています。",
            "aff": body_w, "links": _menu(items, games, games[0]), "root": "/",
            "noindex": tot_n < 20},  # 報告が少ないうちは検索に出さない
            _soon([i for i in items if i["game"] == games[0]]), [("トップ", ""), ("当選率", "tousenritsu/")])

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
                 '受付中の抽選の数は1日6回更新しています。弾の名前を押すと、その弾の抽選の一覧に進めます。</p>']
            h.append(cal_sub_html(site, games))
            # 11/3 ユーザー指摘：下の一覧が「発売日」の一覧だと一目でわかるように見出しと説明を付ける
            h.append('<div class="cal-head"><b>📦 新弾・新商品の発売日一覧</b>'
                     '<p>日付は<strong>発売日</strong>です（過去2か月〜これから発売の弾）。「抽選 受付中〇件」を押すと、その弾の抽選の一覧が見られます。</p></div>')
            cur_m, faq_c = "", []
            for r_, g, x, inf, n_ in rows_c:
                m_ = r_[:7]
                if m_ != cur_m:
                    if cur_m:
                        h.append("</ul>")
                    h.append(f"<h2>{int(m_[:4])}年{int(m_[5:7])}月</h2><ul class=\"cal-list\">")
                    cur_m = m_
                d_ = _dtm.date.fromisoformat(r_)
                # 注意：ここで tag という名前を使うと、build全体のAmazonのタグが上書きされる（11/6 修正）
                new_b = '<span class="cal-new">発売前</span>' if r_ > today_c else ""
                lot = f'<a class="cal-n" href="/{series_path(g, x)}">抽選 受付中{n_}件</a>' if n_ else '<span class="cal-n none">抽選情報待ち</span>'
                # 発売前の弾は、楽天とAmazonで予約・在庫を探せるリンクを並べる（11/6 ユーザー指示：楽天とのバランスを見てAmazonも）
                q_ = f"{s['game_names'][g]} {x}"
                dd_ = (_dtm.date.fromisoformat(r_) - _dtm.date.fromisoformat(today_c)).days
                buy_ = ((f'<span class="cal-buy">あと{dd_}日で発売｜定価で予約：' + (f'<a href="{escape(_rakb(q_, raff))}" {_REL} data-pl="calendar">楽天ブックス</a>' if raff else "")
                         + (f'<a href="{escape(_amz(q_, tag))}" {_REL} data-pl="calendar">Amazon</a>' if tag else "") + ' <span class="ad-pr">PR</span></span>')
                        if r_ > today_c and (raff or tag) else "")
                h.append(f'<li><time datetime="{r_}">{d_.month}/{d_.day}({WEEK[d_.weekday()]})<small class="cal-rl">発売</small></time>'
                         f'<span class="badge gm g-{g}">{escape(GAME_SHORT[g])}</span>{new_b}'
                         f'<a class="cal-t" href="/{series_path(g, x)}">{escape(x)}</a>'
                         f'<small>{escape(inf.get("type") or "")}' + (f'｜{escape(inf["price"])}' if inf.get("price") else "") + f'</small>{lot}{buy_}</li>')
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
                # 11/8 Fable：「ポケカ 発売日 2026」で探す人に、年の一覧だと伝わるタイトルに
                "title": f"ポケカ・ワンピースカード 発売日一覧 {now().year}年〜{now().year + 1}年｜新弾スケジュールと定価・抽選【{now().month}月更新】｜トレカ抽選ナビ",
                "desc": "ポケカ・ワンピースカードの新弾・新商品の発売日と希望小売価格を月ごとにまとめたカレンダー。発売前の弾の抽選・予約の受付状況も1日6回更新。",
                "summary": "", "faq": faq_c or None, "h1": f"ポケカ・ワンピースカード 発売日一覧（{now().year}〜{now().year + 1}年）",
                "lead": "新弾の発売日・定価・抽選の受付状況をまとめています。下には発売前の弾の受付中の抽選を載せています。",
                "aff": "".join(h), "links": _menu(items, games, games[0]), "root": "/"}, up_items,
                [("トップ", ""), ("発売日カレンダー", "calendar/")])

    def _top_ad(sub):
        """お店・チェーンのページの広告（11/8 Fable：検索から来る人の多いページに広告が1つもなかった）。
        そのページでいちばん多い弾の商品と、定価・相場のものさし。弾ページと同じ見た目・PR表記"""
        if not sub or sample is not None:
            return ""
        from collections import Counter as _C
        cnt = _C((i["game"], x_) for i in sub if i["game"] in GAME_SLUG for x_ in (i.get("sers") or ([i["series"]] if i.get("series") else [])))
        if not cnt:
            return ""
        (g_, x_), _n = cnt.most_common(1)[0]
        nm_ = s["game_names"][g_]
        rr_ = rk.get(f"{g_}|{x_}") or {}
        inf_ = (_ser_cfg()["info"].get(g_) or {}).get(x_) or {}
        return (_product_ad(x_, nm_, rr_, tag, raff, inf_.get("release"))
                + _price_anchor(x_, nm_, souba_sm.get(f"{g_}|{x_}"), tag, raff, inf_.get("release"), g_))

    def _lose_ad(past_rows):
        """受付中が0件のお店：前回の抽選の弾を、いま手に入れる方法"""
        if not past_rows or sample is not None:
            return ""
        g_l = past_rows[0].get("g")
        if g_l not in GAME_SLUG:
            return ""
        gx_ = guess_series(g_l, past_rows[0].get("p") or "")
        x_l = (canon_series(g_l, gx_) or [None])[0] if gx_ else None
        return _after_lose_ad(x_l, s["game_names"][g_l], souba_sm.get(f"{g_l}|{x_l}"), tag, raff, None, g_l) if x_l else ""

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
        r.update(name=_alias_of(i["store"]), last=today_s, game=r.get("game") or i["game"])
        if i.get("channel") == "store" and i.get("area"):
            r["area"] = i["area"]
    # お店ごとの抽選の履歴（終わった抽選も1年分残す。「〇〇店 抽選」で探す人に、前回いつ・何の抽選だったかを見せる）
    hist = {} if sample is not None else load_json("store_history.json", {})
    # 11/8 Fable：お店のアドレスの決め方が変わったとき（チェーン追加など）、履歴が前のアドレスのまま残って
    # 同じお店のページが2つできていた（平和堂など15店）。履歴も今のアドレスにまとめ、前のアドレスは転送する
    _fixed = {}
    for sp_, h_ in hist.items():
        nk_ = store_path(h_.get("name") or "")
        if nk_ != sp_:
            store_moves["/" + sp_] = "/" + nk_
            reg.pop(sp_, None)
        t_ = _fixed.setdefault(nk_, {"name": h_.get("name"), "items": {}})
        for k_, v_ in (h_.get("items") or {}).items():
            t_["items"].setdefault(k_, v_)
    hist = _fixed
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
            xs = item_series(it["game"], it.get("series"), it.get("product")) if it.get("series") else []
            if not xs and guess_series(it["game"], it.get("product")):
                xs = [guess_series(it["game"], it.get("product"))]
            old_a = (h["items"].get(k) or {}).get("a")
            h["items"][k] = {"p": "・".join(xs) or (it.get("product") or "")[:60], "g": it["game"],
                             "e": (it.get("end") or "")[:16], "f": (it.get("found_at") or "")[:10],
                             "c": "store" if it.get("channel") == "store" else "online",
                             # 応募のしかた・条件（お店ページの「よくある抽選の形」に使う）
                             "m": how_of(it), "id": it.get("id_check"), "mem": it.get("member"),
                             "rq": [w for w in __import__("common").needs_of(it)[0] if w not in ("本人確認", "お店の会員カード", "会員登録")] +
                                   (["X（旧Twitter）のフォロー"] if re.search("フォロー", " ".join(it.get("tags") or []) + " " + (it.get("conditions") or "") + " " + (it.get("method") or "")) else [])}
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
    # お店の住所（店頭抽選の応募ページから読み取ったもの）。同じお店で住所が食い違う時は載せない
    if sample is None:
        addrs = {}
        for it in load_json("lotteries.json", {}).values():
            if it.get("address") and it.get("channel") == "store" and it.get("store") and it.get("status") not in ("duplicate", "rejected"):
                addrs.setdefault(store_path(it["store"]), {})[normalize(it["address"])] = it["address"]
        for k, v in reg.items():
            a_ = addrs.get(k)
            if a_ and len(a_) == 1:
                v["address"] = next(iter(a_.values()))
            elif a_:
                v.pop("address", None)
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
            _links("同じチェーン", ([(f"{CHAIN[c][1]}の{GAME_SHORT[g0]}抽選をすべて見る", _cgp(c, g0))] if _cgp(c, g0) != f"/chain/{c}/" else [])
                   + [(f"{CHAIN[c][1]}の抽選をすべて見る", f"/chain/{c}/")]) if c else "")
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
        addr_html = ""
        # このお店のよくある抽選の形（応募方法・受け取り・本人確認・会員・そのほかの条件）
        hv = [v for v in (hist.get(path) or {}).get("items", {}).values() if v.get("m")]
        trend_html = ""
        if len(hv) >= 2:
            def _cnt(vals):
                d = {}
                for x in vals:
                    d[x] = d.get(x, 0) + 1
                return sorted(d.items(), key=lambda t: -t[1])
            n_ = len(hv)
            how = "・".join(f"{k}応募{c_}回" for k, c_ in _cnt(v["m"] for v in hv))
            rec_ = _cnt("店頭受取" if v["c"] == "store" else "通販（発送）" for v in hv)
            idv = [v["id"] for v in hv if v.get("id") is not None]
            memv = [v["mem"] for v in hv if v.get("mem")]
            rqv = _cnt(w for v in hv for w in (v.get("rq") or []))
            li = [f"<li><b>応募方法</b>：{escape(how)}</li>",
                  f"<li><b>受け取り</b>：{escape('・'.join(f'{k}{c_}回' for k, c_ in rec_))}</li>"]
            ask = "わからなかった抽選は、応募ページで確認してください"
            if idv:
                yes = sum(1 for x in idv if x)
                li.append(f"<li><b>本人確認</b>：" + (f"必要だった抽選が{yes}回（確認できた{len(idv)}回のうち）" if yes else f"不要（確認できた{len(idv)}回）") +
                          (f"<small>（{n_ - len(idv)}回は{ask}）</small>" if len(idv) < n_ else "") + "</li>")
            else:
                li.append("<li><b>本人確認</b>：応募ページで確認してください</li>")
            if memv:
                mm = {"card": "お店の会員カードが必要", "account": "会員登録が必要", "none": "会員登録なしで応募できた"}
                li.append("<li><b>会員</b>：" + escape("・".join(f"{mm.get(k, k)}{c_}回" for k, c_ in _cnt(memv))) +
                          (f"<small>（{n_ - len(memv)}回は{ask}）</small>" if len(memv) < n_ else "") + "</li>")
            else:
                li.append("<li><b>会員</b>：応募ページで確認してください</li>")
            li.append("<li><b>そのほかの条件</b>：" + (escape("・".join(f"{k}（{c_}回）" for k, c_ in rqv)) if rqv else "応募ページで確認してください") + "</li>")
            trend_html = (f'<section class="hist"><h2>{escape(name)}のよくある抽選の形<small>過去{n_}回の抽選から</small></h2><ul>{"".join(li)}</ul>'
                          '<p class="note">※トレカ抽選ナビが見つけた抽選の集計です。条件は抽選ごとに変わるので、応募前に必ずお店の告知をご確認ください。</p></section>')
            top_how = _cnt(v["m"] for v in hv)[0][0]
            faq_s.append((f"{name}の抽選はどうやって応募しますか？",
                          f"トレカ抽選ナビで確認できた{n_}回の抽選では、{how}でした。いちばん多いのは{top_how}応募です。"))
            if idv:
                yes = sum(1 for x in idv if x)
                faq_s.append((f"{name}の抽選に本人確認は必要ですか？",
                              (f"確認できた{len(idv)}回のうち{yes}回は本人確認が必要でした。" if yes else f"確認できた{len(idv)}回はどれも本人確認は不要でした。") +
                              "抽選ごとに変わることがあるので、応募ページで確認してください。"))
            else:
                faq_s.append((f"{name}の抽選に本人確認は必要ですか？", "トレカ抽選ナビでは確認できていません。応募ページで確認してください。"))
        if r.get("address"):
            from address import maps_url
            addr_html = (f'<p class="ann"><b>📍 住所</b>：{escape(r["address"])} '
                         f'<a href="{escape(maps_url(name, r["address"]))}" target="_blank" rel="noopener">Googleマップで見る</a></p>')
            faq_s.append((f"{name}の場所はどこですか？", f"{name}の住所は{r['address']}です（抽選の告知ページに書かれていた住所です）。"))
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
            "title": (f"{name}の{words}抽選 受付中{len(si)}件【{md}更新】" + (f"締切{_fmt(min(si, key=lambda i: i.get('end') or '9')['end'])}" if any(i.get("end") for i in si) else "")
                      if si else f"{name}の{words}抽選｜" + (f"前回{_d(past[0])}締切「{past[0]['p']}」・" if past else "") + "応募方法") + "｜トレカ抽選ナビ",
            "desc": ((f"【{md}更新】{where}" + summary(si, f"{name}の{words}の抽選").replace("現在受付中の", "いま受付中の") + "応募方法・本人確認や会員の条件もまとめています。") if si else
                     f"{name}{where}の{words}の抽選情報。いま受付中の抽選はありません。" + (f"前回は{_d(past[0])}締切の「{past[0]['p']}」でした。" if past else "") +
                     "これまでの抽選・応募方法・受け取り方をまとめ、新しい抽選が始まり次第ここに載ります。"),
            "summary": summary(si, f"{name}の抽選"),
            "h1": f"{name}の抽選情報", "lead": lead,
            "aff": (_rec_note(CHAIN[c][1]) if c and CHAIN[c][3] else "") + ("" if si else addr_html + trend_html + hist_html + _lose_ad(past)),
            "supply_bottom": _top_ad(si),
            "info_html": addr_html + trend_html + hist_html if si else "",  # 受付中があれば一覧の下に、なければ上に
            "faq": faq_s or None,
            "links": links, "root": "/",
            # 11/8 Fable技術：地名だけの店名（「岡南」「西大寺」など。チェーン名が読み取れなかった）は中身が薄いので検索に出さない
            "noindex": (not si and len(past) < 3 and not _recent60(past)) or bool(re.fullmatch(r"[一-龯]{1,4}店?", re.sub(r"[（(].*?[）)]", "", r.get("name") or "").strip())) and not c},
            si,  # 受付中なし・過去2件以下・60日以上抽選なしのお店だけ検索に出さない（11/7。平和堂などを巻き添えにしない）
            [("トップ", ""), ("店舗一覧", "store/"), (name, path)])

    def _cs_chips(slug, g, cig):
        """チェーン×ゲームのページ：弾ごとのページへ（受付中の件数つき）"""
        lst = [(x, pth) for (c, g2, x), pth in CS_PAGES.items() if c == slug and g2 == g]
        if not lst:
            return ""
        lst.sort(key=lambda t: -sum(1 for i in cig if in_ser(i, t[0])))
        return ('<details class="ser-areas" open><summary>弾ごとに見る</summary><nav aria-label="弾ごとに見る">' +
                "".join(f'<a href="/{p}">{escape(x)}<span>{sum(1 for i in cig if in_ser(i, x))}</span></a>' for x, p in lst[:12]) + "</nav></details>")

    def write_cs(slug, cname, g, x, pth, act, gdc, big):
        """チェーン×弾のページ（/chain/tsutaya/pokeka/hadou-seeker/）。受付中＋これまでが3件以上の組だけ（plan_cs_pages）"""
        from collections import Counter
        sh = GAME_SHORT[g]
        past = ser_past(g, x, slug)
        info_ = (_ser_cfg()["info"].get(g) or {}).get(x) or {}
        rel_ = str(info_.get("release") or "")[:10]
        on_ = sum(1 for i in act if i.get("channel") != "store")
        prefs = Counter(i["area"] for i in act if i.get("channel") == "store" and i.get("area"))
        soon = min((i for i in act if i.get("end")), key=lambda i: i["end"], default=None)
        n_st = len({i.get("store") for i in act})
        # 締切→結果発表の日数（5件以上わかるときだけ「目安」）
        import datetime as _dd
        dd = []
        for t in past:
            a_, e_ = (t[0].get("a") or "")[:10], t[0]["e"][:10]
            try:
                if a_ and e_:
                    d_ = (_dd.date.fromisoformat(a_) - _dd.date.fromisoformat(e_)).days
                    if 0 <= d_ <= 30:
                        dd.append(d_)
            except ValueError:
                pass
        ann_ = f"締切のおよそ{_median(dd)}日後（これまでの{len(dd)}件から）" if len(dd) >= 5 else ""
        idk = [t for t in past if t[0].get("id") is not None]
        idn = sum(1 for t in idk if t[0].get("id"))
        post = [t for t in past if rel_ and t[0]["e"][:10] >= rel_]
        facts = [("いま受付中", f"{len(act)}件（{n_st}店舗・ネット{on_}件・店頭{len(act) - on_}件）" if act else "なし（新しい抽選が見つかり次第ここに載ります）")]
        if soon:
            facts.append(("締切が一番近い抽選", f"{_sname(soon['store'])}（{_fmt(soon['end'])}）"))
        if prefs:
            facts.append(("店頭抽選が多い都道府県", "、".join(f"{a}（{n}件）" for a, n in prefs.most_common(3))))
        facts.append(("これまでの抽選（受付終了）", f"{len(past)}件" + (f"（前回 {_md_(past[0][0]['e'])}締切・{_sname(past[0][1])}）" if past else "")))
        if rel_ and rel_ <= now().date().isoformat():
            facts.append(("発売日のあとの抽選", f"{len(post)}件（発売日 {jdate(rel_)}）"))
        if ann_:
            facts.append(("結果発表の目安", ann_))
        if len(idk) >= 3:
            facts.append(("本人確認が必要だった抽選", f"条件が書かれていた{len(idk)}件のうち{idn}件"))
        fact_html = (f'<section class="sinfo"><h2>{escape(cname)}の「{escape(x)}」抽選のまとめ<small>{escape(upd_hm)}時点</small></h2><table>'
                     + "".join(f"<tr><th>{escape(a_)}</th><td>{escape(b_)}</td></tr>" for a_, b_ in facts) + "</table></section>")
        hist_ = (f'<section class="hist"><h2>{escape(cname)}の「{escape(x)}」これまでの抽選<small>{len(past)}件</small></h2>' + hist_table(past, limit=15)
                 + '<p class="note">※トレカ抽選ナビが見つけた抽選（受付終了）です。</p></section>') if past else ""
        gd_ = (f'<p class="cs-guide">📘 <a href="/guide/{escape(gdc["slug"])}/">{escape(cname)}の抽選の応募のしかた・結果の確かめ方 →</a></p>' if gdc else "")
        others = [(CHAIN[c2][1], "/" + p2) for (c2, g2, x2), p2 in CS_PAGES.items() if g2 == g and x2 == x and c2 != slug][:12]
        nav_ = (f'<p class="cs-nav"><a href="/{series_path(g, x)}">「{escape(x)}」の抽選をすべて見る（全部のお店） ›</a>'
                f'<a href="/chain/{slug}/{GAME_SLUG[g]}/">{escape(cname)}の{escape(sh)}抽選をすべて見る ›</a></p>')
        oth_ = _links(f"ほかのお店の「{x}」の抽選", others) if others else ""
        faq = [(f"{cname}の「{x}」の抽選はいま受付中ですか？",
                (f"いま受付中の抽選は{len(act)}件（{n_st}店舗）です" + (f"。締切が一番近いのは{_sname(soon['store'])}（{_fmt(soon['end'])}）です。" if soon else "。")) if act else
                ("いま受付中の抽選はありません。" + (f"前回は{_md_(past[0][0]['e'])}締切（{_sname(past[0][1])}）でした。" if past else "") + "新しい抽選が見つかり次第、このページに自動で載ります。"))]
        if ann_:
            faq.append((f"{cname}の「{x}」の抽選の結果はいつ出ますか？", f"これまでの抽選では、結果発表は{ann_}でした。抽選ごとに違うので、告知を確認してください。"))
        if len(idk) >= 3:
            faq.append((f"{cname}の「{x}」の抽選に本人確認は必要ですか？", f"条件が書かれていた{len(idk)}件のうち{idn}件で本人確認が必要でした。"))
        md_ = f"{now().month}/{now().day}"
        ttl = (f"{cname}の「{x}」抽選 受付中{len(act)}件【{md_}更新】店舗・締切・応募方法｜トレカ抽選ナビ" if act else
               f"{cname}の「{x}」抽選｜" + (f"前回{_md_(past[0][0]['e'])}締切・" if past else "") + f"これまで{len(past)}件・応募方法｜トレカ抽選ナビ")
        desc = (f"【{md_}更新】{cname}でいま受付中の{sh}「{x}」の抽選は{len(act)}件（{n_st}店舗）。" + (f"締切が一番近いのは{_sname(soon['store'])}（{_fmt(soon['end'])}）。" if soon else "")
                + f"これまでの抽選{len(past)}件の締切・結果発表も表にしています。" if act else
                f"【{md_}更新】{cname}の{sh}「{x}」の抽選の情報。いま受付中の抽選はありません。これまでの抽選{len(past)}件"
                + (f"（前回{_md_(past[0][0]['e'])}締切）" if past else "") + "と応募のしかたをまとめ、新しい抽選が始まり次第ここに載ります。")
        write(pth, {"game": g, "chain": slug, "series": x, "channel": "store" if sum(1 for i in act if i.get("channel") == "store") * 2 > len(act) else "online"}, {
            "title": ttl, "desc": desc, "h1": f"{cname}の「{x}」抽選情報",
            "lead": (f"{cname}でいま受付中の「{x}」の抽選を、店舗別・締切が近い順にまとめています。" if act else
                     f"{cname}でいま受付中の「{x}」の抽選はありません。これまでの抽選と応募のしかたをまとめています。"),
            "summary": summary(act, f"{cname}の「{x}」の抽選"), "faq": faq,
            "aff": nav_ + fact_html + gd_ + ("" if act else hist_ + oth_),
            "info_html": (hist_ + oth_) if act else "",
            "supply_bottom": (_top_ad(act) if act else _after_lose_ad(x, s["game_names"][g], souba_sm.get(f"{g}|{x}"), tag, raff, None, g)),
            "links": _menu(items, games, g), "root": "/"}, act,
            [("トップ", ""), ("店舗一覧", "store/"), (cname, f"chain/{slug}/"), (sh, f"chain/{slug}/{GAME_SLUG[g]}/"), (x, pth)])

    # --- チェーンごとのページ（/chain/xxx/）---
    chain_stores = {}
    for path, r in reg.items():
        c = chain_of(r["name"])
        if c:
            chain_stores.setdefault(c, []).append((path, r))
    chain_links = []
    import yaml as _yaml
    _gp = Path(__file__).resolve().parent.parent / "config" / "guides.yaml"
    _guides = ((_yaml.safe_load(_gp.read_text(encoding="utf-8")) or {}).get("guides") or []) if _gp.exists() else []
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
        gdc = next((gd for gd in _guides if re.search(gd["store_re"], cname, re.I)
                    or any(re.search(gd["store_re"], r_["name"], re.I) for _, r_ in chain_stores.get(slug, [])[:3])), None)

        def _trend(craw, gf=None):
            """チェーンの抽選の傾向（11/8：ゲームごとのページではそのゲームの抽選だけで数える）"""
            guide_c = ""
            faq_c, hw_s, idn, idk, ad_c, sers = [], "", 0, 0, None, {}
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
                ad_c = ann_days(v for h_ in hist.values() if chain_of(h_.get("name")) == slug for v in h_["items"].values() if not gf or v.get("g") == gf)
                if ad_c:
                    li.append(f"<li><b>結果発表の目安</b>：{escape(ann_text(ad_c))}</li>")
                if sers:
                    li.append("<li><b>多かった弾</b>：" + "、".join(f"{escape(k)}（{n}件）" for k, n in sorted(sers.items(), key=lambda kv: -kv[1])[:4]) + "</li>")
                guide_c = (f'<section class="hist"><h2>{escape(cname)}{escape("の" + GAME_SHORT[gf]) if gf else ""}の抽選の傾向<small>最近の{len(craw)}件から</small></h2><ul class="cg">' + "".join(li) +
                           '</ul><p class="note">※トレカ抽選ナビが見つけた最近の抽選から集計しています。応募の条件はお店・抽選ごとに違うので、必ず告知を確認してください。</p></section>')
            # 解説ページ（config/guides.yaml）があれば、要点と一緒にリンク（11/7：チェーンページを解説記事型に）
            if gdc:
                guide_c = (f'<section class="hist cguide"><h2>📘 {escape(cname)}の抽選の応募のしかた・結果の確かめ方</h2>'
                           f'<p>{gdc["intro"]}</p><ul>' + "".join(f'<li>{escape(sec["h"])}</li>' for sec in (gdc.get("sections") or [])[:5]) +
                           f'</ul><p><a href="/guide/{escape(gdc["slug"])}/"><b>{escape(cname)}の抽選のやり方を詳しく見る →</b></a></p></section>') + guide_c

            return guide_c, hw_s, idn, idk, ad_c
        guide_c, hw_s, idn, idk, ad_c = _trend(craw)
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
        def _cd(v):
            d = parse_dt(v["e"])
            return f"{d.month}/{d.day}" if d else ""
        def _cp(v):
            p_ = re.sub(r"(ポケモンカードゲーム|ONE PIECEカードゲーム|ポケモンカード|MEGA|拡張パック|ブースターパック|エクストラブースター|1BOX|[「」『』／/])", " ", v["p"])
            return re.sub(r"\s+", " ", p_).strip() or "抽選"
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
        def _faqs(cpast, hw_s, idn, idk, ad_c):
            faq_c = []
            if cpast:
                yr = [t for t in cpast if t[0]["e"][:10] >= (now() - __import__("datetime").timedelta(days=365)).date().isoformat()]
                faq_c.append((f"{cname}のポケカ・ワンピースカードの抽選はいつありますか？",
                              f"トレカ抽選ナビで確認できた直近の抽選は、{_cd(cpast[0][0])}締切の{GAME_SHORT.get(cpast[0][0]['g'], '')}「{_cp(cpast[0][0])}」でした。"
                              f"過去1年で{len(yr)}件の抽選が見つかっています。新しい弾の発売の前後に抽選が行われることが多いです。"))
            if hw_s:
                faq_c.append((f"{cname}の抽選はどうやって応募しますか？", f"最近の抽選では、{hw_s}でした。抽選ごとに方法が違うので、必ず告知を確認してください。"
                              + (f"詳しくは「{cname}の抽選のやり方」のページをご覧ください。" if gdc else "")))
            if idk >= 3:
                faq_c.append((f"{cname}の抽選に本人確認は必要ですか？", f"条件が書かれていた{idk}件のうち{idn}件で本人確認が必要でした。抽選ごとに違うので、応募前に告知を確認してください。"))
            if ad_c:
                faq_c.append((f"{cname}の抽選の結果発表はいつですか？", f"{ann_text(ad_c)}。結果の確かめ方は抽選ごとに違います（メール・アプリ・店頭など）。"))
            return faq_c
        faq_c = _faqs(cpast, hw_s, idn, idk, ad_c)
        # ゲームごとのページ（/chain/xxx/pokeka/ など）：「ビックカメラ ワンピースカード 抽選」で探す人向け。上のタブで行き来できる
        hist_g = {g: [t for t in cpast if t[0]["g"] == g] for g in games}
        cg_list = [g for g in games if g in ("pokemon", "onepiece") and (any(i["game"] == g for i in ci) or hist_g[g])]
        words_c = "・".join(GAME_SHORT[g] for g in cg_list) or words
        def ctabs(cur):
            if not cg_list:
                return ""
            # 11/8 Fable：タブに受付中の件数（0件なら前回の締切日）を出して、着いた瞬間に状況がわかるように
            def _n(g):
                n = sum(1 for i in ci if i["game"] == g)
                return f"{n}件" if n else (f"前回{_cd(hist_g[g][0][0])}" if hist_g[g] else "0件")
            tb = [("すべて", f"/chain/{slug}/", cur is None, f"{len(ci)}件")] + [(GAME_TAB.get(g, GAME_SHORT[g]), f"/chain/{slug}/{GAME_SLUG[g]}/", cur == g, _n(g)) for g in cg_list]
            return ('<nav class="ctabs" aria-label="ゲームを選ぶ">' + "".join(
                f'<a href="{u}"{" aria-current=\"page\"" if on else ""}>{escape(t)}<span>{escape(n)}</span></a>' for t, u, on, n in tb) + '</nav>')
        for g in cg_list:
            cig = [i for i in ci if i["game"] == g]
            sh = GAME_SHORT[g]
            hg = hist_g[g]
            gguide, ghw, gidn, gidk, gad = _trend([v for v in craw if v.get("game") == g], g)
            gfaq = _faqs(hg, ghw, gidn, gidk, gad)
            chist_g = ""
            if hg:
                chist_g = (f'<section class="hist"><h2>{escape(cname)}の{escape(sh)}のこれまでの抽選<small>直近{min(len(hg), 20)}件</small></h2><ul>' +
                           "".join(f'<li><time>{_cd(v)}締切</time> <a href="/{sp_}">{escape(n_)}</a>｜「{escape(_cp(v))}」</li>' for v, n_, sp_ in hg[:20]) +
                           '</ul><p class="note">※トレカ抽選ナビが見つけた抽選です。新しい抽選が見つかり次第、このページに自動で追加されます。</p></section>')
            lead_g = (f"いま受付中の{cname}の{sh}の抽選は{len(cig)}件です。店舗別・締切が近い順にまとめています。" if cig else
                      f"{cname}で現在受付中の{sh}の抽選はありません。" + (f"前回は{_cd(hg[0][0])}締切の「{_cp(hg[0][0])}」の抽選でした。" if hg else "")
                      + "新しい抽選が見つかり次第、自動で追加されます。")
            write(f"chain/{slug}/{GAME_SLUG[g]}/", {"game": g, "chain": slug, "channel": "store" if sum(1 for i in cig if i.get("channel") == "store") * 2 > len(cig) else "online"}, {
                "title": _cg_title(cname, sh, cig, hg, md, _cd, _cp),
                "desc": _cg_desc(cname, sh, cig, hg, md, _cd, _cp),
                "summary": summary(cig, f"{cname}の{sh}の抽選"), "h1": f"{cname}の{sh}抽選情報", "lead": lead_g,
                "aff": ctabs(g) + _cs_chips(slug, g, cig) + (_rec_note(cname) if big else "") + (_ymall_box(s) if slug == "yamada" else "") + ("" if cig else gguide + chist_g),
                "supply_bottom": _top_ad(cig) + _supply_ad(sh, s["game_names"][g], tag, raff, prices, g),  # サプライの広告は一覧の後へ（11/7 Fable：まず中身）
                "info_html": (gguide + chist_g) if cig else "",
                "faq": [(q.replace("ポケカ・ワンピースカード", sh), a) for q, a in gfaq] or None,
                "links": _menu(items, games, g) + stl, "root": "/"}, cig,
                [("トップ", ""), ("店舗一覧", "store/"), (cname, f"chain/{slug}/"), (sh, f"chain/{slug}/{GAME_SLUG[g]}/")])
            # 11/8 Fable：チェーン×弾のページ（「TSUTAYA ハドウシーカー」「ビックカメラ 30th 抽選」で探す人の受け皿）
            for (c_, g_, x_), pth in sorted(CS_PAGES.items()):
                if c_ != slug or g_ != g:
                    continue
                write_cs(slug, cname, g, x_, pth, [i for i in cig if in_ser(i, x_)], gdc, big)
        # 受付中が0件のときは「前回の抽選」と「これまでの件数」を出す（検索結果で中身が分かるように。11/3 クリック0件の対策）
        _last = (f"前回は{_cd(cpast[0][0])}締切の「{_cp(cpast[0][0])}」。" if cpast else "")
        lose_c = ""  # 受付中が0件のチェーン：前回の抽選の弾を、いま買える方法（11/7）
        if not ci and cpast:
            g_l = cpast[0][0]["g"]
            gx_ = guess_series(g_l, cpast[0][0]["p"]) if g_l in GAME_SLUG else None
            x_l = (canon_series(g_l, gx_) or [None])[0] if gx_ else None
            if x_l:
                lose_c = _after_lose_ad(x_l, s["game_names"][g_l], souba_sm.get(f"{g_l}|{x_l}"), tag, raff, None, g_l)
        write(f"chain/{slug}/", {"game": g0, "chain": slug, "channel": ch}, {
            "title": (f"{cname}の{words_c}抽選 受付中{len(ci)}件【{md}更新】店舗別・締切順" + (f"｜{len(sts)}店舗" if len(sts) >= 5 else "") if ci else
                      f"{cname}の{words_c}抽選｜" + (f"前回{_cd(cpast[0][0])}締切「{_cp(cpast[0][0])}」・" if cpast else "") + "応募方法・結果発表") + "｜トレカ抽選ナビ",
            "desc": (f"【{md}更新】" + summary(ci, f"{cname}の{words_c}の抽選").replace("現在受付中の", "いま受付中の") + "店舗別・締切順に、応募方法と本人確認・会員の条件もまとめています。" if ci else
                     f"【{md}更新】{cname}の{words}の抽選情報。いま受付中の抽選はありません。{_last}" +
                     (f"これまでに見つけた{len(cpast)}件の抽選" + ("と、応募のしかた・本人確認などの傾向" if guide_c else "") + "をまとめています。" if cpast else "") +
                     "新しい抽選が始まり次第、このページに自動で載ります。"),
            "summary": summary(ci, f"{cname}の抽選"), "h1": f"{cname}のポケカ・ワンピースカード抽選情報", "lead": lead,
            "aff": ctabs(None) + (_rec_note(cname) if big else "") + (_ymall_box(s) if slug == "yamada" else "") + ("" if ci else guide_c + chist + lose_c),
            "supply_bottom": _top_ad(ci),
            "info_html": (guide_c + chist) if ci else "",
            "faq": faq_c or None,
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
    inv_all = amazon_invites(items, tag) if tag else {}
    _chain_n, _ser_n, _chain_ng = {}, {}, {}  # いま受付中の抽選の数（終わった抽選のページから案内するため）
    for i in items:
        c0 = chain_of(i.get("store"))
        if c0:
            _chain_n[c0] = _chain_n.get(c0, 0) + 1
            _chain_ng[(c0, i["game"])] = _chain_ng.get((c0, i["game"]), 0) + 1
        if i.get("series"):
            _ser_n[(i["game"], i["series"])] = _ser_n.get((i["game"], i["series"]), 0) + 1
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
            aff = _product_ad(d["series"], s["game_names"][g], (rk if sample is None else {}).get(f"{g}|{d['series']}") or {}, tag, raff,
                              ((_ser_cfg()["info"].get(g) or {}).get(d["series"]) or {}).get("release"))
        elif d.get("series"):  # 受付が終わった抽選：落選した人・間に合わなかった人に「まだ買える方法」
            x_l = (canon_series(g, d["series"]) or [d["series"]])[0]
            inv_ = next((v["url"] for v in (inv_all.get(g) or []) if x_l and x_l in v["name"]), None)
            aff = _after_lose_ad(x_l, s["game_names"][g], souba_sm.get(f"{g}|{x_l}"), tag, raff, inv_, g)
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
        if c == "yamada":
            aff = _ymall_box(s) + aff
        if c:
            if _cgp(c, g) != f"/chain/{c}/":
                rel.insert(0, (f"{CHAIN[c][1]}の{short}抽選をすべて見る", _cgp(c, g)))
            rel.append((f"{CHAIN[c][1]}の抽選", f"/chain/{c}/"))
        if d.get("channel") == "store" and d.get("area") in PREF:
            rel.append((f"{d['area']}の店頭抽選", f"/{GAME_SLUG[g]}/area/{PREF[d['area']]}/"))
        # 今はないページ（抽選がなくなった弾・地域など）へのリンクは出さない
        rel = [(t, u) for t, u in rel if (out / u.strip("/") / "index.html").exists()]
        p = out / lp / "index.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        sbx = None
        if active and d.get("series"):
            x_ = (canon_series(g, d["series"]) or [d["series"]])[0]
            sm_ = souba_sm.get(f"{g}|{x_}")
            if sm_:
                dd, cc = _diff(sm_["price"], sm_["prev"][1] if sm_.get("prev") else None)
                sbx = {"name": x_, "price": _yen(sm_["price"]), "date": _md(sm_["date"]), "diff": dd, "cls": cc,
                       "url": "/" + series_path(g, x_) + "#souba"}
        if active and d.get("channel") == "store":
            aff = line_box(d.get("area")) + aff
        # 11/7 監査：受付は中央値4.5日と短く、1店舗だけの店頭抽選のページは検索に載る前に終わる＆中身が薄い。
        # 検索に出すのは「ネット抽選」と「大手チェーンの店頭抽選」だけ（1店舗だけの抽選はお店ページで受ける）
        c_ = chain_of(d.get("store"))
        l_index = d.get("channel") != "store" or bool(c_ and CHAIN[c_][3])
        nxt = None
        if not active:
            if c_ and _chain_ng.get((c_, g)) and (out / _cgp(c_, g).strip("/") / "index.html").exists():
                nxt = (f"{CHAIN[c_][1]}でいま受付中の{short}抽選を見る（{_chain_ng[(c_, g)]}件）", _cgp(c_, g))
            elif c_ and _chain_n.get(c_) and (out / "chain" / c_ / "index.html").exists():
                nxt = (f"{CHAIN[c_][1]}でいま受付中の抽選を見る（{_chain_n[c_]}件）", f"/chain/{c_}/")
            elif d.get("series") and _ser_n.get((g, d["series"])) and (out / series_path(g, d["series"]).strip("/") / "index.html").exists():
                nxt = (f"「{d['series']}」のいま受付中の抽選を見る（{_ser_n[(g, d['series'])]}件）", "/" + series_path(g, d["series"]))
            else:
                nxt = (f"いま受付中の{short}の抽選を見る", f"/{GAME_SLUG[g]}/")
        p.write_text(detail.render(d, site=site, path=lp, verify=verify, now_dt=now(), ended=not active,
                                   redirect=redirect, aff=aff, related=rel, updated=updated, souba=sbx, noindex=not l_index,
                                   next_link=nxt), encoding="utf-8")
        if active and l_index:
            urls.append((f"{site}/{lp}", (d.get("found_at") or updated)[:10]))
        if active:
            ics = detail.cal_ics(d, d.get("store") or "", detail.short_name(d), f"{site}/{lp}" if site else "")
            if ics:
                (p.parent / "shimekiri.ics").write_text(ics, encoding="utf-8")

    # 締切の購読カレンダー（/cal/xxx.ics）：一度登録すると、これからの締切が自動でカレンダーに入る。
    # 登録したアドレスが消えると困るので、抽選が0件でも全部のファイルを毎回つくる
    write_cal_feeds(out, items, site, games)

    # 応募したリスト（このブラウザの中だけの記録を一覧にする。検索・サイトマップには載せない）
    (out / "mylist").mkdir(parents=True, exist_ok=True)
    (out / "mylist" / "index.html").write_text(detail.mylist_page(site, raff=raff, tag=tag or "", souba={k: [v["price"], v.get("teika")] for k, v in souba_sm.items()}), encoding="utf-8")
    # 404.html が無いと Cloudflare Pages は無いURLにトップページを200で返す（ソフト404）。消えた抽選ページなどのため（11/7）
    # 11/9：大手の抽選の予告・受付開始のポストの予約表。Worker（rakuten-watch）が1分おきに読んで、時刻が来たものをXに出す
    try:
        from datetime import timedelta as _td
        _q = (load_json("x_meta.json", {}) or {}).get("big_queue") or {}
        _t = now()
        (out / "x-queue.json").write_text(json.dumps(
            [{"k": k, "at": v["at"], "text": v["text"]} for k, v in sorted(_q.items(), key=lambda kv: kv[1]["at"])
             if (parse_dt(v.get("at")) or _t) > _t - _td(hours=12)], ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print("x-queue.json を書けませんでした", e)
    (out / "404.html").write_text(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex"><title>ページが見つかりません｜トレカ抽選ナビ</title>'
        '<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:32px 16px;line-height:1.7;color:#222}a{color:#c8102e}</style></head>'
        '<body><h1>ページが見つかりません</h1><p>抽選の受付が終わり、ページを削除した可能性があります。</p>'
        '<p><a href="/">受付中の抽選一覧</a> ・ <a href="/pokeka/">ポケカ</a> ・ <a href="/onepiece/">ワンピースカード</a> ・ '
        '<a href="/store/">店舗一覧</a> ・ <a href="/calendar/">発売日カレンダー</a></p>'
        '<p id="nf-go" hidden>近いページへ移動しています… <a id="nf-a" href="/">こちら</a></p>'
        # 手打ちやAIが作った「ありそうなURL」用：親のページを順にさがして、近いページへ自動で移る（11/8）
        '<script>(function(){var p=location.pathname;if(/^\\/chain\\/?$/.test(p)){location.replace("/store/");return}'
        'var s=p.replace(/\\/+$/,"").split("/").filter(Boolean);if(!s.length)return;'
        'function go(u){document.getElementById("nf-go").hidden=false;document.getElementById("nf-a").href=u;location.replace(u)}'
        'function up(i,miss){if(i<0){go("/");return}var u="/"+s.slice(0,i).join("/")+(i?"/":"");'
        'fetch(u,{credentials:"omit"}).then(function(r){if(!r.ok||r.url.indexOf("404")>-1)return up(i-1,s[i-1]);'
        'return r.text().then(function(h){if(miss&&miss.length>3){var re=/href="(\\/[^"#?]+)"/g,m,best=null;'
        'while((m=re.exec(h))){var l=m[1],t=l.replace(/\\/+$/,"").split("/").pop();'
        'if(l.indexOf(u)===0&&t.length>3&&(t.indexOf(miss)>-1||miss.indexOf(t)>-1)){best=l;break}}if(best)return go(best)}go(u)})})'
        '.catch(function(){go("/")})}up(s.length-1,s[s.length-1])})();</script></body></html>', encoding="utf-8")

    # 共通の画像（OGP・アイコン）と IndexNow の鍵ファイル
    import shutil
    for f in (ROOT / "src" / "static").glob("*"):
        shutil.copy(f, out / f.name)
    for rel_, txt_ in ASSETS.items():  # 共通のCSS・JS（名前に中身の指紋が入っているので、ずっとキャッシュしてよい）
        (out / rel_).parent.mkdir(parents=True, exist_ok=True)
        (out / rel_).write_text(txt_, encoding="utf-8")
    (out / "_headers").write_text("/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n"
                                  "/sw.js\n  Cache-Control: no-cache\n/push.js\n  Cache-Control: public, max-age=3600\n"
                                  "/manifest.webmanifest\n  Content-Type: application/manifest+json\n"
                                  "/og/*\n  Access-Control-Allow-Origin: *\n/x/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: no-cache\n", encoding="utf-8")
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
        # お店の前のアドレス（記号8けた）→ 読めるアドレス。11/8 Fable：前のアドレスは10/30の切り替えまでしか公開していないので、
        # それより前に見つかったお店だけ（全部書くと転送の上限2,000行に約10日で届く）
        first_seen = {}
        for h_ in hist.values():
            fs = min((v.get("f") or "9999") for v in (h_.get("items") or {}).values()) if h_.get("items") else "9999"
            nm_ = h_.get("name") or ""
            first_seen[nm_] = min(first_seen.get(nm_, "9999"), fs)
        for r in reg.values():
            nm_ = r.get("name") or ""
            if first_seen.get(nm_, "9999") >= "2026-10-30":
                continue
            o, n = old_store_path(nm_), store_path(nm_)
            if o != n:
                olds["/" + o] = "/" + n
        # お店のアドレスが変わった分（チェーン追加などで。11/8）。一度見つけた分は覚えておいて転送し続ける
        mv = load_json("store_moves.json", {})
        mv.update({o: n for o, n in store_moves.items() if not re.fullmatch(r"/store/[0-9a-f]{8}/", o)})
        for o in list(mv):  # A→B→C は A→C に
            n, seen = mv[o], {o}
            while n in mv and n not in seen:
                seen.add(n)
                n = mv[n]
            mv[o] = n
        mv = {o: n for o, n in mv.items() if o != n}
        save_json("store_moves.json", mv)
        olds.update(mv)
        olds["/teika/"] = "/"  # 「定価で買えるBOX」のページはやめた
        # 自動で見つけた弾の仮アドレス（/onepiece/op19/ など）→ あとで決めた読めるアドレス（11/8）
        for g_, m_ in ((load_json("newsets.json", {}) or {}).get("series") or {}).items():
            if g_ not in GAME_SLUG:
                continue
            for x_, v_ in (m_ or {}).items():
                if v_.get("slug") and series_path(g_, x_) != f"{GAME_SLUG[g_]}/{v_['slug']}/":
                    olds[f"/{GAME_SLUG[g_]}/{v_['slug']}/"] = "/" + series_path(g_, x_)
        if not (out / "chain" / "index.html").exists():
            olds["/chain/"] = "/store/"  # チェーン一覧は店舗一覧にある（11/8：手打ちのアクセスが404だった）
        # 転送先のページが無い行は書かない（11/8：ワンピの弾がポケカ側の別名に入っていた3行など）
        olds = {o: n for o, n in olds.items() if n == "/" or (out / n.strip("/") / "index.html").exists()}
        if len(olds) > 1900:
            print(f"注意：転送（_redirects）が{len(olds)}行。Cloudflare Pages の上限2,000行に近い")
        # 「/」なしの版は書かない（前のアドレスはいつも「/」付きで公開していた）
        (out / "_redirects").write_text("".join(f"{o} {n} 301\n" for o, n in sorted(olds.items())), encoding="utf-8")

    if sample is None and site:  # 海外向けページ（英語・繁体字・韓国語）11/7
        import intl
        for u_, lm0 in intl.build_intl(out, s, souba_raw, card_raw, _ser_cfg()["info"], site, now().date()):
            # 11/8 Fable：海外ページも「中身が変わった日」を更新日に（毎日全部「今日」だとGoogleが更新日を信用しなくなる）
            pth = u_[len(site):].lstrip("/")
            try:
                body_ = (out / pth / "index.html").read_text(encoding="utf-8")
                body_ = re.sub(r"<script[^>]*>.*?</script>|<time[^>]*>.*?</time>|¥[\d,]+|[\d,.]+\s*(?:만원|원)|(?:NT|HK)?\$[\d,.]+|[+-]?\d+%|Updated[^<]*|更新[^<]*|업데이트[^<]*", "", body_, flags=re.S)
                sig_ = sha(body_)
            except OSError:
                sig_ = ""
            prev = pmod.get(pth) or []
            lm_i = prev[1] if prev[:1] == [sig_] and len(prev) > 1 else today_iso
            pmod[pth] = [sig_, lm_i, prev[2] if len(prev) > 2 else today_iso]
            urls.append((u_, lm_i))
        # 11/8：日本語の弾ページ ⇔ 海外の弾ページを hreflang でつなぐ（同じ弾の別の言語版だとGoogleに伝える。両方向に書く）
        HL_ = [("en", "en"), ("zh-Hant", "zh-tw"), ("zh-TW", "zh-tw"), ("zh-HK", "zh-tw"), ("ko", "ko")]
        n_hl = 0
        for g_, m_ in (_ser_cfg()["info"] or {}).items():
            if g_ not in GAME_SLUG:
                continue
            for x_ in m_:
                ss_ = intl.set_slug(g_, x_)
                jp_ = out / series_path(g_, x_) / "index.html"
                if not jp_.exists() or not all((out / L_ / "sets" / ss_ / "index.html").exists() for _, L_ in HL_):
                    continue
                tags_ = [f'<link rel="alternate" hreflang="ja" href="{site}/{series_path(g_, x_)}">'] + [
                    f'<link rel="alternate" hreflang="{h_}" href="{site}/{L_}/sets/{ss_}/">' for h_, L_ in HL_] + [
                    f'<link rel="alternate" hreflang="x-default" href="{site}/en/sets/{ss_}/">']
                t_ = jp_.read_text(encoding="utf-8")
                if 'hreflang="ja"' not in t_:
                    jp_.write_text(t_.replace("</head>", "".join(tags_) + "</head>", 1), encoding="utf-8")
                for L_ in {L_ for _, L_ in HL_}:
                    f_ = out / L_ / "sets" / ss_ / "index.html"
                    t_ = f_.read_text(encoding="utf-8")
                    if '<link rel="alternate" hreflang="ja"' not in t_:  # 本文の <a hreflang="ja"> と間違えない（11/9 SEO点検で発覚）
                        f_.write_text(t_.replace('<link rel="alternate" hreflang="en"', tags_[0] + '<link rel="alternate" hreflang="en"', 1), encoding="utf-8")
                n_hl += 1
        print(f"日本語⇔海外の弾ページを hreflang でつないだ: {n_hl}弾")
        # 海外のトップ（/en/ /zh-tw/ /ko/）にも、日本語トップへの hreflang="ja" を足す（日本語トップからは出しているので、返しのリンクが要る）
        for L_ in ("en", "zh-tw", "ko"):
            f_ = out / L_ / "index.html"
            if f_.exists():
                t_ = f_.read_text(encoding="utf-8")
                if '<link rel="alternate" hreflang="ja"' not in t_ and '<link rel="alternate" hreflang="en"' in t_:
                    f_.write_text(t_.replace('<link rel="alternate" hreflang="en"', f'<link rel="alternate" hreflang="ja" href="{site}/"><link rel="alternate" hreflang="en"', 1), encoding="utf-8")

    if site:
        # 11/7 監査：サイトマップを種類ごとに分ける（Search Consoleで、どの種類が載っていないか分かる）。sitemap.xml は索引
        def _kind(u):
            p_ = u[len(site):].strip("/").split("/")
            if p_[0] in ("en", "zh-tw", "ko"):
                return "intl"
            if p_[0] in ("store", "chain", "l") and len(p_) > 1:
                return p_[0]
            if len(p_) > 1 and p_[1] == "area":
                return "area"
            if len(p_) > 1 and p_[0] in GAME_SLUG.values() and p_[1] not in ("today", "online", "no-id"):
                return "sets"
            return "main"
        groups = {}
        for u, lm_ in dict(urls).items():
            groups.setdefault(_kind(u), []).append((u, lm_))
        idx_ = []
        for k_, lst_ in sorted(groups.items()):
            (out / f"sitemap-{k_}.xml").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + "".join(f"<url><loc>{escape(u)}</loc><lastmod>{lm_}</lastmod></url>" for u, lm_ in lst_) + "</urlset>\n", encoding="utf-8")
            idx_.append(f"<sitemap><loc>{site}/sitemap-{k_}.xml</loc><lastmod>{max(l_ for _, l_ in lst_)}</lastmod></sitemap>")
        (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                         + "".join(idx_) + "</sitemapindex>\n", encoding="utf-8")
        (out / "robots.txt").write_text(  # 検索エンジンとAI検索（ChatGPT検索・Perplexity・Claude など）の読み取りをはっきり許可（11/3）
            "".join(f"User-agent: {b}\nAllow: /\nDisallow: /x-draft.html\n\n" for b in
                    ("Googlebot", "Bingbot", "Yeti", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Claude-SearchBot", "Claude-User", "*"))
            + f"Sitemap: {site}/sitemap.xml\n", encoding="utf-8")
        # AI検索（ChatGPT・Perplexity・Claude など）向けのサイト案内 llms.txt（11/7 Fable：AIからの流入が3割で一番多い）
        try:
            from collections import Counter as _C
            L = ["# トレカ抽選ナビ", "",
                 f"> ポケモンカード（ポケカ）・ONE PIECEカードゲーム（ワンピースカード）の抽選販売・予約抽選の情報を、全国のお店・通販から自動で集めて1日6回（朝7時〜夜22時）更新している日本語のサイトです。いま受付中{len(items)}件（{upd_hm}時点）。各抽選の締切・応募方法・本人確認や会員の条件・受け取り方をまとめています。",
                 "", "## 主なページ",
                 f"- [トップ（受付中の抽選すべて・締切順）]({site}/)",
                 f"- [ポケカの抽選]({site}/pokeka/)", f"- [ワンピースカードの抽選]({site}/onepiece/)",
                 f"- [今日締切の抽選]({site}/today/)", f"- [抽選結果の発表]({site}/kekka/)",
                 f"- [BOXの相場]({site}/souba/)", f"- [発売日カレンダー]({site}/calendar/)",
                 f"- [抽選の当て方・応募のコツ]({site}/guide/)", f"- [お店ごとの当選率（ユーザー報告）]({site}/tousenritsu/)",
                 f"- [店舗一覧（都道府県別）]({site}/store/)", "", "## 受付中が多い弾"]
            for (g_, x_), n_ in _C((i["game"], i["series"]) for i in items if i.get("series") and i["game"] in GAME_SLUG).most_common(12):
                if (out / series_path(g_, x_).strip("/") / "index.html").exists():
                    L.append(f"- [{GAME_SHORT[g_]}「{x_}」の抽選（受付中{n_}件）]({site}/{series_path(g_, x_)})")
            # 11/8：弾ごとの「予約・再販・在庫」と、チェーン×弾のページ
            sh_ = sorted(str(q.relative_to(out).parent) for q in out.glob("*/*/saihan/index.html"))
            if sh_:
                L += ["", "## 弾ごとの予約・再販・在庫（楽天ブックス・Amazon本体の在庫を1〜2分おきに確認）"]
                L += [f"- {site}/{q}/" for q in sh_]
            cs_ = sorted(CS_PAGES.items(), key=lambda kv: -sum(1 for i in items if i.get("chain") == kv[0][0] and kv[0][2] in (i.get("sers") or [i.get("series")])))[:20]
            if cs_:
                L += ["", "## お店×弾の抽選（例：TSUTAYAのハドウシーカー）"]
                L += [f"- [{CHAIN[c_][1]}の「{x_}」の抽選]({site}/{p_})" for (c_, g_, x_), p_ in cs_]
            L += ["", "## お店（チェーン）ごとの抽選"]
            for slug_, cname_, big_, n_ in sorted(chain_links, key=lambda t: -t[3])[:25]:
                L.append(f"- [{cname_}の抽選（受付中{n_}件）]({site}/chain/{slug_}/)")
            L += ["", "## 注意", "- 抽選の条件・期間は変わることがあります。応募前に各店舗の公式の告知をご確認ください。",
                  "- 本サイトはアフィリエイト広告（楽天・Amazonなど）を含みます。"]
            (out / "llms.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        except Exception as e:
            print("llms.txt を作れませんでした", e)

    inject_ga(out, os.environ.get("GA_ID") or s.get("ga_id"))  # Googleアナリティクス（IDがある時だけ）
    inject_linkswitch(out, s.get("vc_linkswitch_pid"))
    inject_pwa(out)  # ホーム画面に追加・締切の通知（11/7）
    inject_meta(out, "naver-site-verification", s.get("naver_site_verification"))  # NAVERサーチアドバイザーの確認（トップページで確認される）  # バリューコマースのLinkSwitch（提携先への普通のリンクを自動でアフィリンクに）

    if sample is None:
        save_json("site_meta.json", {"digest": digest, "updated": updated})
        save_json("page_lastmod.json", pmod)
    (out / ".changed").unlink(missing_ok=True)
    if changed:
        (out / ".changed").write_text(updated, encoding="utf-8")  # ワークフローはこれがある時だけ公開
    return out


GA_SKIP = {"x-draft.html", "site_preview.html"}  # 自分用のページは数えない
GA_NOTE = ("当サイトはアクセス解析にGoogleアナリティクスを使っています。データはCookieを使って匿名で集められ、"
           "個人を特定するものではありません（ブラウザの設定でCookieを無効にできます）。")


def cal_feeds(items, games):
    """{ファイル名: (カレンダー名, [抽選])}。ネット抽選はゲームごと、店頭抽選はゲーム×都道府県ごと"""
    feeds = {}
    for g in games:
        sh = GAME_SHORT[g]
        feeds[f"{GAME_SLUG[g]}-net.ics"] = (f"{sh}ネット抽選の締切（トレカ抽選ナビ）",
                                            [i for i in items if i["game"] == g and i.get("channel") != "store"])
        for a, sl in PREF.items():
            feeds[f"{GAME_SLUG[g]}-{sl}.ics"] = (f"{sh}店頭抽選の締切・{a}（トレカ抽選ナビ）",
                                                 [i for i in items if i["game"] == g and i.get("channel") == "store" and i.get("area") == a])
    return feeds


def write_cal_feeds(out, items, site, games):
    d = out / "cal"
    d.mkdir(parents=True, exist_ok=True)
    t0, stamp = now(), now()
    for fn, (nm, lots) in cal_feeds(items, games).items():
        evs = []
        for i in lots:
            e_ = parse_dt(i.get("end"))
            if not i.get("key") or not e_ or e_ < t0:
                continue
            lp = i.get("lpath") or detail.lottery_path(i)
            ev = detail.cal_event(i, i.get("store") or "", detail.short_name(i), f"{site}/{lp}" if site else "", stamp=stamp)
            if ev:
                evs.append(ev)
        (d / fn).write_text(detail.ics_wrap(evs, nm), encoding="utf-8")


def cal_sub_html(site, games):
    """/calendar/ の「締切を自動でカレンダーに入れる」。iPhone は webcal://、Android・PC は Googleカレンダーの登録リンク"""
    host = (site or "https://tcg-chusen.com").split("://", 1)[-1]
    def btns(fn, idp=""):
        w = f"webcal://{host}/cal/{fn}"
        gg = "https://calendar.google.com/calendar/render?cid=" + quote(w, safe="")
        return (f'<a class="btn" {idp}data-k="i" href="{escape(w)}">iPhoneのカレンダーに登録</a>'
                f'<a class="btn" {idp}data-k="g" href="{escape(gg)}" target="_blank" rel="noopener">Googleカレンダーに登録（Android・PC）</a>')
    opts = "".join(f'<option value="{sl}">{escape(a)}</option>' for a, sl in PREF.items())
    rows = []
    for g in games:
        sl = GAME_SLUG[g]
        rows.append(f'<h3>{escape(GAME_SHORT[g])}</h3><p><b>ネット抽選</b>（全国どこからでも応募できる抽選）<br>{btns(f"{sl}-net.ics")}</p>'
                    f'<p><b>店頭抽選</b>（お店で受け取る抽選）：<select class="calpref" data-g="{sl}" aria-label="都道府県">{opts}</select><br>'
                    + btns(f"{sl}-tokyo.ics", f'data-g="{sl}" ') + '</p>')
    js = ("<script>document.querySelectorAll('select.calpref').forEach(function(s){s.value='tokyo';s.onchange=function(){"
          f"var w='webcal://{host}/cal/'+s.dataset.g+'-'+s.value+'.ics';"
          "s.parentNode.querySelectorAll('a[data-k]').forEach(function(a){a.href=a.dataset.k=='i'?w:'https://calendar.google.com/calendar/render?cid='+encodeURIComponent(w)})}})</script>")
    return ('<section id="sub" class="calsub"><h2>🔔 抽選の締切を自動でカレンダーに入れる</h2>'
            '<p>一度登録すると、<b>これから見つかった抽選の締切も自動でスマホのカレンダーに入ります</b>（締切の1時間前〜締切の予定）。'
            'いらなくなったら、カレンダーのアプリから登録をはずせます。料金はかかりません。</p>' + "".join(rows) +
            '<p class="note">※カレンダーのアプリが数時間ごとに読みこむので、新しい抽選が入るまで少し時間がかかることがあります。'
            '<br>【やめたいとき】iPhone：カレンダーのアプリの下の「カレンダー」→ このカレンダーの「ⓘ」→「カレンダーを削除」。'
            'Googleカレンダー：パソコンで開いて、左の「他のカレンダー」のこのカレンダーの「︙」→「登録を解除」。</p></section>' + js)


def ga_snippet(ga_id):
    """Googleアナリティクスのタグ。自分たちのアクセス（Claudeアプリのブラウザでの確認・予約作業、自動のブラウザ、
    「?notrack=1」を一度開いた端末）は数えない（GA4の「AI Assistant」が自分たちで水増しされないように）"""
    return ('<script>(function(){var u=navigator.userAgent||"",n=false;'
            'try{if(/[?&]notrack=1/.test(location.search))localStorage.setItem("tcg_notrack","1");'
            'if(/[?&]notrack=0/.test(location.search))localStorage.removeItem("tcg_notrack");'
            'n=localStorage.getItem("tcg_notrack")==="1";}catch(e){}'
            'if(n||navigator.webdriver||/ Claude\\/|HeadlessChrome|Playwright/.test(u))return;'
            f'var s=document.createElement("script");s.async=true;s.src="https://www.googletagmanager.com/gtag/js?id={ga_id}";'
            'document.head.appendChild(s);window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments);};'
            f"gtag('js',new Date());gtag('config','{ga_id}');"
            # アフィリンクのクリックを数える（11/7）：どこに置いたリンクが押されたか（placement）
            'document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[href]");if(!a)return;var h=a.href||"";'
            'var n=/rakuten\\.co\\.jp/.test(h)?"rakuten":/amazon\\.(co\\.jp|com)/.test(h)?"amazon":/valuecommerce|7net|yamada/.test(h)?"vc":/ebay\\.com/.test(h)?"ebay":"";'
            'if(!n||!/sponsored/.test(a.rel||""))return;var p=a.dataset.pl||(a.closest("[data-pl]")||{}).dataset&&a.closest("[data-pl]").dataset.pl||(a.closest(".ad,.lose,.feed,.anchor,.cal-buy,.ticket")||{}).className||"other";'
            'gtag("event","affiliate_click",{network:n,placement:String(p).slice(0,40),page:location.pathname.slice(0,60)});},true);'
            "})();</script>")


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
        if "googletagmanager.com/gtag/js" in h or "</head>" not in h:  # すでに入っている（2回入れない）
            continue
        h = h.replace("</head>", tag + "</head>", 1)
        if "</footer>" in h:
            lang = p.relative_to(out).parts[0] if len(p.relative_to(out).parts) > 1 else ""
            h = h.replace("</footer>", f'<p class="ga-note">{GA_NOTE_INTL.get(lang, GA_NOTE)}</p></footer>', 1)
        p.write_text(h, encoding="utf-8")
        n += 1
    return n


# 海外向けページのフッターの注意書き（11/8：日本語のまま出ていたのを各言語に）
GA_NOTE_INTL = {
    "en": "This site uses Google Analytics to measure traffic. Data is collected anonymously via cookies and does not identify you; you can disable cookies in your browser.",
    "zh-tw": "本站使用 Google Analytics 進行流量分析。資料透過 Cookie 匿名收集，不會識別個人身分；您可在瀏覽器設定中停用 Cookie。",
    "ko": "이 사이트는 방문 통계를 위해 Google 애널리틱스를 사용합니다. 데이터는 쿠키를 통해 익명으로 수집되며 개인을 식별하지 않습니다. 브라우저 설정에서 쿠키를 끌 수 있습니다.",
}


def inject_linkswitch(out, pid):
    """全ページの <head> にバリューコマースの LinkSwitch のタグを入れる（11/7 ユーザーから受け取ったタグ）"""
    pid = str(pid or "").strip()
    if not pid.isdigit():
        return 0
    tag = (f'<script>var vc_pid = "{pid}";</script>'
           '<script src="//aml.valuecommerce.com/vcdal.js" async></script>')
    n = 0
    for p in Path(out).rglob("*.html"):
        if p.name in GA_SKIP or p.relative_to(out).parts[0] in ("en", "zh-tw", "ko"):  # 海外向けページは国内の広告主に関係ないので入れない
            continue
        h = p.read_text(encoding="utf-8")
        if "</head>" not in h:
            continue
        h = re.sub(r'<script>var vc_pid = "\d+";</script><script src="//aml\.valuecommerce\.com/vcdal\.js" async></script>', "", h)  # 古いIDのタグは入れ替える
        p.write_text(h.replace("</head>", tag + "</head>", 1), encoding="utf-8")
        n += 1
    return n


def inject_pwa(out):
    """国内向けの全ページに、ホーム画面アプリの設定と通知のしくみ（/push.js）を入れる（11/7）"""
    tag = ('<link rel="manifest" href="/manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes">'
           '<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="抽選ナビ">'
           '<script src="/push.js" defer></script>')
    n = 0
    for p in Path(out).rglob("*.html"):
        if p.name in GA_SKIP or p.relative_to(out).parts[0] in ("en", "zh-tw", "ko"):
            continue
        h = p.read_text(encoding="utf-8")
        if "</head>" not in h or 'href="/manifest.webmanifest"' in h:
            continue
        p.write_text(h.replace("</head>", tag + "</head>", 1), encoding="utf-8")
        n += 1
    return n


def inject_meta(out, name, value):
    """全ページの <head> に <meta name=… content=…> を入れる（検索エンジンの確認コードなど）"""
    value = str(value or "").strip()
    if not value:
        return 0
    tag, n = f'<meta name="{name}" content="{escape(value)}">', 0
    for p in Path(out).rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        if f'name="{name}"' in h or "</head>" not in h:
            continue
        p.write_text(h.replace("</head>", tag + "</head>", 1), encoding="utf-8")
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
