"""ゲーム・ホビー入荷速報：Google 検索に出すページを「中身のあるページ」だけに絞る（11/28 ユーザーOK「ぜんぶたのむね」）

11/14 から Google 検索にほぼ出なくなり、登録済みページも 668 → 175 → 133 と減り続けた。
サイトマップに約830ページ（うち商品ページ627・発売予定87）あり、薄いページが多くサイト全体の評価が下がっていると考えた。
検索に出すのは下の決まりに当たるページだけ。ほかは noindex＋サイトマップから外す（ページそのものは残す）。

  出す：トップ・1階層のページ（カテゴリ・/now/・/today/・/calendar/・/premium/・/souba/・/new/ など）・/guide/ の記事・
        カテゴリ／モデルのまとめ（/ps5/ps5-pro/ など）・/souba/<カテゴリ>/・/chain/<お店>/
  出さない：/l/（抽選1件ずつ）・/new/<JAN>/・/item/・/chain/<お店>/<カテゴリ>/・/souba/<カテゴリ>/<種類>/
            （Search Console で表示があったページ＝config/game/sc_impression_pages.txt は残す）
  商品ページ（/premium/<JAN>/）は game_premium 側の premium_ok で決める
"""

_DROP_PREFIX = ("l/", "new/", "item/")


_KEEP = {}


def manual_keep(path):
    """config/game/index_keep.txt に書いたページ（手で「検索に出す」と決めたもの）"""
    if "v" not in _KEEP:
        try:
            from pathlib import Path
            txt = (Path(__file__).resolve().parent.parent / "config" / "game" / "index_keep.txt").read_text(encoding="utf-8")
            _KEEP["v"] = {ln.strip().strip("/") for ln in txt.splitlines() if ln.strip() and not ln.startswith("#")}
        except Exception:
            _KEEP["v"] = set()
    return (path or "").strip("/") in _KEEP["v"]


def _sc(path):
    if manual_keep(path):
        return True
    try:
        from sitegen_game import sc_protected
        return sc_protected(path)
    except Exception:
        return False


def keep(path):
    """このページを検索に出してよいか（商品ページ以外）"""
    q = (path or "").strip("/")
    if not q:
        return True
    sp = q.split("/")
    if sp[0] == "premium":
        return True   # 商品ページは premium_ok で決める（呼ぶ側で）
    if sp[0] == "guide" or len(sp) == 1:
        return True
    if q.startswith(_DROP_PREFIX) or q + "/" in ("l/", "new/", "item/"):
        return _sc(q + "/")
    if sp[0] in ("souba", "chain"):
        return len(sp) == 2 or _sc(q + "/")
    return len(sp) == 2 or _sc(q + "/")   # カテゴリ／モデルのまとめ（2階層）は出す


def premium_ok(jan, n_stores, has_facts, has_override_facts, sc):
    """商品ページを検索に出してよいか：手で確かめた商品の特徴がある／商品の特徴＋買取店4店以上の比較／
    Search Console で表示があり、商品の特徴か買取店3店以上がある"""
    if has_override_facts or manual_keep(f"premium/{jan}/"):
        return True
    if has_facts and n_stores >= 4:
        return True
    return bool(sc and (has_facts or n_stores >= 3))
