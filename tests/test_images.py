"""商品名から商品画像を選ぶテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import sitegen

rk = {"pokemon|30th CELEBRATION": {"image": "box30", "url": "u1"},
      "pokemon|30周年御三家カードセット": {"image": "gosan", "url": "u2"},
      "pokemon|30周年エーフィ・ブラッキーデッキ": {"image": "deck", "url": "u3"},
      "pokemon|ストームエメラルダ": {"image": "storm", "url": "u4"},
      "pokemon|バトルコレクション": {"image": "bc1", "url": "u5"},
      "pokemon|スタートデッキ100 バトルコレクション": {"image": "bc2", "url": "u6"},
      "pokemon|MEGA": {"image": "dream", "url": "u7"},
      "onepiece|神の支配": {"image": "op18", "url": "u8"},
      "onepiece|ヒロインズエディション vol.2": {"image": "eb05", "url": "u9"},
      "onepiece|HEROINES PRECIOUS BOX": {"image": "", "url": ""}}
al = {"pokemon": {"30th CELEBRATION カードセット": "30周年御三家カードセット", "エーフィ・ブラッキー": "30周年エーフィ・ブラッキーデッキ"},
      "onepiece": {"OP-18": "神の支配", "EB-05": "ヒロインズエディション vol.2", "Heroines Edition vol.2": "ヒロインズエディション vol.2"}}
m = lambda g, p, s=None, ps=(): [a for a, _ in sitegen.match_images(g, [s, p] + list(ps), rk, {}, al, s)]

assert m("pokemon", "拡張パック「30th CELEBRATION」1BOX／「ストームエメラルダ」1BOX") == ["box30", "storm"]  # 2つの商品
assert m("pokemon", "30th CELEBRATION カードセット") == ["gosan"]  # 長い名前の一部は数えない
assert m("pokemon", "MEGA 30th CELEBRATION プレミアムデッキセット エーフィ・ブラッキー", "30th CELEBRATION") == ["deck"]  # 後ろの具体的な名前
assert m("pokemon", "MEGA スタートデッキ100 バトルコレクション", "バトルコレクション") == ["bc2"]  # 同じ商品は1つ
assert m("pokemon", "ポケモンカードゲーム MEGA 拡張パック") == []  # 「MEGA」だけでは決めない
assert m("pokemon", "不明な商品", "ストームエメラルダ") == ["storm"]  # 商品名で分からなければ弾名
assert m("onepiece", "「神の支配」【OP-18】＋「ONE PIECE Heroines Edition vol.2」【EB-05】") == ["op18", "eb05"]
assert m("onepiece", "「ONE PIECE HEROINES PRECIOUS BOX」") == []  # 画像のない商品
assert m("onepiece", "8商品", None, ["決戦の刻", "神の支配【OP-18】", "Heroines Edition vol.2"]) == ["op18", "eb05"]
print("IMAGES ALL OK")
