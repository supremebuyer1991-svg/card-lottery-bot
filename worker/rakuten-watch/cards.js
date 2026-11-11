// 弾ごとの収録カード（RR以上など）の相場を、スニダンから少しずつ集める（11/11）
// ・GitHub Actions の時間を使わないように、Cloudflare の定期実行（30分に1回。KV の書き込みの無料枠のため）で動かす
// ・どの弾を集めるかはサイトの /data/card-sets.json（sitegen が書く）。[{key, q, rar:[...]}]
// ・弾ごとのカード一覧は、スニダンの検索（「弾の名前 レアリティ」）で見つける。見つかった弾は30日に1回、まだ0枚の弾は7日に1回見直す
// ・カード1枚の相場は、取引履歴（状態A＝未鑑定の美品・1枚）の日ごとの値。2,000円以上のカードは毎日、それより安いカードは3日に1回読み直す
// ・1回の実行でスニダンを読むのは最大 BUDGET 回。連続で読まないように少し間をあける
// ・保存（11/11 全部の弾に広げたので弾ごとに分けた。無料枠の処理時間・書き込み回数のため）：
//     KV "cards:idx" … {sets:{key:{found, n, priced, due}}, last}（小さい目次）
//     KV "cards:s:<key>" … {cards:{id:{id,n,r,no,pid,vid,h:{date:price}(35日),last,at}}}
//   書くのは中身が変わった弾だけ
const SITE = "https://tcg-chusen.com";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const BUDGET = 44;
const COND = "trading_card_single_nearly_unused";
const DAY = 86400e3;
const KEEP_DAYS = 35;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const jst = (t = Date.now()) => new Date(t + 9 * 3600e3).toISOString().slice(0, 10);
const skey = (k) => "cards:s:" + k;

async function get(url, json) {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Accept-Language": "ja" } });
  if (!r.ok) throw new Error(`${r.status} ${url.slice(0, 80)}`);
  return json ? r.json() : r.text();
}

// 検索結果のページから、カードの商品（apparels/番号）と名前を取り出す
function parseSearch(html, setName) {
  const out = [];
  const seen = new Set();
  const un = (t) => t.replace(/&amp;/g, "&").replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"');
  // 例：aria-label="カイオーガ AR [M6 080/076](拡張パック「ストームエメラルダ」) - ¥1,000"
  //     aria-label="ロキ (天野喜孝) SEC [OP17-119](ブースターパック「神の支配」) - ¥"（「:箔押し版」などの特別な版は拾わない）
  const re = /apparels\/(\d+)"[^>]*?aria-label="([^"]+?)\s+([A-Z]{1,4}(?:-[A-Z]+)?)\s*\[([^\]]+)\]\(([^)]*)\)/g;
  for (const m of html.matchAll(re)) {
    const id = +m[1];
    if (seen.has(id) || !un(m[5]).includes(setName)) continue;
    seen.add(id);
    out.push({ id, n: un(m[2]).trim(), r: m[3], no: m[4].trim() });
  }
  return out;
}

async function discover(set, budget) {
  const cards = {};
  let used = 0;
  const name = set.q.replace(/^「|」$/g, "");
  for (const r of set.rar) {
    if (used >= budget) return { cards: null, used };
    const html = await get(`https://snkrdunk.com/search?keywords=${encodeURIComponent(`${set.q} ${r}`)}`);
    used++;
    for (const c of parseSearch(html, name)) if (set.rar.includes(c.r)) cards[c.id] = c;
    await wait(700);
  }
  return { cards, used };
}

const lastPrice = (c) => { const ks = Object.keys(c.h || {}); return ks.length ? c.h[ks.sort()[ks.length - 1]] : 0; };
const every = (c) => (lastPrice(c) >= 2000 ? DAY : 3 * DAY);
const dueAt = (c) => (c.at ? c.at + every(c) : 0);

async function price(card) {
  let used = 0;
  if (!card.pid) {
    const h = await get(`https://snkrdunk.com/apparels/${card.id}`);
    used++;
    const m = h.match(/\\?"productId\\?":(\d+)/);
    if (!m) throw new Error("productId なし");
    card.pid = +m[1];
    await wait(500);
  }
  if (card.vid === undefined) {
    const j = await get(`https://snkrdunk.com/v3/products/${card.pid}/trading-history?range=all`, true);
    used++;
    const o = ((j.filters || {}).variants || {}).options || [];
    card.vid = (o.find((x) => /^1(枚|個)$/.test(x.name || "")) || {}).id || 0;
    await wait(500);
  }
  const q = card.vid ? `&variant_id=${card.vid}` : "";
  const j = await get(`https://snkrdunk.com/v3/products/${card.pid}/trading-history?range=all${q}&condition_code=${COND}`, true);
  used++;
  const day = {};
  for (const p of (((j.chart || {}).lines || [{}])[0] || {}).points || []) {
    if (p.timestamp == null || p.price == null) continue;
    const ts = p.timestamp > 1e11 ? p.timestamp : p.timestamp * 1000;
    day[jst(ts)] = Math.round(p.price);
  }
  const ds = Object.keys(day).sort();
  const cut = jst(Date.now() - KEEP_DAYS * DAY);
  const keep = ds.filter((d) => d >= cut);
  if (!keep.length && ds.length) keep.push(ds[ds.length - 1]);  // 35日に取引がなくても、いちばん新しい取引の日は残す
  card.h = Object.fromEntries(keep.map((d) => [d, day[d]]));
  card.last = ds.length ? ds[ds.length - 1] : null;
  card.at = Date.now();
  return used;
}

function summarize(s) {
  const cs = Object.values(s.cards || {});
  return { n: cs.length, priced: cs.filter((c) => c.at).length, due: cs.length ? Math.min(...cs.map(dueAt)) : 0 };
}

// 前の形（全部の弾を "cards" 1つにまとめていた）から弾ごとに分ける（1回だけ）
async function migrate(env) {
  const old = await env.STATE.get("cards", "json");
  if (!old || !old.sets) return null;
  const idx = { sets: {} };
  for (const [k, s] of Object.entries(old.sets)) {
    await env.STATE.put(skey(k), JSON.stringify({ cards: s.cards || {} }));
    idx.sets[k] = { found: s.found || 0, ...summarize(s) };
  }
  await env.STATE.put("cards:idx", JSON.stringify(idx));
  await env.STATE.delete("cards");
  return idx;
}

export async function runCards(env) {
  let sets;
  try { sets = await get(`${SITE}/data/card-sets.json?${Date.now()}`, true); } catch (e) { return { error: `sets ${e}` }; }
  const idx = (await env.STATE.get("cards:idx", "json")) || (await migrate(env)) || { sets: {} };
  let left = BUDGET;
  const log = [];
  const now = Date.now();
  const touched = {};
  const load = async (k) => (touched[k] ||= (await env.STATE.get(skey(k), "json")) || { cards: {} });
  // 1. カード一覧を見つける（まだの弾・見直しの時期の弾。1回で2弾まで）
  let disc = 0;
  for (const set of sets) {
    if (left < 8 || disc >= 1) break;  // 書き込む弾の数を減らすため、見つけるのは1回1弾
    const ix = idx.sets[set.key] || (idx.sets[set.key] = { found: 0, n: 0, priced: 0, due: 0 });
    const again = ix.n > 0 ? 30 * DAY : 7 * DAY;
    if (ix.found && now - ix.found < again) continue;
    disc++;
    try {
      const { cards, used } = await discover(set, left);
      left -= used;
      if (cards) {
        const s = await load(set.key);
        for (const [id, c] of Object.entries(cards)) s.cards[id] = Object.assign(s.cards[id] || {}, c);
        ix.found = now;
        log.push(`${set.key}: ${Object.keys(cards).length}枚`);
      }
    } catch (e) { log.push(`${set.key}: 検索 ${e.message}`); left -= 1; ix.found = now - again + DAY; }
  }
  // 2. 相場を読む：読み直しの時期が来たカードのある弾を、時期の早い順に
  const order = sets.map((s) => s.key).filter((k) => idx.sets[k] && idx.sets[k].n !== undefined)
    .sort((a, b) => (idx.sets[a].due || 0) - (idx.sets[b].due || 0));
  for (const k of order) {
    if (left < 3) break;
    if (!touched[k] && (idx.sets[k].due || 0) > now) continue;
    const s = await load(k);
    const todo = Object.values(s.cards).filter((c) => dueAt(c) <= now).sort((a, b) => dueAt(a) - dueAt(b));
    for (const c of todo) {
      if (left < 3) break;
      try { left -= await price(c); } catch (e) { log.push(`${c.n}: ${e.message}`); left -= 1; c.at = now - every(c) + 6 * 3600e3; }
      await wait(400);
    }
  }
  for (const [k, s] of Object.entries(touched)) {
    await env.STATE.put(skey(k), JSON.stringify(s));
    Object.assign(idx.sets[k], summarize(s));
  }
  let gone = 0;
  for (const k of Object.keys(idx.sets)) if (!sets.some((s) => s.key === k)) { delete idx.sets[k]; await env.STATE.delete(skey(k)); gone++; }
  idx.last = { at: new Date().toISOString(), used: BUDGET - left, log: log.slice(-10) };
  if (Object.keys(touched).length || log.length || gone) await env.STATE.put("cards:idx", JSON.stringify(idx));  // 何もなかった回は書かない
  return idx.last;
}

// /cards?set=キー … その弾のカード（相場は35日分）。/cards … 目次だけ
export async function cardsData(env, key) {
  if (key) return (await env.STATE.get(skey(key), "json")) || { cards: {} };
  return (await env.STATE.get("cards:idx", "json")) || (await migrate(env)) || { sets: {} };
}
