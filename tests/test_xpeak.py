"""新弾の発売前だけXの上限を上げる"""
import sys, tempfile
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import save_json
import fetch_x

save_json("newsets.json", {"series": {"onepiece": {"神の支配": {"release": "2026-11-21", "type": "ブースターパック【OP-18】"}},
                                      "pokemon": {"デッキ": {"release": "2026-11-10", "type": "構築デッキ"}}}})
s = {"x_read_budget_per_day": 150, "x_read_budget_peak": 300, "x_peak_days_before": 7,
     "series_info": {"pokemon": {"ハドウシーカー": {"release": "2026-11-27", "type": "拡張パック"}}}}
assert fetch_x.peak_set(s, date(2026, 11, 13)) is None       # 8日前
assert fetch_x.peak_set(s, date(2026, 11, 14)) == "神の支配"  # 7日前から
assert fetch_x.peak_set(s, date(2026, 11, 21)) == "神の支配"  # 発売日まで
assert fetch_x.peak_set(s, date(2026, 11, 22)) == "ハドウシーカー"  # 次の弾の発売前（11/20〜27）
assert fetch_x.peak_set(s, date(2026, 11, 28)) is None
assert fetch_x.peak_set(s, date(2026, 11, 9)) is None        # 構築デッキは対象外
import common as c
orig = c.now
fetch_x.now = lambda: __import__("datetime").datetime(2026, 11, 15, 12, tzinfo=orig().tzinfo)
assert fetch_x.daily_limit(s) == 300
fetch_x.now = lambda: __import__("datetime").datetime(2026, 11, 5, 12, tzinfo=orig().tzinfo)
assert fetch_x.daily_limit(s) == 150
assert fetch_x.daily_limit(dict(s, x_read_budget_by_date={"2026-11-05": 500})) == 500
print("XPEAK OK")
