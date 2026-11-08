"""スニダンでゲーム機・ホビーの商品が取引されているか探す（probe-game.yml の mode=snkr）"""
import os, re, time
from html import unescape
import requests
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept-Language": "ja"})
words = os.environ.get("URLS", "").split("|") if os.environ.get("URLS") else [
    "PS5 Pro", "PlayStation 5 デジタル・エディション", "PlayStation 5 ミッドナイト ブラック", "Nintendo Switch 2", "Switch 2 マリオカート ワールド セット",
    "Switch 2 選べるソフト", "ROG Xbox Ally X", "Steam Deck OLED", "PlayStation Portal", "DualSense",
    "HG ガンダム", "MG ガンダム", "PG ガンダム", "ポケモンセンター 限定", "ベイブレードX", "一番くじ", "ちいかわ", "amiibo"]
for w in words:
    try:
        html = s.get("https://snkrdunk.com/search", params={"keywords": w}, timeout=30).text
        hits = []
        for m in re.finditer(r'href=\\?"https://snkrdunk\.com/(apparels|sneakers|products)/([\w-]+)\\?"[^>]*aria-label=\\?"([^"\\]+)', html):
            hits.append(f"{m.group(1)}/{m.group(2)} {unescape(m.group(3))[:60]}")
        print(f"### {w}: {len(hits)}件")
        for h in hits[:8]:
            print("  ", h)
    except Exception as e:
        print(f"### {w}: ERROR {e}")
    time.sleep(1.5)
