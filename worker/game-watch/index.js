// ゲーム・ホビー入荷速報：楽天ブックス・Amazon の見張り（Cloudflare Worker）
// サイトの https://game-nyuka.com/watch.json（ボットが毎回作る）の商品を見て、
// ・楽天：「注文できない」→「注文できる」
// ・Amazon：Amazon.co.jp 本体の販売が「なし」→「招待リクエスト受付中」「販売中」（転売業者の在庫は見ない）
// に変わったら、@a9994aaa にアフィリンク付き（PR表記）で速報する。
// ・最初の1回は記録だけ ・同じ商品は6時間あける ・その状態を3日以内に見ていたら新しく始まったとはみなさない
// ・1日6本まで（ホビーは1本まで。ゲームが本業のアカウントのため）
const WATCH = "https://game-nyuka.com/watch.json";
const ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const REFERER = "https://toreca-chusen-navi.pages.dev/"; // 楽天に登録してあるアドレス
const AMZ_SELLER = "AN1VRQENFRJN5"; // Amazon.co.jp
const AMZ_TAG = "st9994ststst-22";
const COOLDOWN = 6 * 3600e3, PER_DAY = 6, HOBBY_PER_DAY = 1;
const RANK = { none: 0, invite: 1, buy: 2 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function affLink(url, aff) {
  const u = url.split("?")[0];
  return aff ? `https://hb.afl.rakuten.co.jp/hgc/${aff}/?pc=${encodeURIComponent(u)}&m=${encodeURIComponent(u)}` : u;
}

// ---- X（OAuth 1.0a・@a9994aaa）----
const pct = (s) => encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
async function hmac(key, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return btoa(String.fromCharCode(...new Uint8Array(s)));
}
async function tweet(env, text) {
  const url = "https://api.twitter.com/2/tweets";
  const o = { oauth_consumer_key: env.X_API_KEY, oauth_nonce: crypto.randomUUID().replace(/-/g, ""), oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)), oauth_token: env.X_GAME_ACCESS_TOKEN, oauth_version: "1.0" };
  const base = ["POST", pct(url), pct(Object.keys(o).sort().map((k) => `${pct(k)}=${pct(o[k])}`).join("&"))].join("&");
  o.oauth_signature = await hmac(`${pct(env.X_API_SECRET)}&${pct(env.X_GAME_ACCESS_SECRET)}`, base);
  const auth = "OAuth " + Object.keys(o).sort().map((k) => `${pct(k)}="${pct(o[k])}"`).join(", ");
  const r = await fetch(url, { method: "POST", headers: { Authorization: auth, "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error(`X ${r.status} ${(await r.text()).slice(0, 200)}`);
  return (await r.json()).data?.id;
}

async function watchList() {
  const r = await fetch(WATCH, { cf: { cacheTtl: 300 } });
  if (!r.ok) throw new Error(`watch.json ${r.status}`);
  return (await r.json()).items || [];
}

// ---- 楽天 ----
async function rakutenItem(env, code) {
  const p = new URLSearchParams({ applicationId: env.RAKUTEN_APP_ID, itemCode: code, format: "json", formatVersion: "2", availability: "0" });
  const r = await fetch(`${ENDPOINT}?${p}`, { headers: { accessKey: env.RAKUTEN_ACCESS_KEY, Referer: REFERER, Origin: REFERER.slice(0, -1), "User-Agent": "game-nyuka/1.0" } });
  if (!r.ok) throw new Error(`楽天API ${r.status} ${(await r.text()).slice(0, 120)}`);
  return ((await r.json()).Items || [])[0];
}

// ---- Amazon（Creators API）----
let amzTok = null;
async function amzToken(env) {
  if (amzTok && amzTok.exp > Date.now() + 60e3) return amzTok.v;
  const r = await fetch("https://api.amazon.co.jp/auth/o2/token", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "client_credentials", client_id: env.AMAZON_CREDENTIAL_ID, client_secret: env.AMAZON_CREDENTIAL_SECRET, scope: "creatorsapi::default" }) });
  if (!r.ok) throw new Error(`Amazonトークン ${r.status} ${(await r.text()).slice(0, 120)}`);
  const j = await r.json();
  amzTok = { v: j.access_token, exp: Date.now() + (j.expires_in || 3600) * 1000 };
  return amzTok.v;
}
async function amzItem(env, asin) {
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/searchItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ keywords: asin, searchIndex: "All", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG, itemCount: 3,
      resources: ["itemInfo.title", "offersV2.listings.availability", "offersV2.listings.price", "offersV2.listings.merchantInfo"] }) });
  if (!r.ok) throw new Error(`Amazon ${r.status} ${(await r.text()).slice(0, 160)}`);
  return ((await r.json()).searchResult?.items || []).find((x) => x.asin === asin);
}
function amzState(it) {
  const l = ((it && it.offersV2?.listings) || []).find((x) => x.merchantInfo?.id === AMZ_SELLER);
  if (!l) return "none";
  const a = l.availability || {};
  if (/招待/.test(a.message || "")) return "invite";
  if (/^IN_STOCK/.test(a.type || "") && (a.maxOrderQuantity ?? 1) > 0) return "buy";
  return "none";
}

function compose(w, shop, kind, url) {
  const head = shop === "rk" ? "楽天ブックスで販売開始🔥" : kind === "invite" ? "Amazonで招待リクエスト受付開始🔥" : "Amazonで販売開始🔥";
  const lines = ["🚨速報🚨 " + head, "", `【${w.n}】`, ...(w.pm ? [`💰定価以上で売れてる商品（${w.pm}）`] : []), "", shop === "az" ? "Amazon.co.jp本体の販売です👇（PR）" : "定価で買えます👇（PR）", url, ""];
  if (kind === "invite") lines.push("📩リクエストして、招待メールが届いた人が買える方式です", "");
  lines.push("⚠️売り切れてもすぐ復活することあり", "🔔通知ONで速報が届きます", (w.tag || []).join(" "));
  return lines.join("\n");
}

async function run(env, which, { dry = false } = {}) {
  const key = which === "rk" ? "rk" : "az";
  const st = (await env.STATE.get(key, "json")) || { items: {}, posted: {}, seen: {}, day: "", count: 0, hobby: 0, init: false };
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  if (st.day !== today) { st.day = today; st.count = 0; st.hobby = 0; }
  const log = [], out = [];
  let changed = false, n = 0;
  let list = [];
  try { list = (await watchList()).filter((w) => (which === "rk" ? w.rk : w.asin)); } catch (e) { log.push(String(e)); }
  for (const w of list.slice(0, 20)) {
    const id = which === "rk" ? w.rk : w.asin;
    let cur, url;
    try {
      if (which === "rk") {
        const it = await rakutenItem(env, id);
        cur = it && it.availability === 1 ? "buy" : "none";
        url = it ? affLink(it.itemUrl, env.RAKUTEN_AFF) : "";
        await sleep(1100);
      } else {
        const it = await amzItem(env, id);
        cur = amzState(it);
        url = (it && it.detailPageURL) || `https://www.amazon.co.jp/dp/${id}?tag=${AMZ_TAG}`;
        await sleep(1100);
      }
    } catch (e) { log.push(String(e)); continue; }
    n++;
    const prev = st.items[id];
    const seenAt = st.seen[id + cur] || 0, recentlySeen = Date.now() - seenAt < 3 * 86400e3;
    if (cur !== "none") { if (Date.now() - seenAt > 6 * 3600e3) changed = true; st.seen[id + cur] = Date.now(); }
    if (prev !== cur) changed = true;
    const fresh = st.init && prev !== undefined && RANK[cur] > RANK[prev] && !recentlySeen && !(st.posted[id + cur] && Date.now() - st.posted[id + cur] < COOLDOWN);
    st.items[id] = cur;
    if (!fresh) continue;
    if (st.count >= PER_DAY || (!w.g && st.hobby >= HOBBY_PER_DAY)) { log.push("1日の上限"); continue; }
    const text = compose(w, which, cur, url);
    if (dry) { out.push(text); continue; }
    try {
      const tid = await tweet(env, text);
      st.count++; if (!w.g) st.hobby++; st.posted[id + cur] = Date.now(); changed = true;
      out.push(`posted ${tid}`);
    } catch (e) { log.push(String(e)); }
  }
  if (n) { if (!st.init) changed = true; st.init = true; }
  st.last = { at: new Date().toISOString(), checked: n, out, log };
  if (!dry && (changed || log.length)) await env.STATE.put(key, JSON.stringify(st));
  return st.last;
}

export default {
  async scheduled(event, env, ctx) {
    const m = new Date(event.scheduledTime).getUTCMinutes();
    if (env.RAKUTEN_APP_ID) ctx.waitUntil(run(env, "rk"));
    if (env.AMAZON_CREDENTIAL_ID && m % 4 === 0) ctx.waitUntil(run(env, "az"));
  },
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.searchParams.get("k") !== env.ADMIN_KEY) return new Response("game-watch", { status: 200 });
    if (u.pathname === "/dry") return Response.json({ rk: await run(env, "rk", { dry: true }), az: await run(env, "az", { dry: true }) });
    return Response.json({ rk: (await env.STATE.get("rk", "json"))?.last, az: (await env.STATE.get("az", "json"))?.last });
  },
};
