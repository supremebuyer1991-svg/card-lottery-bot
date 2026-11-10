// ゲーム・ホビー入荷速報：楽天ブックス・Amazon の見張り（Cloudflare Worker）
// サイトの https://game-nyuka.com/watch.json（ボットが毎回作る）の商品を見て、
// ・楽天：「注文できない」→「注文できる」
// ・Amazon：Amazon.co.jp 本体の販売が「なし」→「招待リクエスト受付中」「販売中」（転売業者の在庫は見ない）
// に変わったら、@a9994aaa にアフィリンク付きで速報する（PRの表記はXのプロフィールにあるので本文には書かない）。
// ・速報は「売り切れ → 販売中・予約受付中」に切り替わった時だけ（前から売っているものは出さない）
// ・検索で見つからなかっただけの時は売り切れと数えない ・同じ商品は6時間あける
// ・相場の商品（watch.json の jan）は JAN で楽天ブックス・Amazon の商品ページを探し、見つけたページは /map でサイトに渡す
// ・1回に見る数を決めて順番に回す（プレ値の商品は回ってくる間隔が短い）。定価の110%より高い売値は「定価で買える」とみなさない
// ・1日12本まで（ホビーは3本まで。ゲームが本業のアカウントのため）
const WATCH = "https://game-nyuka.com/watch.json";
const ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const REFERER = "https://toreca-chusen-navi.pages.dev/"; // 楽天に登録してあるアドレス
const AMZ_SELLER = "AN1VRQENFRJN5"; // Amazon.co.jp
const AMZ_TAG = "st9994ststst-22";
const COOLDOWN = 6 * 3600e3, PER_DAY = 12, HOBBY_PER_DAY = 3, SCARCE_DAYS = 3;   // 3日以上売り切れが続いた＝品薄
const RANK = { none: 0, invite: 1, pre: 2, buy: 3 };
// 1回（2分ごと）に見る数（11/9 ユーザー：できるだけ速く）：楽天は1件ずつ・1秒に1回まで、Amazonは10件ずつまとめて
const RK_PER_RUN = 40, AZ_BATCH = 40, AZ_SEARCH = 2;
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
// 商品名がどれだけ合っているか（0〜1）：こちらの商品名の2文字の組が、Amazonの商品名にどれだけ入っているか
// 11/10 ユーザー指摘：JANで検索したAmazonの1件目が別の商品で、速報のリンクがサイトの商品と違っていた → 名前が合わないものは使わない
function norm(t) { return String(t || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").normalize("NFKC").toLowerCase().replace(/[（(【\[][^）)】\]]*[）)】\]]/g, " ").replace(/[\s・\-_/／,.、。!！?？+＋:：'"]/g, ""); }
function sim(name, title) {
  const a = norm(name), b = norm(title);
  if (a.length < 2 || !b) return 0;
  const grams = new Set(); for (let i = 0; i < a.length - 1; i++) grams.add(a.slice(i, i + 2));
  let hit = 0; for (const g of grams) if (b.includes(g)) hit++;
  return hit / grams.size;
}
const SIM_MIN = 0.5;
const amzTitle = (it) => (it && (it.itemInfo?.title?.displayValue || it.itemInfo?.title?.value)) || "";

async function amzItem(env, asin, byJan = false, name = "") {
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/searchItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ keywords: asin, searchIndex: "All", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG, itemCount: 3,
      resources: ["itemInfo.title", "offersV2.listings.availability", "offersV2.listings.price", "offersV2.listings.merchantInfo"] }) });
  if (!r.ok) throw new Error(`Amazon ${r.status} ${(await r.text()).slice(0, 160)}`);
  const items = (await r.json()).searchResult?.items || [];
  if (!byJan) return items.find((x) => x.asin === asin);
  // JANで探した時は、商品名がいちばん合うものだけ（合うものが無ければ「見つからない」扱い）
  let best = null, bs = 0;
  for (const x of items) { const v = name ? sim(name, amzTitle(x)) : 1; if (v > bs) { bs = v; best = x; } }
  return bs >= SIM_MIN ? best : null;
}
// 10件まとめて調べる（11/9：見張りを速くするため）。失敗したら null（呼び出し側で1件ずつの検索に戻す）
async function amzItems(env, asins) {
  const r = await fetch("https://creatorsapi.amazon/catalog/v1/getItems", { method: "POST",
    headers: { Authorization: `Bearer ${await amzToken(env)}`, "Content-Type": "application/json", "x-marketplace": "www.amazon.co.jp" },
    body: JSON.stringify({ itemIds: asins, itemIdType: "ASIN", marketplace: "www.amazon.co.jp", partnerTag: AMZ_TAG,
      resources: ["itemInfo.title", "offersV2.listings.availability", "offersV2.listings.price", "offersV2.listings.merchantInfo"] }) });
  if (!r.ok) { lastAmzErr = `getItems ${r.status} ${(await r.text()).slice(0, 120)}`; return null; }
  const j = await r.json();
  const items = j.itemsResult?.items || j.items || j.itemResults?.items || j.getItemsResult?.items || [];
  if (!items.length) { lastAmzErr = `getItems 0件 ${JSON.stringify(j).slice(0, 160)}`; return null; }   // 返事の形が違う時は1件ずつに戻す
  const m = {};
  for (const it of items) if (it && it.asin) m[it.asin] = it;
  return m;
}
let lastAmzErr = "";
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
  // 11/9 ユーザーの指示：リンク先はサイトの商品ページ（いちばん上に Amazon・楽天のボタンと「速報から来た方へ」の案内）。ページが無い商品はお店へ直接
  const link = w.pg ? `https://game-nyuka.com${w.pg}?x=${shop}` : url;
  const lines = ["🚨速報🚨 " + head, "", `【${w.n}】`, ...(w.pm ? [`💰定価以上で売れてる商品（${w.pm}）`] : []), ...(w._days >= 3 ? [`📦${Math.floor(w._days)}日ぶりの在庫復活`] : []), "",
    w.pg ? `${where}の購入ボタンはこちら👇` : (kind === "pre" ? "定価で予約できます👇" : shop === "az" ? "Amazon.co.jp本体の販売です👇" : "定価で買えます👇"), link, ""];
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
  let changed = false, minor = false, n = 0;
  let list = [];
  try { list = await watchList(); } catch (e) { log.push(String(e)); }
  list = list.filter((w) => (which === "rk" ? (w.rk || w.jan) : (w.asin || w.jan)));
  // Amazon：ASINが分かっている商品は10件ずつまとめて調べる（1回で最大 AZ_BATCH 件）。ASINがまだ分からない商品だけ1件ずつ検索
  const azAsin = (w) => w.asin || (w.jan && st.map[w.jan] && st.map[w.jan].asin) || "";
  let pre = {};
  let targets;
  if (which === "rk") targets = batch(list, RK_PER_RUN, 0);
  else {
    const known = list.filter((w) => azAsin(w)), unknown = list.filter((w) => !azAsin(w));
    targets = [...batch(known, AZ_BATCH, 7), ...batch(unknown, AZ_SEARCH, 3)];
    const asins = [...new Set(targets.map(azAsin).filter(Boolean))];
    for (let i = 0; i < asins.length; i += 10) {
      const m = await amzItems(env, asins.slice(i, i + 10));
      if (m === null) { log.push(lastAmzErr); pre = null; break; }
      Object.assign(pre, m);
      await sleep(1100);
    }
    if (pre === null) targets = [...batch(known, 6, 7), ...batch(unknown, 2, 3)];   // まとめて調べられない時は前のやり方（1件ずつ）
  }
  for (const w of targets) {
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
        const a = azAsin(w);
        const usePre = pre && a;
        const it = usePre ? pre[a] : await amzItem(env, w.asin || w.jan, !w.asin, w.n);
        if (!it) { if (!usePre) await sleep(1100); continue; }   // 見つからなかっただけ（売り切れとは数えない）
        // JANから見つけたASINなのに名前が合わない（前に間違って覚えた）→ 忘れて使わない（次に探し直す）
        if (!w.asin && w.n && sim(w.n, amzTitle(it)) < SIM_MIN) {
          if (w.jan && st.map[w.jan] && st.map[w.jan].asin) { delete st.map[w.jan].asin; delete st.map[w.jan].azUrl; changed = true; log.push(`名前が合わないASINを外した ${w.jan} ${amzTitle(it).slice(0, 40)}`); }
          delete st.items[id]; delete st.soldout[id];
          continue;
        }
        cur = amzState(it);
        const l = ((it && it.offersV2?.listings) || []).find((x) => x.merchantInfo?.id === AMZ_SELLER);
        price = yen(l?.price?.money?.amount ?? l?.price?.money?.displayAmount);
        url = (it && it.detailPageURL) || (it ? `https://www.amazon.co.jp/dp/${it.asin}?tag=${AMZ_TAG}` : "");
        if (w.jan && it && !(st.map[w.jan] && st.map[w.jan].asin)) { st.map[w.jan] = Object.assign(st.map[w.jan] || {}, { asin: it.asin, azUrl: url, t: amzTitle(it).slice(0, 80) }); changed = true; }
      }
    } catch (e) { log.push(String(e).slice(0, 160)); await sleep(1500); continue; }
    if (which === "rk" || !(pre && azAsin(w))) await sleep(1100);   // 楽天は1秒に1回まで（まとめて調べたAmazonは待たない）
    n++;
    // 定価より高い値段で売っているものは「定価で買える」とは言わない（定価が分かるときだけ。110%まで）
    if (cur !== "none" && w.tk && price && price > w.tk * 1.1) cur = "none";
    const prev = st.items[id];
    st.stat = st.stat || {};
    if (prev !== cur) changed = true;
    if (!st.stat[id] || st.stat[id].s !== cur || (cur !== "none" && st.stat[id].p !== price)) {
      // 販売・在庫の履歴（11/9：サイトの商品ページに「楽天・Amazonの販売・在庫の履歴」の表を出す。状態が変わった時だけ・直近12件）
      st.hist = st.hist || {};
      if (!st.stat[id] || st.stat[id].s !== cur) { (st.hist[id] = st.hist[id] || []).unshift({ t: new Date().toISOString(), s: cur, p: price }); st.hist[id] = st.hist[id].slice(0, 12); }
      const sChanged = !st.stat[id] || st.stat[id].s !== cur;
      st.stat[id] = { s: cur, p: price, u: url, at: new Date().toISOString() };
      if (sChanged) changed = true; else minor = true;   // 値段だけ変わった時は急いで保存しない（KVの書き込みは1日1,000回まで）
    }
    // 売り切れの記録（11/9 ユーザーの指示：売り切れ→販売に切り替わった時だけ速報。売り切れは1回見たらOK）
    st.soldout = st.soldout || {};
    const so = st.soldout[id];
    if (cur === "none") { if (!so) { st.soldout[id] = { since: Date.now(), n: 1 }; changed = true; } else if (so.n < 2) { so.n++; changed = true; } }
    const confirmed = !!so;   // 11/9 ユーザーの指示：売り切れは1回見たらOK（商品を見る間隔がもともと40分〜1時間あるため）
    if (cur !== "none" && so) { delete st.soldout[id]; changed = true; }
    // 速報：前に「本当に売り切れ」を見ていて、いま販売中・予約受付中・招待受付中に変わった時だけ。前から売っているものは出さない
    const fresh = st.init[id] && prev === "none" && cur !== "none" && confirmed && !(st.posted[id + cur] && Date.now() - st.posted[id + cur] < COOLDOWN);
    if (!st.init[id]) { st.init[id] = 1; changed = true; }
    st.items[id] = cur;
    if (!fresh || w.nopost) continue;   // nopost：投稿しないカテゴリ（一番くじなど）
    // 速報するのは（11/9 ユーザーの指示）：定価以上で売れる商品（hot）か、売り切れが長く続いていた品薄の商品（3日以上）だけ
    const soldDays = so ? (Date.now() - so.since) / 86400e3 : 0;
    if (!(w.hot || soldDays >= SCARCE_DAYS)) continue;
    if (st.count >= PER_DAY || (!w.g && st.hobby >= HOBBY_PER_DAY)) { log.push("1日の上限"); continue; }
    w._days = soldDays;
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
  // 2分ごとに2つ（楽天・Amazon）動くので、毎回保存すると上限を超える：在庫の状態が変わった・新しく見つけた・投稿した時はすぐ、
  // 値段だけの変化やエラーの記録は30分に1回まとめて
  const due = Date.now() - (st.savedAt || 0) > 30 * 60e3;
  if (!dry && (changed || ((minor || log.length) && due))) { st.savedAt = Date.now(); await env.STATE.put(key, JSON.stringify(st)); }
  return st.last;
}

export default {
  async scheduled(event, env, ctx) {
    const m = new Date(event.scheduledTime).getUTCMinutes();
    if (env.RAKUTEN_APP_ID) ctx.waitUntil(run(env, "rk"));
    if (env.AMAZON_CREDENTIAL_ID) ctx.waitUntil(run(env, "az"));   // 11/9：4分ごと → 2分ごと（10件ずつまとめて調べるので呼び出し回数はむしろ少ない）
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
      m._st2 = { rk: rk.stat || {}, az: az.stat || {} };   // 楽天とAmazonを分けた今の状態（同じ「j+JAN」でも別々に）
      m._hist = { rk: rk.hist || {}, az: az.hist || {} };   // 販売・在庫の履歴
      return Response.json(m);
    }
    if (u.pathname === "/dry") return Response.json({ rk: await run(env, "rk", { dry: true }), az: await run(env, "az", { dry: true }) });
    return Response.json({ rk: (await env.STATE.get("rk", "json"))?.last, az: (await env.STATE.get("az", "json"))?.last });
  },
};
