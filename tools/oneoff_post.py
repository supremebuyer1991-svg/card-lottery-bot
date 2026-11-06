"""oneoff/post.txt（と oneoff/post.png）を、指定の時刻（POST_AT, JST）にXへ1回だけ投稿する"""
import os, sys, time
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "src")
import xpost
at = os.environ.get("POST_AT")
if at:
    t = datetime.fromisoformat(at).replace(tzinfo=timezone(timedelta(hours=9)))
    wait = (t - datetime.now(timezone.utc)).total_seconds()
    if 0 < wait < 3600:
        print(f"{int(wait)}秒待ちます"); time.sleep(wait)
text = open("oneoff/post.txt", encoding="utf-8").read().strip()
mid = xpost.upload_image(open("oneoff/post.png", "rb").read()) if os.path.exists("oneoff/post.png") else None
r = xpost._client().create_tweet(text=text, media_ids=[mid] if mid else None)
print("投稿しました", r.data.get("id"), "画像あり" if mid else "画像なし")
