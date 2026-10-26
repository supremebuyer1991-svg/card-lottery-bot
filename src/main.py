"""1回分の実行：収集 → 承認 → X投稿 → WP更新"""
import sys

from common import load_settings, load_sources, log
from collect import collect
from approve import approve
from xpost import post_all, post_daily_summary
from wp import update_pages
from sitegen import build as build_site


def main():
    s = load_settings()
    log(f"開始 auto_approve={s['auto_approve']} dry_run={s['dry_run']}")
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("all", "collect"):
        new = collect(load_sources(), s)
        log(f"新着 {len(new)} 件")
    if step in ("all", "publish"):
        approve(s)
        post_all(s)
        post_daily_summary(s)
        update_pages(s)
        build_site(s)  # 自作サイト（site/index.html）を書き出し
    log("完了")


if __name__ == "__main__":
    main()
