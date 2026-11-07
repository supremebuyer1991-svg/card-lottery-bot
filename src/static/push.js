/* トレカ抽選ナビ：ホーム画面に追加・締切の通知（11/7）
   ・「☐ 応募した」の抽選の締切の前日夜と3時間前に通知（通知をオンにした人だけ）
   ・送るのは通知の送り先と、応募したリストの抽選（締切・名前・ページ）だけ。名前やメールは送らない */
(function () {
  var W = "https://rakuten-watch.supreme-buyer-1991.workers.dev", K = "lot_applied";
  var ua = navigator.userAgent, IOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  var SA = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  var CAN = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  function g(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function s(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function ga(n, p) { try { window.gtag && gtag("event", n, p || {}); } catch (e) {} }
  var reg = null;
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").then(function (r) { reg = r; afterReg(); }).catch(function () { box(); });

  function items() {
    var a = {}; try { a = JSON.parse(g(K) || "{}") || {}; } catch (e) {}
    var now = Date.now(), out = [];
    Object.keys(a).forEach(function (k) {
      var o = a[k]; if (!o || typeof o !== "object" || !o.end) return;
      if (Date.parse(o.end) <= now) return;
      out.push({ k: k, e: o.end, t: (o.store || "抽選") + "「" + (o.series || o.product || "") + "」", u: o.lpath || "mylist/" });
    });
    return out;
  }
  function getSub() { return reg && reg.pushManager ? reg.pushManager.getSubscription() : Promise.resolve(null); }
  function post(path, body) {
    return fetch(W + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(function (r) { return r.json(); });
  }
  function sync(force, hello) {
    return getSub().then(function (sub) {
      if (!sub) return null;
      var it = items(), sig = sub.endpoint.slice(-24) + JSON.stringify(it.map(function (x) { return x.k + x.e; }));
      if (!force && g("push_sig") === sig) return null;
      return post("/push/sub", { sub: sub.toJSON(), items: it, hello: !!hello }).then(function (j) { s("push_sig", sig); return j; });
    }).catch(function () { return null; });
  }
  function b64(u) { var p = "=".repeat((4 - u.length % 4) % 4), r = atob((u + p).replace(/-/g, "+").replace(/_/g, "/")), a = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) a[i] = r.charCodeAt(i); return a; }
  function enable() {
    if (!CAN) return Promise.resolve("unsupported");
    return Notification.requestPermission().then(function (p) {
      if (p !== "granted") { ga("push_denied"); return p; }
      return (reg ? Promise.resolve(reg) : navigator.serviceWorker.ready).then(function (r) {
        reg = r;
        return fetch(W + "/push/key").then(function (x) { return x.json(); }).then(function (j) {
          return r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(j.k) });
        });
      }).then(function () { ga("push_on"); return sync(true, true); }).then(function () { return "on"; });
    }).catch(function () { return "error"; });
  }
  function state() {
    if (!CAN) return Promise.resolve(IOS && !SA ? "ios" : "unsupported");
    if (Notification.permission === "denied") return Promise.resolve("denied");
    return getSub().then(function (x) { return x ? "on" : "off"; });
  }

  // 「応募した」を押したら（このページの中の保存を見張る）通知の登録も新しくする
  var t = null, prevN = items().length;
  try {
    var orig = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) {
      orig.apply(this, arguments);
      if (k === K) { clearTimeout(t); t = setTimeout(function () { var n = items().length; var up = n > prevN; prevN = n; sync(); if (up) nudge(); }, 1200); }
    };
  } catch (e) {}

  // ---- 見た目 ----
  var css = ".tnp-bar{position:fixed;left:10px;right:10px;bottom:10px;z-index:9999;max-width:520px;margin:0 auto;background:#1a1a1a;color:#fff;border-radius:14px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.25);font-size:13.5px;line-height:1.5;display:flex;gap:10px;align-items:center;flex-wrap:wrap}" +
    ".tnp-bar b{flex:1 1 200px}.tnp-bar button{font:inherit;font-weight:700;border:0;border-radius:999px;padding:8px 14px;cursor:pointer}.tnp-bar .y{background:#c8102e;color:#fff}.tnp-bar .n{background:transparent;color:#bbb;padding:8px 6px}" +
    ".tnp-box{background:var(--card,#fff);color:var(--ink,#111);border:2px solid #c8102e;border-radius:12px;padding:12px 14px;margin:0 0 12px;font-size:13.5px;line-height:1.6}.tnp-box b{display:block;font-size:15px;margin-bottom:2px}" +
    ".tnp-box button{display:block;width:100%;font:inherit;font-weight:700;font-size:15px;margin-top:8px;padding:11px;border:0;border-radius:10px;background:#c8102e;color:#fff;cursor:pointer}.tnp-box .ok{color:var(--done,#067a3a);font-weight:700}.tnp-box small{color:var(--ink-2,#666);display:block;margin-top:6px}" +
    ".tnp-box .tnp-ios{display:block;margin:8px 0 0;padding-left:1.3em;list-style:decimal}.tnp-box .tnp-ios li{display:list-item;margin:2px 0;padding:0;border:0;min-height:0;background:none;font-size:13.5px}.tnp-box .tnp-ios li b{display:inline;font-size:inherit;margin:0}";
  function addCss() { if (document.getElementById("tnp-css")) return; var st = document.createElement("style"); st.id = "tnp-css"; st.textContent = css; document.head.appendChild(st); }
  function bar(html, yes, onYes, key) {
    addCss(); var old = document.querySelector(".tnp-bar"); if (old) old.remove();
    var d = document.createElement("div"); d.className = "tnp-bar"; d.setAttribute("role", "dialog");
    d.innerHTML = "<b>" + html + "</b>" + (yes ? '<button class="y" type="button">' + yes + "</button>" : "") + '<button class="n" type="button" aria-label="閉じる">あとで</button>';
    document.body.appendChild(d);
    if (yes) d.querySelector(".y").onclick = function () { d.remove(); onYes(); };
    d.querySelector(".n").onclick = function () { d.remove(); if (key) s(key, String(Date.now())); };
  }
  var IOS_HOW = '<ol class="tnp-ios"><li>画面下の <b style="display:inline">共有ボタン（□に↑）</b>を押す</li><li>「<b style="display:inline">ホーム画面に追加</b>」を押す</li><li>ホーム画面のアイコンから開いて、この画面の「通知を受け取る」を押す</li></ol>';
  function recent(key, days) { var v = +g(key) || 0; return Date.now() - v < days * 864e5; }

  // 応募したを押した直後：通知のおすすめ（14日に1回まで）
  function nudge() {
    if (recent("tnp_nudge", 14) || location.pathname.indexOf("/mylist") === 0) return;
    state().then(function (st) {
      if (st === "off") bar("🔔 締切の前日夜と3時間前に通知しましょうか？（応募のし忘れ防止）", "通知を受け取る", function () { enable().then(function (r) { if (r === "on") bar("🔔 通知をオンにしました。応募したリストの締切前にお知らせします。"); }); }, "tnp_nudge");
      else if (st === "ios") bar("🔔 iPhoneはホーム画面に追加すると、締切前の通知を受け取れます", "やり方を見る", function () { location.href = "/mylist/#push"; }, "tnp_nudge");
      if (st === "off" || st === "ios") s("tnp_nudge", String(Date.now()));
    });
  }

  // ホーム画面に追加のおすすめ（2回目以降の訪問・30日に1回まで）
  var dp = null;
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); dp = e; installNudge(); });
  window.addEventListener("appinstalled", function () { ga("pwa_installed"); });
  var visits = (+g("tnp_v") || 0) + 1; s("tnp_v", String(visits));
  function installNudge() {
    if (SA || visits < 2 || recent("tnp_inst", 30) || document.querySelector(".tnp-bar")) return;
    if (dp) bar("📲 ホーム画面に追加すると、アプリみたいにすぐ開けます", "追加する", function () { dp.prompt(); dp.userChoice.then(function (c) { ga("pwa_prompt", { outcome: c.outcome }); }); dp = null; }, "tnp_inst");
    else if (IOS && /Safari/.test(ua) && !/CriOS|FxiOS|Line\//.test(ua)) bar("📲 ホーム画面に追加すると、アプリみたいにすぐ開けて締切の通知も届きます", "やり方を見る", function () { location.href = "/mylist/#push"; }, "tnp_inst");
    else return;
    s("tnp_inst", String(Date.now()));
  }
  if (location.pathname === "/" ) setTimeout(installNudge, 4000);

  // 応募したリストのページ：通知の欄
  function box() {
    var el = document.getElementById("pushbox"); if (!el) return;
    addCss(); el.className = "tnp-box"; el.id = "push";
    state().then(function (st) {
      if (st === "on") { el.innerHTML = '<span class="ok">🔔 締切の通知はオンです</span>　リストに入れた抽選の、締切の前日夜（20時）と3時間前にお知らせします。<small>止めたいときは、ブラウザの設定でこのサイトの通知をオフにしてください。</small>'; sync(); return; }
      if (st === "denied") { el.innerHTML = "<b>🔕 通知がブロックされています</b>ブラウザの設定で、このサイト（tcg-chusen.com）の通知を「許可」にすると、締切前にお知らせできます。"; return; }
      if (st === "ios") { el.innerHTML = "<b>🔔 締切前に通知を受け取る（iPhone）</b>iPhoneは、このサイトを<b style=\"display:inline\">ホーム画面に追加</b>すると通知を受け取れます（iOS 16.4以降）。" + IOS_HOW; return; }
      if (st === "unsupported") { el.innerHTML = "<b>🔔 締切前の通知</b>このブラウザは通知に対応していません。Chrome・Safari（ホーム画面に追加）・Edgeなどで開いてください。下の「カレンダーに入れる」でも締切前に通知できます。"; return; }
      el.innerHTML = "<b>🔔 応募のし忘れ・締切を通知でお知らせ</b>リストに入れた抽選の、<b style=\"display:inline\">締切の前日夜（20時）と3時間前</b>にスマホ・パソコンに通知が届きます。会員登録はいりません。" +
        '<button type="button">通知を受け取る</button><small>名前やメールアドレスは送りません。いつでもブラウザの設定で止められます。</small>';
      el.querySelector("button").onclick = function () { this.disabled = true; this.textContent = "設定中…"; enable().then(function () { box(); }); };
    });
  }
  function afterReg() { box(); sync(); }
  if (!("serviceWorker" in navigator)) box();
  window.TNP = { enable: enable, sync: sync, state: state };
})();
