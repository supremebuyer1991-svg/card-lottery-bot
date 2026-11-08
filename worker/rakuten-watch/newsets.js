// 新弾の発表の見張り（11/8）。公式サイトの商品一覧を10分おきに見て、新しい弾が載ったらすぐXに速報する。
// ・ワンピース：onepiece-cardgame.com の商品ページ（ブースターパック・エクストラブースター・プレミアム系）
// ・ポケカ：pokemon-card.com の商品情報（拡張パック・強化拡張パック・ハイクラスパック・BOX商品）
// ・最初の1回は記録だけ（投稿しない）。一度に7件以上「新しい」が出たら、ページの作りが変わったと考えて記録だけ
// ・前に見つけた弾は KV（STATE の "newsets"）に覚えておく。二度投稿しない
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const SITE = "https://tcg-chusen.com";
const W = "日月火水木金土";

function jdate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${y}年${m}月${d}日（${W[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}）`;
}
const unesc = (s) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&nbsp;/g, " ");

async function onepiece() {
  const out = {};
  for (const page of [1, 2]) {
    const r = await fetch(`https://www.onepiece-cardgame.com/products/?page=${page}&view=detail`, { headers: { "User-Agent": UA } });
    if (!r.ok) throw new Error(`ワンピ公式 ${r.status}`);
    const txt = unesc((await r.text()).replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ");
    const re = /(ブースター) ((?:ブースターパック|エクストラブースター|プレミアム\S*ブースター) [^発]{2,60}?) 発売日\s*(\d{4})\.(\d{2})\.(\d{2})\S*\s*メーカー希望小売価格\s*([\d,]+円)/g;
    for (const m of txt.matchAll(re)) {
      const full = m[2].trim();
      const code = (full.match(/【([A-Z]{2,4}-\d{2})】/) || [])[1] || "";
      const name = full.replace(/【[^】]+】/g, "").replace(/^(ブースターパック|エクストラブースター|プレミアム\S*ブースター)\s*/, "").trim();
      const type = full.split(" ")[0] + (code ? `【${code}】` : "");
      out[`onepiece|${code || name}`] = { game: "onepiece", name, type, code, release: `${m[3]}-${m[4]}-${m[5]}`, price: `1パック${m[6]}（税込）` };
    }
  }
  return out;
}

async function pokemon() {
  const t = new Date(Date.now() + 9 * 3600e3), lo = new Date(t.getTime() - 30 * 86400e3);
  const base = "https://www.pokemon-card.com/products/resultAPI.php?" +
    `dateLowerY=${lo.getUTCFullYear()}&dateLowerM=${lo.getUTCMonth() + 1}&dateLowerD=${lo.getUTCDate()}` +
    `&dateUpperY=${t.getUTCFullYear() + 1}&dateUpperM=12&dateUpperD=31&page=`;
  const out = {};
  for (let page = 1; page <= 3; page++) {
    const r = await fetch(base + page, { headers: { "User-Agent": UA, Referer: "https://www.pokemon-card.com/products/" } });
    if (!r.ok) throw new Error(`ポケカ公式 ${r.status}`);
    const j = await r.json();
    for (const p of j.products || []) {
      const title = (p.productTitle || "").trim(), kind = p.productType || "";
      if (kind === "周辺グッズ" || kind === "構築デッキ" || (kind === "その他の商品" && !/BOX|ボックス/.test(title))) continue;
      const m = (p.releaseDate || "").match(/(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日/);
      if (!m) continue;
      const q = title.match(/「([^」]+)」/);
      const name = q ? q[1].trim() : title.replace(/^(ポケモンカードゲーム\s*)?(MEGA\s*)?/, "").trim();
      const type = title.replace(/^(ポケモンカードゲーム\s*)?(MEGA\s*)?/, "").replace(/[「」].*$/, "").trim() || kind;
      const price = unesc((p.priceTxt || "").replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
      const release = `${m[1]}-${String(m[2]).padStart(2, "0")}-${String(m[3]).padStart(2, "0")}`;
      out[`pokemon|${name}`] = { game: "pokemon", name, type, code: "", release, price };
    }
    if (page >= Number(j.maxPage || 1)) break;
  }
  return out;
}

function compose(it) {
  const op = it.game === "onepiece";
  const head = op ? "ワンピカード" : "ポケカ";
  const tags = op ? "#ワンピースカード #ワンピースカード抽選" : "#ポケモンカード #ポケカ抽選";
  const lines = [`🚨${head} 新情報解禁🚨`, "", `新弾『${it.name}』${it.code ? `【${it.code}】` : ""}の発売が決定‼️`, `（${it.type.replace(/【[^】]+】/, "")}）`, ""];
  if (it.release) lines.push(`📅発売日：${jdate(it.release)}`);
  if (it.price) lines.push(`💴定価：${it.price}`);
  lines.push("", "予約・抽選が始まったらすぐお知らせします📣", "🔔フォロー＆通知ONで速報が届きます", "",
    `${SITE}/${op ? "onepiece" : "pokeka"}/`, "", tags);
  return lines.join("\n");
}

export async function runNewsets(env, tweet, { dry = false } = {}) {
  const st = (await env.STATE.get("newsets", "json")) || { seen: {}, init: false, posted: [] };
  const log = [];
  let found = {};
  for (const [label, fn] of [["onepiece", onepiece], ["pokemon", pokemon]]) {
    try { Object.assign(found, await fn()); } catch (e) { log.push(`${label}: ${e.message}`); }
  }
  const fresh = Object.keys(found).filter((k) => !st.seen[k]);
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  // 発売済みの物は「新弾」ではない（公式の一覧の並びが変わっただけ）
  const toPost = fresh.filter((k) => (found[k].release || "") >= today);
  if (!st.init || toPost.length > 6) {
    log.push(st.init ? `新しい物が${toPost.length}件と多いので記録だけ` : "最初の1回：記録だけ");
  } else {
    for (const k of toPost.slice(0, 3)) {
      const text = compose(found[k]);
      if (dry) { log.push("（ためし）\n" + text); continue; }
      try {
        const id = await tweet(env, text);
        st.posted.push({ k, id, at: new Date().toISOString() });
        log.push(`投稿しました ${k} ${id}`);
      } catch (e) {
        log.push(`投稿失敗 ${k} ${e.message}`);
        st.fail = st.fail || {};
        st.fail[k] = (st.fail[k] || 0) + 1;
        if (st.fail[k] < 3) fresh.splice(fresh.indexOf(k), 1);  // 失敗したら次の回にもう一度（3回まで）
      }
    }
  }
  if (!dry) {
    for (const k of fresh) st.seen[k] = { ...found[k], first: today };
    st.init = true;
    st.posted = st.posted.slice(-30);
    st.last = { at: new Date().toISOString(), n: Object.keys(found).length, log };
    await env.STATE.put("newsets", JSON.stringify(st));
  }
  return { found: Object.keys(found).length, fresh, log };
}

export async function newsetsStatus(env) {
  const st = (await env.STATE.get("newsets", "json")) || {};
  return { init: !!st.init, last: st.last, posted: st.posted, seen: Object.keys(st.seen || {}) };
}
