"""1回分の実行：収集 → 承認 → X投稿 → WP更新"""
import sys

from common import load_settings, load_sources, log
from collect import collect, sync_manual
from approve import approve
from xpost import post_all, post_daily_summary
from xbuzz import post_buzz
from xtrend import update_trends
from pagecheck import check_pages
from market import update_market
from wp import update_pages
from sitegen import build as build_site, active_series
import rakuten
from classify import classify
from deadline import fill_deadlines
from dedupe import dedupe


def main():
    s = load_settings()
    log(f"開始 auto_approve={s['auto_approve']} dry_run={s['dry_run']}")
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    sync_manual()  # 自分で追加した抽選（config/manual.yaml）
    if step in ("all", "collect"):
        new = collect(load_sources(), s)
        log(f"新着 {len(new)} 件")
    if step in ("all", "publish"):
        try:
            fill_deadlines(s)  # 締切が分からない抽選は、Xの告知（本文・画像）や応募ページから読み取る
        except Exception as e:
            log(f"締切の調査: スキップ {e}")
        try:
            check_pages(s)  # 応募ページ（通販・フォーム・LivePocket）が受付終了になっていたら終了に
        except Exception as e:
            log(f"応募ページの確認: スキップ {e}")
        try:
            classify(s)  # ネット（発送）／店頭（店頭受け取り）の振り分けと都道府県の補完
        except Exception as e:
            log(f"振り分け: スキップ {e}")
        try:
            dedupe(s)  # 別々の情報元から拾った同じ抽選を1件にまとめる
        except Exception as e:
            log(f"重複: スキップ {e}")
        approve(s)
        post_all(s)
        post_daily_summary(s)
        try:
            post_buzz(s)  # 1日1回、リンクなしの反応狙い投稿（buzz_hour 時〜）
        except Exception as e:
            log(f"バズ投稿: スキップ {e}")
        update_pages(s)
        try:
            rakuten.update(s, active_series(s))  # 楽天の商品画像（キー未登録なら何もしない）
            rakuten.supply_prices(s, list(s["game_names"]))  # サプライの楽天最安値（1日1回）
        except Exception as e:
            log(f"楽天: スキップ {e}")
        try:
            update_market(s)  # 今日の相場（スニダン・1日1回だけ）
        except Exception as e:
            log(f"相場: スキップ {e}")
        try:
            update_trends(s)  # Xで話題のネタから投稿文の下書き（下書きページに出す）
        except Exception as e:
            log(f"話題ネタ: スキップ {e}")
        build_site(s)  # 自作サイト（site/index.html）を書き出し
    log("完了")


if __name__ == "__main__":
    main()
