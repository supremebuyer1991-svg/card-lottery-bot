"""写真の無い買取相場の商品の写真を、いっぺんに全部探す（11/14 ユーザー「今全部やるのはよくない？」）。
順番：Amazon（JAN）→ 楽天市場（JAN）。楽天ブックスの写真がある商品は探さない。結果は state/game/premium_photo.json"""
import os
import sys
os.environ["SITE"] = "game"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from common import load_settings, log  # noqa: E402
import game_premium as gp  # noqa: E402

s = load_settings()
before = sum(1 for x in gp.catalog(s, gp.watch_map_cached()) if not x.get("img"))
log(f"写真の無い商品：{before}件")
gp.az_photo_update(s, limit=2000, no_time_limit=True)
gp.photo_update(s, limit=2000, no_time_limit=True)
# 抽選・発売の商品（11/14 追加）：Amazon（商品名）→ 楽天市場（商品名）
import game_affi  # noqa: E402
from common import load_json, now, parse_dt  # noqa: E402
_t = now()
live = [i for i in load_json("lotteries.json", {}).values() if i.get("status") in ("approved", "posted", "listed")
        and not (parse_dt(i.get("end")) and parse_dt(i["end"]) < _t) and not i.get("from_tcg")]
c = game_affi.az_photo_lots(s, live, limit=500, no_time_limit=True)
s2 = dict(s, rakuten_photo_calls_per_run=500, rakuten_until_sec=100000)
game_affi.photo_update(s2, live, cache=c)
after = sum(1 for x in gp.catalog(s, gp.watch_map_cached()) if not x.get("img"))
log(f"写真の無い商品：{before}件 → {after}件")
