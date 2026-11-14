"""中身の少ないページの解説を、いっぺんにまとめて作る（11/14 ユーザー：1ページごとの中身も充実させて）。
候補は前回の測定（state/game/content_volume.json）で中身の少ないページ。結果は state/game/ai_text.json"""
import os
import sys
os.environ["SITE"] = "game"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from common import load_settings  # noqa: E402
import game_aitext  # noqa: E402

s = load_settings()
s["aitext_parallel"] = 8
game_aitext.update(s, limit=int(os.environ.get("AITEXT_LIMIT", "400")), no_time_limit=True)
