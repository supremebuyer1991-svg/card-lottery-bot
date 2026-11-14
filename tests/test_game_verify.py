"""元の記事で確かめる（game_verify）"""
import json, os, sys, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ["SITE"] = "game"
tmp = pathlib.Path(tempfile.mkdtemp())
import common
common.STATE_DIR = tmp
from common import save_json, load_json
import game_verify, sitegen_game

lots = {
    "ok": dict(status="approved", store="ヨドバシ", product="PS5 Pro", kind="lottery", source_url="https://a/1", found_at="2026-11-10T13:00"),
    "ng": dict(status="approved", store="ちいかわ", product="クリスマスマーケット", kind="first_come", start="2026-11-24T11:00+09:00", source_url="https://a/2", found_at="2026-11-10T13:00"),
    "fix": dict(status="approved", store="ゲオ", product="Switch2", kind="lottery", end="2026-11-20T23:59+09:00", source_url="https://a/3", found_at="2026-11-10T13:00"),
    "ev": dict(status="approved", store="会場", product="イベント", kind="lottery", source_url="https://a/4", found_at="2026-11-10T13:00"),
    "dead": dict(status="approved", store="X", product="Y", source_url="https://a/5", found_at="2026-11-10T13:00"),
    "man": dict(status="approved", store="M", product="N", manual=True, url="https://a/6"),
}
save_json("lotteries.json", lots)
ANS = {"ok": {"is_sale": True, "ok": True, "facts": ["1人1台まで", "  PSNアカウントの連携が必要  ", 3]},
       "ng": {"is_sale": True, "ok": False, "wrong": ["start", "channel"], "fix": {"start": None}, "reason": "通販の記載なし"},
       "fix": {"is_sale": True, "ok": False, "wrong": ["end"], "fix": {"end": "2026-11-18T23:59:00+09:00"}},
       "ev": {"is_sale": False, "ok": False}}
def ai(item, url, text): return ANS[{"1": "ok", "2": "ng", "3": "fix", "4": "ev"}[url[-1]]]
def fetcher(url):
    if url.endswith("5"): raise RuntimeError("404")
    return "<p>" + "本文です。" * 100 + "</p>"
n = game_verify.verify({"verify_per_run": 10}, ai=ai, fetcher=fetcher)
L = load_json("lotteries.json", {})
assert n == 4, n
assert L["ok"]["verified"] is True
assert L["ng"]["verified"] is False and "start" in L["ng"]["verify_note"]
assert L["fix"]["verified"] is True and L["fix"]["end"].startswith("2026-11-18") and L["fix"]["before_verify"]["end"].startswith("2026-11-20")
assert L["ev"]["verified"] is False
assert "verified" not in L["dead"] and "verified" not in L["man"]   # 読めない・手で入れたもの は次の回／確かめない
# サイトに出すか
assert sitegen_game.shown_ok(L["ok"]) and not sitegen_game.shown_ok(L["ng"]) and not sitegen_game.shown_ok(L["dead"])
assert sitegen_game.shown_ok(L["man"]) and sitegen_game.shown_ok(dict(found_at="2026-11-01T10:00"))
# 要点（facts）：自分の言葉で書いた要点を残す（文字以外は捨てる）・出典の記事
assert L["ok"]["facts"] == ["1人1台まで", "PSNアカウントの連携が必要"] and L["ok"]["facts_src"] == "https://a/1", L["ok"]
assert "facts" not in L["ev"]
# 前に確かめた項目で要点が無いものは、要点だけ取り直す（verified は変えない）
L["old"] = dict(status="approved", store="ゲオ", product="Switch2", kind="lottery", verified=True, verify_note="前の", source_url="https://a/1", found_at="2026-11-09T13:00")
save_json("lotteries.json", L)
game_verify.verify({"verify_per_run": 10, "verify_facts_backfill": 4}, ai=ai, fetcher=fetcher)
L = load_json("lotteries.json", {})
assert L["old"]["facts"] == ["1人1台まで", "PSNアカウントの連携が必要"] and L["old"]["verified"] is True and L["old"]["verify_note"] == "前の"
print("VERIFY OK")
