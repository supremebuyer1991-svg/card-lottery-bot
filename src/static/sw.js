// トレカ抽選ナビ：ホーム画面アプリ用と、締切の通知を受け取るためのもの（11/7）
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("push", (e) => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (_) { m = { title: "トレカ抽選ナビ", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(m.title || "トレカ抽選ナビ", {
    body: m.body || "", icon: "/icon-192.png", badge: "/icon-192.png", tag: m.tag || undefined,
    data: { url: m.url || "/mylist/" }, lang: "ja",
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/", self.location.origin);
  url.searchParams.set("utm_source", "push");
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
    for (const c of cs) if (c.url.startsWith(self.location.origin) && "navigate" in c) return c.navigate(url.href).then((w) => w && w.focus());
    return self.clients.openWindow(url.href);
  }));
});
