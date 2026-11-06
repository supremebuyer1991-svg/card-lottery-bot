"""当選・落選の報告（サイトの「応募したリスト」→ Worker）を集めて state/winrates.json に保存する（11/7）"""
import requests

from common import save_json, log

URL = "https://rakuten-watch.supreme-buyer-1991.workers.dev/rates"


def update_winrates():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "tcg-chusen-bot/1.0"})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            save_json("winrates.json", data)
            log(f"当選の報告: {len(data)}件の抽選・{sum(v.get('n', 0) for v in data.values())}人分")
    except Exception as e:
        log(f"当選の報告: 取得できず {e}")
