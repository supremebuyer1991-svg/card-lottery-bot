// 大手の抽選の「予告」「受付開始」ポスト（11/9 ユーザーの指示）
// GitHub側（plan_big_queue）がサイトに /x-queue.json（[{k, at, text}]）を置く。ここは1分おきに読んで、時刻が来たものをXに出す。
// 出したものは KV の "xqueue" に覚えて二度出さない。3時間より前の古いもの・1回に4本より多くは出さない（事故防止）
export async function runXQueue(env, tweet) {
  let list;
  try {
    const r = await fetch(`https://tcg-chusen.com/x-queue.json?t=${Math.floor(Date.now() / 60000)}`, { cf: { cacheTtl: 0 } });
    if (!r.ok) return { err: r.status };
    list = await r.json();
  } catch (e) { return { err: String(e) }; }
  const now = Date.now();
  const due = (list || []).filter((x) => { const t = Date.parse(x.at); return t <= now && t > now - 3 * 3600e3; });
  if (!due.length) return { due: 0 };
  const st = (await env.STATE.get("xqueue", "json")) || { posted: {} };
  const out = [];
  let changed = false;
  for (const x of due.filter((x) => !st.posted[x.k]).slice(0, 4)) {
    try {
      const id = await tweet(env, x.text);
      st.posted[x.k] = { at: new Date().toISOString(), id };
      out.push(`posted ${x.k} ${id}`);
    } catch (e) {
      st.fail = st.fail || {};
      st.fail[x.k] = (st.fail[x.k] || 0) + 1;
      if (st.fail[x.k] >= 3) st.posted[x.k] = { at: new Date().toISOString(), err: String(e).slice(0, 200) };  // 3回失敗したらあきらめる
      out.push(`fail ${x.k} ${e}`);
    }
    changed = true;
  }
  if (changed) {
    for (const [k, v] of Object.entries(st.posted)) if (now - Date.parse(v.at) > 5 * 86400e3) delete st.posted[k];
    st.last = { at: new Date().toISOString(), out };
    await env.STATE.put("xqueue", JSON.stringify(st));
  }
  return { due: due.length, out };
}

export async function xqueueStatus(env) {
  return (await env.STATE.get("xqueue", "json")) || {};
}
