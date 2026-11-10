// 弾ごとの収録カード（RR以上など）の相場を、スニダンから少しずつ集める（11/11）
// ・GitHub Actions の時間を使わないように、Cloudflare の定期実行（10分に1回）で動かす
// ・どの弾を集めるかはサイトの /data/card-sets.json（sitegen が書く）。[{key, q, rar:[...]}]
// ・弾ごとのカード一覧は、スニダンの検索（「弾の名前 レアリティ」）で見つける。7日に1回見直す
// ・カード1枚の相場は、取引履歴（状態A＝未鑑定の美品・1枚）の日ごとの値。1日1回だけ読み直す
// ・1回の実行でスニダンを読むのは最大 BUDGET 回。連続で読まないように少し間をあける
// ・保存：KV の "cards"（全部の弾をまとめた1つ）。書くのは中身が変わったときだけ（無料枠の書き込み回数のため）
const SITE = "https://tcg-chusen.com";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const BUDGET = 30;
const COND = "trading_card_single_nearly_unused";
const DAY = 86400e3;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const jst = (t = Date.now()) => new Date(t + 9 * 3600e3).toISOString().slice(0, 10);

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
  // 例：<a href="https://snkrdunk.com/apparels/868590" ... aria-label="カイオーガ AR [M6 080/076](拡張パック「ストームエメラルダ」) - ¥1,000">
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
  for (const r of set.rar) {
    if (used >= budget) return { cards: null, used };
    const html = await get(`https://snkrdunk.com/search?keywords=${encodeURIComponent(`${set.q} ${r}`)}`);
    used++;
    for (const c of parseSearch(html, set.q)) if (c.r === r || set.rar.includes(c.r)) cards[c.id] = c;
    await wait(800);
  }
  return { cards, used };
}

async function price(card) {
  let used = 0;
  if (!card.pid) {
    const h = await get(`https://snkrdunk.com/apparels/${card.id}`);
    used++;
    const m = h.match(/\\?"productId\\?":(\d+)/);
    if (!m) throw new Error("productId なし");
    card.pid = +m[1];
    await wait(600);
  }
  if (card.vid === undefined) {
    const j = await get(`https://snkrdunk.com/v3/products/${card.pid}/trading-history?range=all`, true);
    used++;
    const o = ((j.filters || {}).variants || {}).options || [];
    card.vid = (o.find((x) => /^1(枚|個)$/.test(x.name || "")) || {}).id || 0;
    await wait(600);
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
  const cut = jst(Date.now() - 90 * DAY);
  card.h = Object.fromEntries(ds.filter((d) => d >= cut).map((d) => [d, day[d]]));  // 90日分だけ持つ
  card.last = ds.length ? ds[ds.length - 1] : null;
  card.at = Date.now();
  return used;
}

export async function runCards(env) {
  let sets;
  try { sets = await get(`${SITE}/data/card-sets.json?${Date.now()}`, true); } catch (e) { return { error: `sets ${e}` }; }
  const st = (await env.STATE.get("cards", "json")) || { sets: {} };
  let left = BUDGET, changed = false;
  const log = [];
  for (const set of sets) {
    const s = st.sets[set.key] || (st.sets[set.key] = { cards: {}, found: 0 });
    if (left <= 0) break;
    if (!s.found || Date.now() - s.found > 7 * DAY) {
      try {
        const { cards, used } = await discover(set, left);
        left -= used;
        if (cards) {
          for (const [id, c] of Object.entries(cards)) s.cards[id] = Object.assign(s.cards[id] || {}, c);
          s.found = Date.now(); changed = true;
          log.push(`${set.key}: ${Object.keys(cards).length}枚`);
        }
      } catch (e) { log.push(`${set.key}: 検索 ${e.message}`); left -= 1; }
    }
  }
  // 古い順（読んでいない・1日以上前）に相場を読む
  const todo = [];
  for (const set of sets) for (const c of Object.values((st.sets[set.key] || {}).cards || {})) if (!c.at || Date.now() - c.at > DAY) todo.push(c);
  todo.sort((a, b) => (a.at || 0) - (b.at || 0));
  for (const c of todo) {
    if (left < 3) break;
    try { left -= await price(c); changed = true; } catch (e) { log.push(`${c.n}: ${e.message}`); left -= 1; c.at = Date.now() - DAY + 6 * 3600e3; }
    await wait(500);
  }
  for (const k of Object.keys(st.sets)) if (!sets.some((s) => s.key === k)) { delete st.sets[k]; changed = true; }
  st.last = { at: new Date().toISOString(), todo: todo.length, log: log.slice(-10) };
  if (changed) await env.STATE.put("cards", JSON.stringify(st));
  return st.last;
}

export async function cardsData(env) {
  return (await env.STATE.get("cards", "json")) || { sets: {} };
}
