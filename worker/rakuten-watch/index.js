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
  const g = GAME[game];
  const lines = [`🚨楽天ブックスで販売開始｜${g.head}`, "", "楽天ブックスで購入できるようになっています！", ""];
  for (const it of items.slice(0, 3)) lines.push(`・${shortName(it.itemName)}`, affLink(it.itemUrl, aff), "");
  lines.push("⚠️売り切れても、すぐに復活することがあります！", "売り切れていても、定期的にリンクを見張ってみてください👀", "",
    "🔔フォロー＆通知ONで、販売・抽選の速報を受け取れます", "", g.tags);
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

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil(run(env)); },
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === "/status") {
      const st = (await env.STATE.get("state", "json")) || {};
      return Response.json({ last: st.last, count: st.count, items: Object.keys(st.items || {}).length });
    }
    if (u.pathname === "/dry" && u.searchParams.get("k") === env.ADMIN_KEY) return Response.json(await run(env, { dry: true }));
    return new Response("ok");
  },
};
