// 締切の通知（Web Push・11/7）
// サイトの「応募したリスト」に入れた抽選の、締切の前日夜（20時）と3時間前にスマホ・パソコンへ通知する。
// ・通知のカギ（VAPID）はこのWorkerが最初に自分で作ってKVに置く（外に出さない）
// ・登録は KV "ps:<id>"（id は送り先URLのハッシュ）。次に送る時刻は metadata.n（分）に入れて、一覧だけで判断できるようにする
// ・名前やメールなどの個人の情報は受け取らない（送り先URLと、リストに入れた抽選の締切・名前・ページだけ）
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const ub64 = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const enc = (s) => new TextEncoder().encode(s);
const cat = (...a) => { const o = new Uint8Array(a.reduce((n, x) => n + x.length, 0)); let i = 0; for (const x of a) { o.set(x, i); i += x.length; } return o; };
const JST = 9 * 3600e3;
const HOSTS = /^(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|push\.services\.mozilla\.com|web\.push\.apple\.com|[\w.-]+\.notify\.windows\.com|[\w.-]+\.push\.apple\.com)$/;

async function vapid(env) {
  let k = await env.STATE.get("vapid", "json");
  if (!k) {
    const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
    const jwk = await crypto.subtle.exportKey("jwk", kp.privateKey);
    const pub = await crypto.subtle.exportKey("raw", kp.publicKey);
    k = { jwk: { kty: "EC", crv: "P-256", d: jwk.d, x: jwk.x, y: jwk.y }, pub: b64u(pub) };
    await env.STATE.put("vapid", JSON.stringify(k));
  }
  return k;
}

async function jwt(k, aud) {
  const key = await crypto.subtle.importKey("jwk", k.jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const h = b64u(enc(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const c = b64u(enc(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: "https://tcg-chusen.com/" })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc(`${h}.${c}`));
  return `${h}.${c}.${b64u(sig)}`;
}

// RFC 8291（aes128gcm）で中身を暗号化
async function encrypt(sub, payload) {
  const uaPub = ub64(sub.keys.p256dh), auth = ub64(sub.keys.auth);
  const eph = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPub = new Uint8Array(await crypto.subtle.exportKey("raw", eph.publicKey));
  const uaKey = await crypto.subtle.importKey("raw", uaPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, eph.privateKey, 256));
  const hkdf = async (salt, ikm, info, bits) => new Uint8Array(await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info }, await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]), bits));
  const ikm = await hkdf(auth, shared, cat(enc("WebPush: info\0"), uaPub, asPub), 256);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, enc("Content-Encoding: aes128gcm\0"), 128);
  const nonce = await hkdf(salt, ikm, enc("Content-Encoding: nonce\0"), 96);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, cat(enc(payload), new Uint8Array([2]))));
  const rs = new Uint8Array([0, 0, 16, 0]);
  return cat(salt, rs, new Uint8Array([asPub.length]), asPub, ct);
}

export async function sendPush(env, sub, msg) {
  const k = await vapid(env);
  const aud = new URL(sub.endpoint).origin;
  const body = await encrypt(sub, JSON.stringify(msg));
  const r = await fetch(sub.endpoint, { method: "POST", body, headers: {
    Authorization: `vapid t=${await jwt(k, aud)}, k=${k.pub}`, TTL: "21600", Urgency: "high",
    "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", Topic: (msg.tag || "t").replace(/[^\w-]/g, "").slice(0, 32) || "t" } });
  return r.status;
}

// 1件の抽選の、通知する時刻（ミリ秒）：前日20時（締切が翌日以降のとき）と3時間前
function dues(end) {
  const e = Date.parse(end);
  if (!e) return [];
  const out = [[e - 3 * 3600e3, "3h"]];
  const d = new Date(e + JST); // JSTの日付
  const eve = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - 1, 20) - JST;
  if (eve < e - 6 * 3600e3) out.push([eve, "d"]);
  return out;
}
function nextDue(rec, now) {
  let n = Infinity;
  for (const it of rec.it) for (const [t, kind] of dues(it.e)) if (t > now - 2 * 3600e3 && !rec.sent[it.k + kind]) n = Math.min(n, t);
  return n;
}
async function saveRec(env, id, rec, now) {
  const n = nextDue(rec, now);
  await env.STATE.put("ps:" + id, JSON.stringify(rec), { metadata: { n: n === Infinity ? 0 : Math.floor(n / 60e3) }, expirationTtl: 120 * 86400 });
}

async function idOf(endpoint) {
  const h = await crypto.subtle.digest("SHA-256", enc(endpoint));
  return [...new Uint8Array(h)].slice(0, 10).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function pushApi(req, env, path, hdr) {
  if (path === "/push/key") return Response.json({ k: (await vapid(env)).pub }, { headers: { ...hdr, "Cache-Control": "max-age=3600" } });
  let b;
  try { b = await req.json(); } catch { return new Response("bad", { status: 400, headers: hdr }); }
  const sub = b.sub || {};
  let host = "";
  try { host = new URL(sub.endpoint).hostname; } catch { /* */ }
  if (!HOSTS.test(host) || !String(sub.endpoint).startsWith("https://")) return new Response("bad endpoint", { status: 400, headers: hdr });
  const id = await idOf(sub.endpoint);
  if (path === "/push/unsub") { await env.STATE.delete("ps:" + id); return Response.json({ ok: true }, { headers: hdr }); }
  if (!(sub.keys && sub.keys.p256dh && sub.keys.auth)) return new Response("bad keys", { status: 400, headers: hdr });
  const now = Date.now();
  const it = (Array.isArray(b.items) ? b.items : []).slice(0, 60).map((x) => ({
    k: String(x.k || "").replace(/[^\w-]/g, "").slice(0, 40), e: String(x.e || "").slice(0, 40),
    t: String(x.t || "").slice(0, 80), u: String(x.u || "").replace(/[^\w\-/.%]/g, "").slice(0, 120),
  })).filter((x) => x.k && Date.parse(x.e) > now);
  const old = (await env.STATE.get("ps:" + id, "json")) || { sent: {} };
  const rec = { s: { endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth } }, it, sent: {}, at: new Date(now).toISOString() };
  for (const x of it) for (const kind of ["3h", "d"]) if (old.sent?.[x.k + kind]) rec.sent[x.k + kind] = 1;
  await saveRec(env, id, rec, now);
  let st = 0;
  if (b.hello) st = await sendPush(env, rec.s, { title: "🔔 締切の通知をオンにしました", body: it.length ? `応募したリストの${it.length}件の抽選の、締切の前日夜と3時間前にお知らせします。` : "「☐ 応募した」を押した抽選の、締切の前日夜と3時間前にお知らせします。", url: "/mylist/", tag: "hello" });
  return Response.json({ ok: true, n: it.length, hello: st }, { headers: hdr });
}

// 10分おき：時刻が来た通知を送る
export async function runPush(env) {
  const now = Date.now(), nowMin = Math.floor(now / 60e3);
  let cursor, sent = 0, dead = 0;
  do {
    const r = await env.STATE.list({ prefix: "ps:", cursor });
    for (const key of r.keys) {
      const n = key.metadata?.n || 0;
      if (!n || n > nowMin) continue;
      const rec = await env.STATE.get(key.name, "json");
      if (!rec) continue;
      const due = [];
      for (const it of rec.it) for (const [t, kind] of dues(it.e)) if (t <= now && t > now - 2 * 3600e3 && !rec.sent[it.k + kind]) due.push([it, kind]);
      let gone = false;
      for (const [it, kind] of due) {
        const e = new Date(Date.parse(it.e) + JST);
        const hm = `${e.getUTCMonth() + 1}/${e.getUTCDate()} ${e.getUTCHours()}:${String(e.getUTCMinutes()).padStart(2, "0")}`;
        const msg = kind === "3h"
          ? { title: "⏰ 締切まであと3時間", body: `${it.t}\n締切 ${hm}。応募がまだなら今のうちに！`, url: "/" + it.u.replace(/^\//, ""), tag: it.k }
          : { title: "📅 明日が締切の抽選があります", body: `${it.t}\n締切 ${hm}`, url: "/" + it.u.replace(/^\//, ""), tag: it.k };
        let st = 0;
        try { st = await sendPush(env, rec.s, msg); } catch { st = 0; }
        if (st === 404 || st === 410) { gone = true; break; }
        rec.sent[it.k + kind] = 1; sent++;
      }
      if (gone) { await env.STATE.delete(key.name); dead++; continue; }
      await saveRec(env, key.name.slice(3), rec, now);
    }
    cursor = r.list_complete ? null : r.cursor;
  } while (cursor);
  if (sent || dead) await env.STATE.put("push_last", JSON.stringify({ at: new Date(now).toISOString(), sent, dead }));
  return { sent, dead };
}

export async function pushStats(env) {
  let cursor, n = 0;
  do { const r = await env.STATE.list({ prefix: "ps:", cursor }); n += r.keys.length; cursor = r.list_complete ? null : r.cursor; } while (cursor);
  return { subs: n, last: await env.STATE.get("push_last", "json") };
}
