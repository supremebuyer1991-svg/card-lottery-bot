"""商品の事実（メーカー公式などをAIがウェブ検索して要約）を、まとめて取る（11/14 ユーザー「ええで」）。
材料が無くて解説を作れていない商品（has_material が False）から。結果は state/game/product_facts.json"""
import os
import sys
os.environ["SITE"] = "game"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from common import load_settings  # noqa: E402
import game_facts  # noqa: E402
import game_premium  # noqa: E402

s = load_settings()
s["product_facts_parallel"] = 6
game_facts.update(s, limit=int(os.environ.get("FACTS_LIMIT", "400")), only=lambda x: not game_premium.has_material(x))
