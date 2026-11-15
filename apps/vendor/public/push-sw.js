/*
 * Vendor PWA push worker (feature flag `web_push`, default OFF).
 *
 * The vendor app has no Serwist build yet, so this is a tiny hand-written,
 * push-only worker: no fetch handler, no caching. It is registered only from
 * the notifications page after the vendor taps "Turn on phone alerts".
 * Payload contract mirrors apps/customer/lib/push-payload.ts:
 *   { "title": string, "body": string, "url": "/en/orders/…", "badge": number }
 */
const FALLBACK_URL = "/en/notifications";
const SAFE_PATH = /^\/[A-Za-z0-9/_-]{0,240}$/;

function safeUrl(value) {
  return typeof value === "string" && SAFE_PATH.test(value) && !value.startsWith("//")
    ? value
    : FALLBACK_URL;
}

function text(value) {
  return typeof value === "string" ? value.slice(0, 240) : "";
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? JSON.parse(event.data.text()) : {};
  } catch {
    data = {};
  }
  const badge = typeof data.badge === "number" && data.badge >= 0 ? Math.floor(data.badge) : null;
  const tasks = [
    self.registration.showNotification(text(data.title) || "Convergeo", {
      body: text(data.body),
      tag: "vergeo-vendor-notification",
      data: { url: safeUrl(data.url) },
    }),
  ];
  if (badge !== null && self.navigator && typeof self.navigator.setAppBadge === "function") {
    tasks.push(self.navigator.setAppBadge(badge).catch(() => undefined));
  }
  event.waitUntil(Promise.all(tasks));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = safeUrl(event.notification.data && event.notification.data.url);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows[0];
      if (open) {
        return open.focus().then(() => (open.navigate ? open.navigate(url) : undefined));
      }
      return self.clients.openWindow(url);
    }),
  );
});
