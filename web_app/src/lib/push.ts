/* Browser side of Web Push: permission, registration, subscription.
 *
 * The chain that has to hold for a reminder to arrive with the app closed:
 *
 *   service worker registered   -> browser keeps it after tabs close
 *   Notification permission     -> user granted it explicitly
 *   PushManager.subscribe       -> browser issues an endpoint + keys
 *   endpoint stored on server   -> the scheduler has somewhere to send
 *
 * Any one missing and nothing arrives, usually with no error anywhere. The
 * status object below reports each link so a failure can be pointed at rather
 * than guessed at.
 */
import { api, BACKEND_URL } from "@/lib/api";
import { deviceTimeZone } from "@/lib/timezone";

export interface PushStatus {
  enabled: boolean;
  devices: number;
  last_push_at: string | null;
  cooldown_hours: number;
  quiet_hours: string;
  currently_awake: boolean;
  scheduler_running: boolean;
}

export interface PushSendResult {
  sent: number;
  failed: number;
  removed: number;
  devices: number;
  detail: string | null;
}

/** Web Push needs all three. Safari on iOS only exposes them to installed PWAs. */
export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Service workers require a secure context; localhost counts as one. */
export function isSecureContext(): boolean {
  return typeof window !== "undefined" && window.isSecureContext;
}

export function permissionState(): NotificationPermission | "unsupported" {
  if (!isPushSupported()) return "unsupported";
  return Notification.permission;
}

/** The VAPID public key arrives base64url; PushManager wants raw bytes. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  // Scope "/" so the worker controls the whole app, not just /reminders.
  const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;
  return reg;
}

/**
 * Turn notifications on for this device.
 *
 * Throws with a message meant to be shown to the user - the failure modes here
 * are things they can act on (blocked permission, insecure origin) rather than
 * bugs.
 */
export async function enablePush(userId: number): Promise<PushStatus> {
  if (!isPushSupported()) {
    throw new Error(
      "This browser can't do web notifications. On iPhone, add CogniSense to your Home Screen first.",
    );
  }
  if (!isSecureContext()) {
    throw new Error(
      "Notifications need a secure connection (https, or localhost during development).",
    );
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error(
      permission === "denied"
        ? "Notifications are blocked for this site. Allow them in your browser's site settings, then try again."
        : "Notification permission was dismissed. Try again and choose Allow.",
    );
  }

  const registration = await registerServiceWorker();

  const { public_key: publicKey } = await api.get<{ public_key: string }>(
    "/push/vapid-public-key",
  );

  // If a subscription already exists it is reused; browsers hand back the same
  // endpoint, and re-subscribing with a DIFFERENT key would throw.
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, // required by Chrome; every push must show a notification
      applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
    });
  }

  await api.post("/push/subscribe", {
    user_id: userId,
    subscription: subscription.toJSON(),
    // Quiet hours follow the account's time zone. An account without one
    // takes this device's; a zone already set is never changed from here.
    timezone: deviceTimeZone(),
    user_agent: navigator.userAgent.slice(0, 400),
  });

  return getPushStatus(userId);
}

/** Turn notifications off for this device only; other devices keep theirs. */
export async function disablePush(userId: number): Promise<PushStatus> {
  if (isPushSupported()) {
    const registration = await navigator.serviceWorker.getRegistration("/");
    const subscription = await registration?.pushManager.getSubscription();
    if (subscription) {
      await api.post("/push/unsubscribe", { endpoint: subscription.endpoint });
      await subscription.unsubscribe();
    }
  }
  return getPushStatus(userId);
}

export function getPushStatus(userId: number): Promise<PushStatus> {
  return api.get<PushStatus>(`/push/status/${userId}`);
}

export function sendTestPush(userId: number): Promise<PushSendResult> {
  return api.post<PushSendResult>(`/push/test/${userId}`);
}

/** Diagnostic string for the UI when something in the chain is missing. */
export function describeBlocker(): string | null {
  if (!isPushSupported()) {
    return "This browser doesn't support web notifications. On iPhone, add CogniSense to your Home Screen first (iOS 16.4+).";
  }
  if (!isSecureContext()) {
    return `Notifications need a secure connection. This page is on ${window.location.origin}; use https or localhost.`;
  }
  if (Notification.permission === "denied") {
    return "Notifications are blocked for this site in your browser settings. Allow them there, then reload.";
  }
  return null;
}

export { BACKEND_URL };
