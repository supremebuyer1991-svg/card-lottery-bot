// ゲーム・ホビー入荷速報：楽天ブックス・Amazon の見張り（Cloudflare Worker）
// サイトの https://game-nyuka.com/watch.json（ボットが毎回作る）の商品を見て、
// ・楽天：「注文できない」→「注文できる」
// ・Amazon：Amazon.co.jp 本体の販売が「なし」→「招待リクエスト受付中」「販売中」（転売業者の在庫は見ない）
// に変わったら、@a9994aaa にアフィリンク付きで速報する（PRの表記はXのプロフィールにあるので本文には書かない）。
// ・速報は「売り切れ（2回以上・30分以上続けて確認）→ 販売中・予約受付中」に切り替わった時だけ（前から売っているものは出さない）
// ・検索で見つからなかっただけの時は売り切れと数えない ・同じ商品は6時間あける
// ・相場の商品（watch.json の jan）は JAN で楽天ブックス・Amazon の商品ページを探し、見つけたページは /map でサイトに渡す
// ・1回に見る数を決めて順番に回す（プレ値の商品は回ってくる間隔が短い）。定価の110%より高い売値は「定価で買える」とみなさない
// ・1日12本まで（ホビーは3本まで。ゲームが本業のアカウントのため）
const WATCH = "https://game-nyuka.com/watch.json";
const ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const REFERER = "https://toreca-chusen-navi.pages.dev/"; // 楽天に登録してあるアドレス
const AMZ_SELLER = "AN1VRQENFRJN5"; // Amazon.co.jp
const AMZ_TAG = "st9994ststst-22";
const COOLDOWN = 6 * 3600e3, PER_DAY = 12, HOBBY_PER_DAY = 3;
const RANK = { none: 0, invite: 1, pre: 2, buy: 3 };
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
async function amzItem(env, asin, byJan = false) {
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/searchItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ keywords: asin, searchIndex: "All", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG, itemCount: 3,
      resources: ["itemInfo.title", "offersV2.listings.availability", "offersV2.listings.price", "offersV2.listings.merchantInfo"] }) });
  if (!r.ok) throw new Error(`Amazon ${r.status} ${(await r.text()).slice(0, 160)}`);
  const items = (await r.json()).searchResult?.items || [];
  return byJan ? items[0] : items.find((x) => x.asin === asin);
}
function amzState(it) {
  const l = ((it && it.offersV2?.listings) || []).find((x) => x.merchantInfo?.id === AMZ_SELLER);
  if (!l) return "none";
  const a = l.availability || {};
  if (/招待/.test(a.message || "")) return "invite";
  if (/PRE_?ORDER/i.test(a.type || "") || /予約/.test(a.message || "")) return "pre";   // 予約受付中（11/9 ユーザー指摘：Switch2選べるソフトセットの予約を拾えていなかった）
  if (/^IN_STOCK/.test(a.type || "") && (a.maxOrderQuantity ?? 1) > 0) return "buy";
  return "none";
}

function compose(w, shop, kind, url) {
  const where = shop === "rk" ? "楽天ブックス" : "Amazon";
  const head = `${where}で` + (kind === "invite" ? "招待リクエスト受付再開🔥" : kind === "pre" ? "予約受付再開🔥" : "販売再開🔥") + "（売り切れ→在庫あり）";
  const lines = ["🚨速報🚨 " + head, "", `【${w.n}】`, ...(w.pm ? [`💰定価以上で売れてる商品（${w.pm}）`] : []), "", kind === "pre" ? "定価で予約できます👇" : shop === "az" ? "Amazon.co.jp本体の販売です👇" : "定価で買えます👇", url, ""];
  if (kind === "invite") lines.push("📩リクエストして、招待メールが届いた人が買える方式です", "");
  lines.push("⚠️売り切れてもすぐ復活することあり", "🔔通知ONで速報が届きます", (w.tag || []).join(" "));
  return lines.join("\n");
}

// 見張る順番：その回の分だけ見る（全部を毎回は見ない）。プレ値の商品（hot）は回ってくる間隔を短く
function batch(list, n, salt) {
  const hot = list.filter((w) => w.hot || w.rk || w.asin), rest = list.filter((w) => !(w.hot || w.rk || w.asin));
  const turn = Math.floor(Date.now() / 120e3) + salt;
  const pick = (arr, k) => { if (!arr.length) return []; const out = []; const s0 = (turn * k) % arr.length; for (let i = 0; i < Math.min(k, arr.length); i++) out.push(arr[(s0 + i) % arr.length]); return out; };
  const nh = Math.min(hot.length, Math.ceil(n / 2));
  return [...pick(hot, nh), ...pick(rest, n - nh)];
}
const yen = (s) => Number(String(s || "").replace(/[^\d]/g, "")) || 0;

async function rakutenByJan(env, jan) {
  const p = new URLSearchParams({ applicationId: env.RAKUTEN_APP_ID, keyword: jan, shopCode: "book", hits: "3", format: "json", formatVersion: "2", availability: "0" });
  const r = await fetch(`${ENDPOINT}?${p}`, { headers: { accessKey: env.RAKUTEN_ACCESS_KEY, Referer: REFERER, Origin: REFERER.slice(0, -1), "User-Agent": "game-nyuka/1.0" } });
  if (!r.ok) throw new Error(`楽天API ${r.status} ${(await r.text()).slice(0, 120)}`);
  return ((await r.json()).Items || [])[0];
}

async function run(env, which, { dry = false } = {}) {
  const key = which === "rk" ? "rk" : "az";
  const st = (await env.STATE.get(key, "json")) || { items: {}, posted: {}, off: {}, map: {}, day: "", count: 0, hobby: 0, init: {} };
  st.off = st.off || {}; st.map = st.map || {}; st.init = typeof st.init === "object" ? st.init : {};
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  if (st.day !== today) { st.day = today; st.count = 0; st.hobby = 0; }
  const log = [], out = [];
  let changed = false, n = 0;
  let list = [];
  try { list = await watchList(); } catch (e) { log.push(String(e)); }
  list = list.filter((w) => (which === "rk" ? (w.rk || w.jan) : (w.asin || w.jan)));
  for (const w of batch(list, which === "rk" ? 12 : 6, which === "rk" ? 0 : 7)) {
    const id = which === "rk" ? (w.rk || "j" + w.jan) : (w.asin || "j" + w.jan);
    let cur = "none", url = "", price = 0;
    try {
      if (which === "rk") {
        const it = w.rk ? await rakutenItem(env, w.rk) : await rakutenByJan(env, w.jan);
        if (!it) { await sleep(1100); continue; }   // 見つからなかっただけ（売り切れとは数えない）
        if (it) {
          price = Number(it.itemPrice) || 0;
          cur = it.availability === 1 ? (/予約/.test((it.itemName || "") + (it.itemCaption || "").slice(0, 200)) ? "pre" : "buy") : "none";
          url = affLink(it.itemUrl, env.RAKUTEN_AFF);
          if (w.jan && !st.map[w.jan]) { st.map[w.jan] = { rkUrl: it.itemUrl.split("?")[0], img: (it.mediumImageUrls || [])[0] ? String(it.mediumImageUrls[0]).split("?")[0] + "?_ex=300x300" : "", rkPrice: price }; changed = true; }
        }
      } else {
        const it = await amzItem(env, w.asin || w.jan, !w.asin);
        if (!it) { await sleep(1100); continue; }   // 見つからなかっただけ（売り切れとは数えない）
        cur = amzState(it);
        const l = ((it && it.offersV2?.listings) || []).find((x) => x.merchantInfo?.id === AMZ_SELLER);
        price = yen(l?.price?.money?.amount ?? l?.price?.money?.displayAmount);
        url = (it && it.detailPageURL) || (it ? `https://www.amazon.co.jp/dp/${it.asin}?tag=${AMZ_TAG}` : "");
        if (w.jan && it && !st.map[w.jan]) { st.map[w.jan] = { asin: it.asin, azUrl: url }; changed = true; }
      }
    } catch (e) { log.push(String(e).slice(0, 160)); await sleep(1500); continue; }
    await sleep(1100);
    n++;
    // 定価より高い値段で売っているものは「定価で買える」とは言わない（定価が分かるときだけ。110%まで）
    if (cur !== "none" && w.tk && price && price > w.tk * 1.1) cur = "none";
    const prev = st.items[id];
    st.stat = st.stat || {};
    if (prev !== cur) changed = true;
    if (!st.stat[id] || st.stat[id].s !== cur || (cur !== "none" && st.stat[id].p !== price)) { st.stat[id] = { s: cur, p: price, u: url, at: new Date().toISOString() }; changed = true; }
    // 売り切れの確認：売り切れ（none）を2回以上・30分以上続けて見たら「本当に売り切れ」（11/9 ユーザーの指示：売り切れ→販売に切り替わった時だけ速報）
    st.soldout = st.soldout || {};
    const so = st.soldout[id];
    if (cur === "none") { if (!so) { st.soldout[id] = { since: Date.now(), n: 1 }; changed = true; } else if (so.n < 2) { so.n++; changed = true; } }
    const confirmed = so && so.n >= 2 && Date.now() - so.since >= 30 * 60e3;
    if (cur !== "none" && so) { delete st.soldout[id]; changed = true; }
    // 速報：前に「本当に売り切れ」を見ていて、いま販売中・予約受付中・招待受付中に変わった時だけ。前から売っているものは出さない
    const fresh = st.init[id] && prev === "none" && cur !== "none" && confirmed && !(st.posted[id + cur] && Date.now() - st.posted[id + cur] < COOLDOWN);
    if (!st.init[id]) { st.init[id] = 1; changed = true; }
    st.items[id] = cur;
    if (!fresh) continue;
    // 相場の商品は「買う価値のある」ものだけ速報：プレ値、または最高買取が売値（定価）の95%以上
    const ref = w.tk || price;
    if (w.jan && !w.rk && !w.asin && !(w.hot || (w.mx && ref && w.mx >= ref * 0.95))) continue;
    if (st.count >= PER_DAY || (!w.g && st.hobby >= HOBBY_PER_DAY)) { log.push("1日の上限"); continue; }
    const text = compose(w, which, cur, url);
    if (dry) { out.push(text); continue; }
    try {
      const tid = await tweet(env, text);
      st.count++; if (!w.g) st.hobby++; st.posted[id + cur] = Date.now(); changed = true;
      out.push(`posted ${tid}`);
    } catch (e) { log.push(String(e)); }
  }
  st.last = { at: new Date().toISOString(), checked: n, total: list.length, out, log };
  // KVの保存は無料だと1日1,000回まで：在庫が変わった・新しく見つけた・投稿した・エラーのときだけ
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
    if (u.pathname === "/mark") {   // 手で投稿した商品に「投稿済み」の印（見張りの速報と二重にならないように）。?id=ASIN&s=pre&w=az
      const k = u.searchParams.get("w") === "rk" ? "rk" : "az", st = (await env.STATE.get(k, "json")) || { items: {}, posted: {} };
      const id = u.searchParams.get("id"), sv = u.searchParams.get("s") || "pre";
      const before = (st.posted || {})[id + sv] || 0;
      if (u.searchParams.get("check") === "1") return Response.json({ postedAt: before });
      st.posted = st.posted || {}; st.posted[id + sv] = Date.now(); st.posted[id + "buy"] = Date.now();
      await env.STATE.put(k, JSON.stringify(st));
      return Response.json({ ok: true, postedBefore: before });
    }
    if (u.pathname === "/map") {   // JANで見つけた楽天・Amazonの商品ページ（サイトのボタン・写真に使う）
      const rk = (await env.STATE.get("rk", "json")) || {}, az = (await env.STATE.get("az", "json")) || {};
      const m = {};
      for (const [j, v] of Object.entries(rk.map || {})) m[j] = { ...(m[j] || {}), ...v };
      for (const [j, v] of Object.entries(az.map || {})) m[j] = { ...(m[j] || {}), ...v };
      m._status = { ...((rk.stat) || {}), ...((az.stat) || {}) };   // いまの状態（予約受付中・販売中など）：サイトの目立つところに出す
      return Response.json(m);
    }
    if (u.pathname === "/dry") return Response.json({ rk: await run(env, "rk", { dry: true }), az: await run(env, "az", { dry: true }) });
    return Response.json({ rk: (await env.STATE.get("rk", "json"))?.last, az: (await env.STATE.get("az", "json"))?.last });
  },
};
