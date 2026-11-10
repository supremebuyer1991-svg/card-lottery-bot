"""11/10：JANの無い買取店の商品名を寄せるとき、数字（世代・周年など）が違う商品には寄せない"""
import os, sys, pathlib
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import official_link as ol
import game_premium as gp

assert ol.same_item_score("Nintendo Switch 2 Proコントローラー", "Nintendo Switch Proコントローラー") == 0
assert ol.same_item_score("Nintendo Switch 2 Proコントローラー", "Nintendo Switch2 Proコントローラー") == 1
assert ol.same_item_score("PS5 ワイヤレスコントローラー クロマ パール CFI-ZCT1J12", "PS5 コントローラー DualSense クロマ パール [CFI-ZCT1J12]") >= 0.85

st = {
    "買取商店": {"at": "x", "items": [["Nintendo Switch 2 Proコントローラー", None, 8500]]},
    "A店": {"at": "x", "items": [["Nintendo Switch Proコントローラー", "4902370535730", 6100],
                                ["Nintendo Switch 2 Proコントローラー BEE-A-FSSKA", "4902370552843", 8400]]},
    "B店": {"at": "x", "items": [["Nintendo Switch 2 Proコントローラー", "4902370552843", 8300]]},
}
g = gp.groups(st)
assert "買取商店" not in g["4902370535730"]["prices"], g["4902370535730"]
assert g["4902370552843"]["prices"]["買取商店"] == 8500
assert g["4902370535730"]["max"] == 6100
print("ok")
