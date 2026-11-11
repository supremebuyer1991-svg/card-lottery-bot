import { runCards, cardsData } from "./cards.js";
import { pushApi, runPush, pushStats } from "./push.js";
import { runNewsets, newsetsStatus } from "./newsets.js";
import { runXQueue, xqueueStatus } from "./xqueue.js";
// 楽天ブックスのトレカの見張り（Cloudflare Worker・1分おき）
// 楽天市場API（shopCode=book）で「注文できない(0)」→「注文できる(1)」に変わった商品を見つけたら、
// Xに楽天アフィリエイトのリンク付きで自動投稿する。前の状態は KV（STATE）に置く。
// ・最初の1回は記録だけ（投稿しない）
// ・同じ商品は6時間あける、1日の投稿は6本まで（APIの値がゆれたときの連投を防ぐ）
const ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const REFERER = "https://toreca-chusen-navi.pages.dev/"; // 楽天に登録してあるアドレス
const QUERIES = [
  ["onepiece", "ONE PIECEカードゲーム ブースターパック"],
  ["onepiece", "ONE PIECEカードゲーム エクストラブースター"],
  ["pokemon", "ポケモンカードゲーム 拡張パック"],
  ["pokemon", "ポケモンカードゲーム 強化拡張パック"],
];
const GAME = {
  onepiece: { head: "ワンピースカード", tags: "#ワンピースカード #PR" },
  pokemon: { head: "ポケカ", tags: "#ポケモンカード #ポケカ #PR" },
};
const COOLDOWN = 6 * 3600e3, PER_DAY = 6;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function search(env, kw) {
  const p = new URLSearchParams({ applicationId: env.RAKUTEN_APP_ID, keyword: kw, shopCode: "book", format: "json",
    formatVersion: "2", hits: "30", availability: "0", sort: "-updateTimestamp" });
  const r = await fetch(`${ENDPOINT}?${p}`, { headers: { accessKey: env.RAKUTEN_ACCESS_KEY, Referer: REFERER,
    Origin: REFERER.slice(0, -1), "User-Agent": "toreca-chusen-navi/1.0" } });
  if (!r.ok) throw new Error(`楽天API ${r.status} ${(await r.text()).slice(0, 120)}`);
  const j = await r.json();
  if (!j.Items) throw new Error(`楽天API 結果なし ${JSON.stringify(j).slice(0, 160)}`);
  return j.Items;
}

function affLink(url, aff) {
  const u = url.split("?")[0];
  return aff ? `https://hb.afl.rakuten.co.jp/hgc/${aff}/?pc=${encodeURIComponent(u)}&m=${encodeURIComponent(u)}` : u;
}

function shortName(n) {
  return n.replace(/ポケモンカードゲーム|ONE PIECEカードゲーム|ＭＥＧＡ|MEGA|スカーレット[＆&]バイオレット|ソード[＆&]シールド/g, "")
    .replace(/【(\d+パック|BOX|クレジットカード決済限定|24パック|30パック|20パック)】/g, "").replace(/\s+/g, " ").trim().slice(0, 40);
}

// ---- X（OAuth 1.0a）----
const pct = (s) => encodeURIComponent(s).replace(/[!'()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());
async function hmac(key, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return btoa(String.fromCharCode(...new Uint8Array(s)));
}
async function tweet(env, text) {
  const url = "https://api.twitter.com/2/tweets";
  const o = { oauth_consumer_key: env.X_API_KEY, oauth_nonce: crypto.randomUUID().replace(/-/g, ""), oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)), oauth_token: env.X_ACCESS_TOKEN, oauth_version: "1.0" };
  const base = ["POST", pct(url), pct(Object.keys(o).sort().map((k) => `${pct(k)}=${pct(o[k])}`).join("&"))].join("&");
  o.oauth_signature = await hmac(`${pct(env.X_API_SECRET)}&${pct(env.X_ACCESS_SECRET)}`, base);
  const auth = "OAuth " + Object.keys(o).sort().map((k) => `${pct(k)}="${pct(o[k])}"`).join(", ");
  const r = await fetch(url, { method: "POST", headers: { Authorization: auth, "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error(`X ${r.status} ${(await r.text()).slice(0, 200)}`);
  return (await r.json()).data?.id;
}

function compose(game, items, aff) {
  // Xはプレミアム（長いポストOK）。ユーザーの指示：発売された商品は全部アフィリンク付きで1つのポストに並べる（念のため最大10個）
  const g = GAME[game], list = items.slice(0, 10), more = items.length - list.length;
  const lines = ["🚨🚨速報🚨🚨", `楽天ブックスで${g.head}が販売開始🔥`, "", "今なら買えます！急いで👇", ""];
  for (const it of list) lines.push(`・${shortName(it.itemName)}`, affLink(it.itemUrl, aff), "");
  if (more > 0) lines.push(`ほか${more}商品も販売中`, "");
  lines.push("⚠️売り切れてもすぐ復活することあり！", "定期的にリンクを見張って👀", "",
    "🔔フォロー＆通知ONで速報が届きます", "", g.tags);
  return lines.join("\n");
}

async function run(env, { dry = false } = {}) {
  const st = (await env.STATE.get("state", "json")) || { items: {}, posted: {}, day: "", count: 0, init: false };
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  if (st.day !== today) { st.day = today; st.count = 0; }
  const found = {}, log = [];
  for (const [game, kw] of QUERIES) {
    try {
      for (const it of await search(env, kw)) {
        if (/セット商品|特典|カードスリーブ|デッキケース/.test(it.itemName)) continue;
        found[it.itemCode] = { ...it, game };
      }
    } catch (e) { log.push(String(e)); }
    await sleep(1300);
  }
  const fresh = {};
  let changed = !st.init && Object.keys(found).length > 0;
  for (const [code, it] of Object.entries(found)) {
    const prev = st.items[code];
    const now = it.availability === 1 ? 1 : 0;
    if (prev !== now) changed = true;
    if (st.init && prev === 0 && now === 1 && !(st.posted[code] && Date.now() - st.posted[code] < COOLDOWN)) {
      (fresh[it.game] = fresh[it.game] || []).push(it);
    }
    st.items[code] = now;
    // サイトの「いま買える」表示用に、名前とURLも覚えておく（新しい商品の時だけ＝保存回数は増えない）
    st.info = st.info || {};
    if (!st.info[code]) { st.info[code] = { n: shortName(it.itemName), u: it.itemUrl, g: it.game }; changed = true; }
  }
  const out = [];
  for (const [game, items] of Object.entries(fresh)) {
    if (st.count >= PER_DAY) { log.push("1日の上限"); break; }
    const text = compose(game, items, env.RAKUTEN_AFF);
    if (dry) { out.push(text); continue; }
    try {
      const id = await tweet(env, text);
      st.count++; changed = true;
      for (const it of items) st.posted[it.itemCode] = Date.now();
      out.push(`posted ${id}`);
    } catch (e) { log.push(String(e)); }
  }
  if (Object.keys(found).length) st.init = true;
  st.last = { at: new Date().toISOString(), found: Object.keys(found).length, avail: Object.values(found).filter((i) => i.availability === 1).length, out, log };
  // KVの保存は無料だと1日1,000回まで。1分おきに動くので、在庫が変わった・投稿した・エラーのときだけ保存する
  if (!dry && (changed || log.length)) await env.STATE.put("state", JSON.stringify(st));
  return st.last;
}

// ---- Amazon（Creators API）----
// Amazon.co.jp 本体が売っている物だけを見る（業者の転売在庫は対象外）。
// 「買えない」→「招待リクエスト受付中」または「販売中」に変わったら速報する（ユーザーの指示）
const AMZ_SELLER = "AN1VRQENFRJN5"; // Amazon.co.jp
const AMZ_TAG = "st9994ststst-22";
const AMZ_QUERIES = [
  ["pokemon", "ポケモンカードゲーム 拡張パック BOX"],
  ["pokemon", "ポケモンカードゲーム 強化拡張パック BOX"],
  ["onepiece", "ONE PIECEカードゲーム ブースターパック BOX"],
  ["onepiece", "ONE PIECEカードゲーム エクストラブースター BOX"],
];
const RANK = { none: 0, invite: 1, buy: 2 };
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
async function amzSearch(env, kw) {
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/searchItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ keywords: kw, searchIndex: "All", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG, itemCount: 10,
      resources: ["itemInfo.title", "offersV2.listings.availability", "offersV2.listings.price", "offersV2.listings.merchantInfo"] }) });
  if (!r.ok) throw new Error(`Amazon ${r.status} ${(await r.text()).slice(0, 160)}`);
  return (await r.json()).searchResult?.items || [];
}
// 11/11：弾ページの JANコード用。Amazon の商品情報（externalIds の EAN＝JAN）を返す。結果は7日間 KV に置く
async function janLookup(env, q) {
  q = String(q || "").slice(0, 80).trim();
  if (q.length < 4) return { error: "q" };
  const key = "jan:" + q;
  const c = await env.STATE.get(key, "json");
  if (c) return c;
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/searchItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ keywords: q, searchIndex: "All", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG, itemCount: 10,
      resources: ["itemInfo.title", "itemInfo.externalIds", "itemInfo.byLineInfo"] }) });
  if (!r.ok) return { error: `Amazon ${r.status}` };
  const items = ((await r.json()).searchResult?.items || []).map((it) => {
    const ids = JSON.stringify(it.itemInfo?.externalIds || {});
    return { asin: it.asin, title: it.itemInfo?.title?.displayValue || "", brand: it.itemInfo?.byLineInfo?.brand?.displayValue || it.itemInfo?.byLineInfo?.manufacturer?.displayValue || "",
      jan: [...new Set(ids.match(/\b4[59]\d{11}\b/g) || [])] };
  });
  const out = { q, at: new Date().toISOString(), items };
  await env.STATE.put(key, JSON.stringify(out), { expirationTtl: 7 * 86400 });
  return out;
}

function amzState(it) {
  const l = (it.offersV2?.listings || []).find((x) => x.merchantInfo?.id === AMZ_SELLER);
  if (!l) return { s: "none" };
  const a = l.availability || {};
  if (/招待/.test(a.message || "")) return { s: "invite", price: l.price?.money?.displayAmount };
  if (/^IN_STOCK/.test(a.type || "") && (a.maxOrderQuantity ?? 1) > 0) return { s: "buy", price: l.price?.money?.displayAmount };
  return { s: "none" };
}
function amzCompose(game, kind, items) {
  // 11/9：見られる数が楽天の1/5だったので、1行目から「何が・いくらで」が分かる形に（商品名と定価を見出しに）
  const g = GAME[game], invite = kind === "invite";
  const first = shortName(items[0]?.itemInfo?.title?.displayValue || "") || g.head;
  const yen = (it) => it._price || "";  // Amazon本体の出品の値段（amzState で入れた値）
  const lines = ["🚨🚨速報🚨🚨", invite ? `Amazon本体で「${first}」の招待リクエスト受付開始🔥` : `Amazon本体で「${first}」が定価で販売開始🔥`,
    invite ? "📩リクエストしておくと、招待された人が定価で買える方式です" : "今なら定価で買えます！急いで👇", ""];
  for (const it of items.slice(0, 10)) {
    const t = shortName(it.itemInfo?.title?.displayValue || "");
    const p = yen(it);
    lines.push(`・${t}${p ? `（${p}）` : ""}`, it.detailPageURL || `https://www.amazon.co.jp/dp/${it.asin}?tag=${AMZ_TAG}`, "");
  }
  if (items.length > 10) lines.push(`ほか${items.length - 10}商品も`, "");
  if (invite) lines.push("✉️招待メールが来ていなくても招待されていることがあるので、ときどき商品ページを確認👀", "");
  lines.push("⚠️売り切れてもすぐ復活することあり！", "定期的にリンクを見張って👀", "", "🔔フォロー＆通知ONで速報が届きます", "",
    g.tags.replace("#PR", "#Amazon #PR"));
  return lines.join("\n");
}
async function runAmazon(env, { dry = false } = {}) {
  if (!env.AMAZON_CREDENTIAL_ID || !env.AMAZON_CREDENTIAL_SECRET) return { skip: "鍵なし" };
  const st = (await env.STATE.get("amz", "json")) || { items: {}, posted: {}, day: "", count: 0, init: false };
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  if (st.day !== today) { st.day = today; st.count = 0; }
  const found = {}, log = [];
  for (const [game, kw] of AMZ_QUERIES) {
    try {
      for (const it of await amzSearch(env, kw)) {
        const t = it.itemInfo?.title?.displayValue || "";
        if (!/ポケモンカード|ONE PIECE|ワンピース/.test(t) || /スリーブ|デッキケース|ローダー|ファイル|セット商品/.test(t)) continue;
        found[it.asin] = { ...it, game };
      }
    } catch (e) { log.push(String(e)); }
    await sleep(1100);
  }
  const fresh = {};
  let changed = !st.init && Object.keys(found).length > 0;
  for (const [asin, it] of Object.entries(found)) {
    const prev = st.items[asin], cur = amzState(it);
    it._price = cur.price;
    if (prev !== cur.s) changed = true;
    // 11/8 ユーザー指摘：ずっと招待受付中のニンジャスピナーを「受付開始」と流した（Amazonの検索結果が一瞬「買えない」になってすぐ戻っただけ）。
    // その状態（招待・販売中）を3日以内に見ていたら、新しく始まったとはみなさない
    st.seen = st.seen || {};
    const seenAt = st.seen[asin + cur.s] || 0;
    const recentlySeen = Date.now() - seenAt < 3 * 86400e3;
    if (cur.s !== "none") { if (Date.now() - seenAt > 6 * 3600e3) changed = true; st.seen[asin + cur.s] = Date.now(); }
    if (cur.s === "buy") st.seen[asin + "invite"] = Date.now();
    if (st.init && prev !== undefined && RANK[cur.s] > RANK[prev] && !recentlySeen && !(st.posted[asin + cur.s] && Date.now() - st.posted[asin + cur.s] < COOLDOWN)) {
      const k = `${it.game}|${cur.s}`;
      (fresh[k] = fresh[k] || []).push(it);
    }
    st.items[asin] = cur.s;
    st.info = st.info || {};
    if (!st.info[asin]) { st.info[asin] = { n: shortName(it.itemInfo?.title?.displayValue || ""), u: it.detailPageURL || `https://www.amazon.co.jp/dp/${asin}?tag=${AMZ_TAG}`, g: it.game }; changed = true; }
  }
  const out = [];
  for (const [k, items] of Object.entries(fresh)) {
    if (st.count >= PER_DAY) { log.push("1日の上限"); break; }
    const [game, kind] = k.split("|");
    const text = amzCompose(game, kind, items);
    if (dry) { out.push(text); continue; }
    try {
      const id = await tweet(env, text);
      st.count++; changed = true;
      for (const it of items) st.posted[it.asin + kind] = Date.now();
      out.push(`posted ${id}`);
    } catch (e) { log.push(String(e)); }
  }
  if (Object.keys(found).length) st.init = true;
  const cnt = (x) => Object.values(st.items).filter((v) => v === x).length;
  st.last = { at: new Date().toISOString(), found: Object.keys(found).length, buy: cnt("buy"), invite: cnt("invite"), out, log };
  if (!dry && (changed || log.length)) await env.STATE.put("amz", JSON.stringify(st));
  return st.last;
}

// ---- 当選・落選の報告（11/7）：サイトの「応募したリスト」から送られる。抽選ごとに数えるだけ（個人の情報は持たない）----
const ORIGINS = ["https://tcg-chusen.com", "https://toreca-chusen-navi.pages.dev"];
function cors(req) {
  const o = req.headers.get("Origin") || "";
  return { "Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
           "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
}
async function sha8(t) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t));
  return [...new Uint8Array(h)].slice(0, 6).map((b) => b.toString(16).padStart(2, "0")).join("");
}
async function report(req, env) {
  let b;
  try { b = await req.json(); } catch { return new Response("bad", { status: 400, headers: cors(req) }); }
  const k = String(b.k || ""), res = b.res, uid = String(b.uid || "");
  if (!/^[\w-]{4,40}$/.test(k) || !["win", "lose", "none"].includes(res) || !/^[\w-]{8,64}$/.test(uid))
    return new Response("bad", { status: 400, headers: cors(req) });
  const key = "r:" + k, cur = (await env.STATE.get(key, "json")) || { s: "", x: "", g: "", u: {} };
  cur.s = String(b.store || cur.s || "").slice(0, 80);
  cur.x = String(b.series || cur.x || "").slice(0, 80);
  cur.g = String(b.game || cur.g || "").slice(0, 20);
  const h = await sha8(uid + k);
  if (res === "none") delete cur.u[h]; else cur.u[h] = res === "win" ? 1 : 0;
  const ks = Object.keys(cur.u);
  if (ks.length > 2000) delete cur.u[ks[0]];
  await env.STATE.put(key, JSON.stringify(cur));
  const v = Object.values(cur.u);
  return Response.json({ ok: true, w: v.filter((x) => x === 1).length, n: v.length }, { headers: cors(req) });
}
async function rates(env) {
  const out = {};
  let cursor;
  do {
    const r = await env.STATE.list({ prefix: "r:", cursor });
    for (const k of r.keys) {
      const v = await env.STATE.get(k.name, "json");
      if (!v) continue;
      const vs = Object.values(v.u || {});
      out[k.name.slice(2)] = { s: v.s, x: v.x, g: v.g, w: vs.filter((x) => x === 1).length, n: vs.length };
    }
    cursor = r.list_complete ? null : r.cursor;
  } while (cursor);
  return out;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(env));
    // Amazonは2分おき（APIの回数に余裕を持たせる）
    if (new Date(event.scheduledTime).getUTCMinutes() % 2 === 0) ctx.waitUntil(runAmazon(env));
    // 締切の通知は10分おき（11/7）
    if (new Date(event.scheduledTime).getUTCMinutes() % 10 === 3) ctx.waitUntil(runPush(env));
    // 大手の抽選の予告・受付開始ポスト（11/9）：ユーザーの指示で「Xの予約投稿」で出すことにしたので、ここからは出さない（予約は Claude の予定の作業がブラウザで入れる）
    // ctx.waitUntil(runXQueue(env, tweet));
    // 新弾の発表の見張り：10分おき（11/8）
    if (new Date(event.scheduledTime).getUTCMinutes() % 10 === 6) ctx.waitUntil(runNewsets(env, tweet));
    if (new Date(event.scheduledTime).getUTCMinutes() % 30 === 9) ctx.waitUntil(runCards(env));  // 弾ごとの収録カードの相場（11/11）。KV の書き込み（無料枠1日1,000回）を食うので30分おき
  },
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === "/report") {
      if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
      if (req.method === "POST") return report(req, env);
    }
    if (u.pathname.startsWith("/push/")) {
      if (req.method === "OPTIONS") return new Response(null, { headers: cors(req) });
      if (u.pathname === "/push/stats") return Response.json(await pushStats(env));
      if (u.pathname === "/push/run" && u.searchParams.get("k") === env.ADMIN_KEY) return Response.json(await runPush(env));
      if (u.pathname === "/push/key" || req.method === "POST") return pushApi(req, env, u.pathname, cors(req));
    }
    if (u.pathname === "/stock") {  // サイト用：いま楽天ブックス・Amazon.co.jp本体で買える（または招待リクエスト受付中の）商品
      const st = (await env.STATE.get("state", "json")) || {}, az = (await env.STATE.get("amz", "json")) || {};
      const rk = Object.entries(st.items || {}).filter(([, v]) => v === 1).map(([k]) => ({ ...(st.info || {})[k], a: "buy" })).filter((x) => x.n);
      const am = Object.entries(az.items || {}).filter(([, v]) => v === "buy" || v === "invite").map(([k, v]) => ({ ...(az.info || {})[k], a: v })).filter((x) => x.n);
      return Response.json({ at: st.last?.at, amz_at: az.last?.at, rakuten: rk, amazon: am }, { headers: { "Cache-Control": "max-age=60" } });
    }
    if (u.pathname === "/snkrtest" && u.searchParams.get("k") === env.ADMIN_KEY) {  // 11/11：Cloudflare からスニダンが読めるかの試し
      const out = {};
      for (const [k, url] of [["search", "https://snkrdunk.com/search?keywords=" + encodeURIComponent(u.searchParams.get("q") || "ハドウシーカー SAR")],
                              ["hist", "https://snkrdunk.com/v3/products/1035491/trading-history?range=month"]]) {
        try { const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "ja" } });
          const t = await r.text(); out[k] = { status: r.status, len: t.length, head: t.slice(0, 200), apparels: (t.match(/apparels\/\d+/g) || []).length };
        } catch (e) { out[k] = { error: String(e) }; }
      }
      return Response.json(out);
    }
    if (u.pathname === "/cards") return Response.json(await cardsData(env, u.searchParams.get("set")), { headers: { "Cache-Control": "max-age=300" } });  // ?set=キー でその弾、なしで目次
    if (u.pathname === "/cards/status") { const d = await cardsData(env); const v = Object.values(d.sets || {}); return Response.json({ last: d.last, total: { sets: v.length, found: v.filter((x) => x.n).length, cards: v.reduce((a, x) => a + (x.n || 0), 0), priced: v.reduce((a, x) => a + (x.priced || 0), 0) }, sets: d.sets }); }
    if (u.pathname === "/jan") {
      try { return Response.json(await janLookup(env, u.searchParams.get("q"))); } catch (e) { return Response.json({ error: String(e).slice(0, 120) }); }
    }
    if (u.pathname === "/xqueue") return Response.json(await xqueueStatus(env));
    if (u.pathname === "/newsets") return Response.json(await newsetsStatus(env));
    if (u.pathname === "/newsets/dry") return Response.json(await runNewsets(env, tweet, { dry: true }));
    if (u.pathname === "/rates") return Response.json(await rates(env), { headers: { "Cache-Control": "max-age=300" } });
    if (u.pathname === "/status") {
      const st = (await env.STATE.get("state", "json")) || {};
      const az = (await env.STATE.get("amz", "json")) || {};
      return Response.json({ last: st.last, count: st.count, items: Object.keys(st.items || {}).length, amazon: { last: az.last, count: az.count, items: Object.keys(az.items || {}).length } });
    }
    if (u.pathname === "/dry" && u.searchParams.get("k") === env.ADMIN_KEY) return Response.json(await run(env, { dry: true }));
    if (u.pathname === "/dry-amazon" && u.searchParams.get("k") === env.ADMIN_KEY) return Response.json(await runAmazon(env, { dry: true }));
    return new Response("ok");
  },
};
