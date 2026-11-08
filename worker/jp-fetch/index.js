// 日本の買取店のページを代わりに読む中継（GitHubのサーバーからだと断られるお店があるため）
// ・決まったお店（ALLOW）だけ。鍵（KEY）が合わないと使えない
// ・同じページは1時間キャッシュ（お店に負担をかけない）
const ALLOW = [
  "panda-kaitori.co.jp", "runto666.com", "jptomiya.com", "akiba-mobile.co.jp", "kaitoritojo.jp", "keitai-god.com",
  "guestmobile.jp", "jcka-mobile.co.jp", "twinkle-mobile.com", "mobileone.co.jp", "mobile-mix.jp", "pastec.net",
  "kaden-ichiba.com", "keitaispace.co.jp", "morimori-kaitori.jp", "mobile-ichiban.com", "gamekaitori.jp",
  "newenoking-kaitori.com", "kaitori-oku.jp", "kaitoristar.com", "somurie-kaitori.com", "top1mobile.net",
  "kaitori-homura.com", "kaitoriminato.com", "kaitori-mirai.com", "kaitori-rudeya.com", "kaitorishouten-co.jp",
  "tobansyoji.co.jp", "keitairakuen.com", "1-chome.com", "kaitori-search.app",
];
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (!env.KEY || u.searchParams.get("k") !== env.KEY) return new Response("forbidden", { status: 403 });
    const target = u.searchParams.get("u") || "";
    let host;
    try { host = new URL(target).hostname; } catch (e) { return new Response("bad url", { status: 400 }); }
    if (!ALLOW.some((a) => host === a || host.endsWith("." + a))) return new Response("host not allowed", { status: 400 });
    const init = { headers: { "User-Agent": UA, "Accept-Language": "ja,en;q=0.8", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8" },
                   cf: { cacheTtl: 3600, cacheEverything: true } };
    if (req.method === "POST") { init.method = "POST"; init.body = await req.text(); init.headers["Content-Type"] = req.headers.get("content-type") || "application/x-www-form-urlencoded"; }
    try {
      const r = await fetch(target, init);
      return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") || "text/html; charset=utf-8", "x-upstream-status": String(r.status) } });
    } catch (e) {
      return new Response("upstream error: " + e, { status: 502 });
    }
  },
};
