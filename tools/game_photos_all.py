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
after = sum(1 for x in gp.catalog(s, gp.watch_map_cached()) if not x.get("img"))
log(f"写真の無い商品：{before}件 → {after}件")
