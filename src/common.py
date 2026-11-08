"""設定・状態ファイル・共通ユーティリティ"""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# GitHubに登録したキーに、貼り付け時の空白・改行・引用符・「Bearer 」が混ざっていても動くように掃除する
_SECRET_NAMES = ("ANTHROPIC_API_KEY", "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
                 "X_BEARER_TOKEN", "WP_USER", "WP_URL", "SITE_URL", "AMAZON_TAG",
                 "RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID")
for _k in _SECRET_NAMES:
    _v = os.environ.get(_k)
    if _v:
        _v = _v.strip().strip('"').strip("'")
        if _v.lower().startswith("bearer "):
            _v = _v[7:]
        os.environ[_k] = "".join(_v.split())
JST = timezone(timedelta(hours=9))

# サイトの切り替え（SITE=tcg が今まで通りのトレカ抽選ナビ。SITE=game は姉妹サイト「ゲーム・ホビー入荷速報」）
# 何も指定しなければ tcg。設定は config/（tcg）か config/game/（game）、状態は state/ か state/game/ に分ける
SITE = (os.environ.get("SITE") or "tcg").strip().lower()
if SITE not in ("tcg", "game"):
    SITE = "tcg"
CONFIG_DIR = ROOT / "config" if SITE == "tcg" else ROOT / "config" / "game"
STATE_DIR = ROOT / "state" if SITE == "tcg" else ROOT / "state" / "game"


def now() -> datetime:
    return datetime.now(JST)


def _env_bool(name, default):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.lower() in ("1", "true", "yes", "on")


_SETTINGS_CACHE = {}


def _yaml_load(text):
    try:
        return yaml.load(text, Loader=yaml.CSafeLoader)  # 速い読み込み（あれば）
    except AttributeError:
        return yaml.safe_load(text)


def load_settings() -> dict:
    # 設定ファイルは一度だけ読んで使い回す（サイトを作る間に2,000回以上読み直していて、GitHub Actions の時間の大半を使っていた。11/7）
    import copy
    p = CONFIG_DIR / "settings.yaml"
    mt = p.stat().st_mtime
    if _SETTINGS_CACHE.get("mt") != mt or _SETTINGS_CACHE.get("p") != str(p):
        _SETTINGS_CACHE.update(mt=mt, p=str(p), v=_yaml_load(p.read_text(encoding="utf-8")))
    s = copy.deepcopy(_SETTINGS_CACHE["v"])
    s["auto_approve"] = _env_bool("AUTO_APPROVE", s.get("auto_approve", False))
    s["dry_run"] = _env_bool("DRY_RUN", s.get("dry_run", False))
    s["site_url"] = os.environ.get("WP_URL") or s.get("site_url") or ""
    if SITE == "game":  # ゲーム・ホビー版：カテゴリの名前などは config/game/categories.yaml から組み立てる
        try:
            import gamecats
            gamecats.apply(s)
        except Exception as e:
            log(f"カテゴリ設定の読み込みに失敗: {e}")
    return s


def load_sources() -> list:
    return yaml.safe_load((CONFIG_DIR / "sources.yaml").read_text(encoding="utf-8"))["sources"]


def load_json(name, default):
    p = STATE_DIR / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def save_json(name, data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize(s: str) -> str:
    return "".join((s or "").lower().split())


def lottery_key(item: dict) -> str:
    """同じ抽選を一意に判定するキー（ゲーム＋店舗＋商品＋締切日）
    ゲーム・ホビー版の再入荷・先着（締切が無い）は、同じ商品でも日が違えば別の出来事なので、見つけた日も混ぜる。
    発売日・再販日（release）はお店ではなくメーカーの予定なので、カテゴリ＋商品＋発売日で1件"""
    end = (item.get("end") or "")[:10]
    kind = item.get("kind")
    if SITE == "game" and kind == "release":
        return sha("|".join(["release", item.get("game", ""), normalize(item.get("product")), end]))
    if SITE == "game" and kind in ("restock", "first_come") and not end:
        day = (item.get("found_at") or item.get("start") or "")[:10] or now().date().isoformat()
        item.setdefault("found_at", now().isoformat())
        return sha("|".join([item.get("game", ""), normalize(item.get("store")),
                             normalize(item.get("product")), kind, day]))
    return sha("|".join([item.get("game", ""), normalize(item.get("store")),
                         normalize(item.get("product")), end]))


def parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt


def log(*a):
    print(f"[{now():%m-%d %H:%M}]", *a, flush=True)


# 商品名・弾名から、ゲームがはっきり分かるもの（AIがXの「ポケカ 抽選」検索の投稿をポケカと取り違えることがある）
GAME_HINTS = {
    "onepiece": re.compile(r"ONE ?PIECE|ワンピース|ワンピカ|Heroines|HEROINES|ヒロインズ|\b(?:OP|EB|PRB)-?\d{2}\b", re.I),
    "pokemon": re.compile(r"ポケモン|ポケカ|Pok[eé]mon|ピカチュウ"),
    "dragonball": re.compile(r"ドラゴンボール|DRAGON ?BALL|フュージョンワールド|FUSION ?WORLD", re.I),
}


def game_hints():
    """ゲーム（カテゴリ）を見分ける手がかり。tcg はこのファイルの GAME_HINTS、game は config/game/categories.yaml の hints"""
    if SITE == "game":
        try:
            import gamecats
            return gamecats.hints()
        except Exception:
            return {}
    return GAME_HINTS


def fix_game(it):
    """商品名・弾名がはっきり別のゲームのものなら、ゲームを直す。直したら True"""
    hints = game_hints()
    txt = " ".join(str(it.get(k) or "") for k in ("product", "series"))
    hit = [g for g, r in hints.items() if r.search(txt)]
    if len(hit) == 1 and it.get("game") != hit[0] and it.get("game") in hints:
        it["game"] = hit[0]
        return True
    return False


# ---- 応募に必要なもの（本人確認・会員・購入履歴・レシート・お店のクレジットカード）----
# お店のクレジットカード：「支払いはクレジットカードのみ」（払い方）とまちがえないよう、持っていることが条件の書き方・カードの名前だけ
STORE_CC_RE = (r"ゴールドポイントカード・?プラス|ビックカメラSuica|ビックカメラ.{0,4}カード.{0,4}(会員|お持ち)|イオンカード|エディオンカード|"
               r"ジョーシン.{0,6}カード|JQ\s*CARD|(クレジット|クレカ)カード?.{0,4}(会員|をお持ち|お持ちの|所持|保有|限定|ご利用の方|入会)|"
               r"(当社|店舗|提携)(の)?クレジット")
NEEDS_RE = {"購入履歴": r"購入(履歴|実績|歴)|利用(履歴|実績)", "レシート": r"レシート",
            "お店のクレジットカード": STORE_CC_RE, "アプリ会員": r"アプリ"}


def needs_of(i):
    """抽選に必要なもののリスト（分かっているものだけ）と、本人確認・会員が分からないか（True＝応募ページで確認）"""
    import re as _re
    t = " ".join(i.get("tags") or []) + " " + (i.get("conditions") or "") + " " + (i.get("method") or "")
    out = []
    if i.get("id_check") is True:
        out.append("本人確認")
    if i.get("member") == "card":
        out.append("お店の会員カード")
    elif i.get("member") == "account":
        out.append("会員登録")
    for w, pat in NEEDS_RE.items():
        if (w in (i.get("tags") or []) or _re.search(pat, t)) and w not in out:
            if w == "アプリ会員" and "アプリ" not in (i.get("tags") or []) and not _re.search("アプリ", i.get("method") or ""):
                continue
            out.append(w)
    unknown = i.get("id_check") is None or not i.get("member")
    return out, unknown


# 情報元に店名が書かれていない抽選（「その他のストア」など）。応募ページの名前から店名を入れるまで、投稿には出さない
GENERIC_STORE_RE = re.compile(r"^\s*(その他|そのほか|他)の?(ストア|店舗|ショップ|お店|店)?\s*$|^\s*(ストア|店舗|不明)\s*$")


def site_name(html):
    """ページの名前（og:site_name → title）からお店の名前らしい部分を取り出す。無ければ None"""
    m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', html or "", re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name', html or "", re.I)
    name = m.group(1) if m else None
    if not name:
        t = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
        if not t:
            return None
        parts = [x.strip() for x in re.split(r"\s*[｜|\-–—:：]\s*", re.sub(r"\s+", " ", t.group(1))) if x.strip()]
        if not parts:
            return None
        shop = [x for x in parts if re.search(r"店|ストア|ショップ|shop|store|トレカ|カード", x, re.I)]
        name = (shop or parts)[-1]
    import html as _h
    name = _h.unescape(name).strip()
    return name if 1 < len(name) <= 40 and not GENERIC_STORE_RE.search(name) else None
