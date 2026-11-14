"""Creators APIがつながるかの確認（鍵の中身は出力しない）"""
import json, os, requests
out = {"have": {k: bool(os.environ.get(k)) for k in ["AMAZON_CREDENTIAL_ID", "AMAZON_CREDENTIAL_SECRET", "AMAZON_CREDENTIAL_VERSION"]}}
ver = (os.environ.get("AMAZON_CREDENTIAL_VERSION") or "").strip()
out["version"] = ver
tok_url = {"3.1": "https://api.amazon.com/auth/o2/token", "3.2": "https://api.amazon.co.uk/auth/o2/token"}.get(ver, "https://api.amazon.co.jp/auth/o2/token")
try:
    r = requests.post(tok_url, json={"grant_type": "client_credentials", "client_id": os.environ["AMAZON_CREDENTIAL_ID"].strip(),
                                     "client_secret": os.environ["AMAZON_CREDENTIAL_SECRET"].strip(), "scope": "creatorsapi::default"}, timeout=20)
    out["token_status"] = r.status_code
    tok = r.json().get("access_token") if r.ok else None
    if not r.ok:
        out["token_err"] = r.text[:300]
except Exception as e:
    tok = None; out["token_exc"] = str(e)[:300]
if tok:
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp"}
    # 11/14：写真（images）が取れるか・リソース名の確認。キーワードはソニー α7 IV のJAN
    for res in (["itemInfo.title", "itemInfo.externalIds", "images.primary.medium", "images.primary.large"], ["itemInfo.title", "images.primary.medium"], ["itemInfo.title"]):
        body = {"keywords": "4548736133730", "searchIndex": "All", "marketplace": "www.amazon.co.jp",
                "partnerTag": "st9994ststst-22", "itemCount": 3, "resources": res}
        r = requests.post("https://creatorsapi.amazon/catalog/v1/searchItems", headers=h, json=body, timeout=20)
        out.setdefault("search", []).append({"res": res, "status": r.status_code, "body": r.text[:6000]})
        if r.ok and len(out["search"]) >= 2:
            break
os.makedirs("state", exist_ok=True)
json.dump(out, open("state/amazon_probe.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "search"}, ensure_ascii=False))
