"""1回分の実行：収集 → 承認 → X投稿 → WP更新"""
import sys

from common import load_settings, load_sources, log
from collect import collect
from approve import approve
from xpost import post_all, post_daily_summary
from wp import update_pages
from sitegen import build as build_site, active_series
import rakuten
from classify import classify


def main():
    s = load_settings()
    log(f"開始 auto_approve={s['auto_approve']} dry_run={s['dry_run']}")
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("all", "collect"):
        new = collect(load_sources(), s)
        log(f"新着 {len(new)} 件")
    if step in ("all", "publish"):
        try:
            classify(s)  # ネット（発送）／店頭（店頭受け取り）の振り分けと都道府県の補完
        except Exception as e:
            log(f"振り分け: スキップ {e}")
        approve(s)
        post_all(s)
        post_daily_summary(s)
        update_pages(s)
        try:
            rakuten.update(s, active_series(s))  # 楽天の商品画像（キー未登録なら何もしない）
            rakuten.supply_prices(s, list(s["game_names"]))  # サプライの楽天最安値（1日1回）
        except Exception as e:
            log(f"楽天: スキップ {e}")
        build_site(s)  # 自作サイト（site/index.html）を書き出し
    log("完了")


if __name__ == "__main__":
    main()
