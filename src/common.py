import re
"""設定・状態ファイル・共通ユーティリティ"""
import hashlib
import json
import os
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
STATE_DIR = ROOT / "state"


def now() -> datetime:
    return datetime.now(JST)


def _env_bool(name, default):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.lower() in ("1", "true", "yes", "on")


def load_settings() -> dict:
    s = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    s["auto_approve"] = _env_bool("AUTO_APPROVE", s.get("auto_approve", False))
    s["dry_run"] = _env_bool("DRY_RUN", s.get("dry_run", False))
    s["site_url"] = os.environ.get("WP_URL") or s.get("site_url") or ""
    return s


def load_sources() -> list:
    return yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))["sources"]


def load_json(name, default):
    p = STATE_DIR / name
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default


def save_json(name, data):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize(s: str) -> str:
    return "".join((s or "").lower().split())


def lottery_key(item: dict) -> str:
    """同じ抽選を一意に判定するキー（ゲーム＋店舗＋商品＋締切日）"""
    end = (item.get("end") or "")[:10]
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


def fix_game(it):
    """商品名・弾名がはっきり別のゲームのものなら、ゲームを直す。直したら True"""
    txt = " ".join(str(it.get(k) or "") for k in ("product", "series"))
    hit = [g for g, r in GAME_HINTS.items() if r.search(txt)]
    if len(hit) == 1 and it.get("game") != hit[0] and it.get("game") in GAME_HINTS:
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
