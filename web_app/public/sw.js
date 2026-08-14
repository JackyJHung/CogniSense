/* CogniSense service worker.
 *
 * This file is why a reminder can reach you with the app closed. The browser
 * keeps it registered after every tab is gone; when a push arrives, the browser
 * starts this worker, runs the handler, and shuts it down again.
 *
 * Served from web_app/public/, so it lives at the site root and its scope
 * covers the whole app. A service worker can only control pages at or below its
 * own path, so moving this into a subdirectory would silently stop it
 * controlling "/".
 *
 * Deliberately has no caching / offline logic. A memory-support tool showing
 * stale reminders from a cache would be worse than showing nothing, and this
 * worker exists for notifications only.
 */

const DEFAULT_URL = "/reminders";

self.addEventListener("install", () => {
  // Take over immediately instead of waiting for every old tab to close;
  // otherwise a newly-deployed worker sits idle behind the previous one.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    // A malformed or unencrypted payload must still surface something rather
    // than throwing away the push.
    data = {};
  }

  const title = data.title || "CogniSense";
  const options = {
    body: data.body || "Tap to check your reminders.",
    // Same tag replaces an earlier unread prompt instead of stacking up.
    tag: data.tag || "cognisense-reminder-check",
    renotify: false,
    icon: "/favicon.svg",
    badge: "/favicon.svg",
    data: { url: data.url || DEFAULT_URL },
  };

  // waitUntil keeps the worker alive until the notification is actually shown.
  // Without it the browser may kill the worker first and show nothing.
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || DEFAULT_URL;

  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      // Reuse an open tab if there is one, rather than piling up windows.
      for (const client of clients) {
        if ("focus" in client) {
          await client.focus();
          if ("navigate" in client) {
            try {
              await client.navigate(target);
            } catch (err) {
              /* cross-origin or blocked; focusing was the important part */
            }
          }
          return;
        }
      }

      if (self.clients.openWindow) {
        await self.clients.openWindow(target);
      }
    })(),
  );
});

self.addEventListener("pushsubscriptionchange", (event) => {
  // The push service rotated the endpoint. The old one is dead; the app
  // re-subscribes on next load and the backend prunes the stale row when it
  // gets a 404/410. Logged so the cause is visible in DevTools.
  console.info("[cognisense sw] push subscription changed; will re-register on next load");
});
