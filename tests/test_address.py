"""住所の読み取りのテスト  python tests/test_address.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from address import find_address, maps_url

assert find_address("会場 TSUTAYA枚方ベルパルレ店 大阪府枚方市宮之阪4-28-12 TEL:072-000", "大阪府") == "大阪府枚方市宮之阪4-28-12"
assert find_address("店舗住所：〒573-0022 大阪府枚方市宮之阪4−28−12 ベルパルレ1F", "大阪府") == "大阪府枚方市宮之阪4-28-12"
assert find_address("運営会社 株式会社X 東京都渋谷区1-2-3", "東京都") is None          # 住所の手がかりの言葉がない
assert find_address("住所 東京都渋谷区1-2-3", "大阪府") is None                        # 都道府県がちがう
assert find_address("住所 大阪府枚方市", None) is None                                  # 番地がない
assert find_address("住所 東京都豊島区東池袋1丁目2-3 サンシャインセンター", None) == "東京都豊島区東池袋1丁目2-3"
assert maps_url("店", "大阪府枚方市宮之阪4-28-12").startswith("https://www.google.com/maps/search/?api=1&query=")
print("ADDRESS OK")
assert find_address("概要 開催日 2026年11月6日 会場 TSUTAYA枚方ベルパルレ店 (大阪府) 枚方市宮之阪4-28-12 会場マップ", "大阪府") == "大阪府枚方市宮之阪4-28-12"
print("ADDRESS LP OK")
