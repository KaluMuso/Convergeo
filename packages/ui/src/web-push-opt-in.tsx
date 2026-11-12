"use client";

/**
 * Web Push opt-in (customer + vendor PWAs) — behind `feature_flags.web_push`
 * (default OFF). Renders nothing unless the API reports push as enabled AND the
 * browser supports Push. Permission is requested ONLY from the button tap,
 * never on load; a denied permission shows a short note and no button.
 */

import { useEffect, useState } from "react";

import type { NotificationRequest } from "./notification-center";

export type WebPushLabels = {
  enable: string;
  enabled: string;
  denied: string;
  hint: string;
  failed: string;
};

type Status = "hidden" | "idle" | "working" | "on" | "denied" | "failed";

type WebPushConfig = { enabled: boolean; vapid_public_key: string | null };

export function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const raw = atob(padded);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export type WebPushOptInProps = {
  request: NotificationRequest;
  audience: "customer" | "vendor";
  /** Worker that carries the push/notificationclick handlers. */
  serviceWorkerUrl: string;
  labels: WebPushLabels;
};

export function WebPushOptIn({ request, audience, serviceWorkerUrl, labels }: WebPushOptInProps) {
  const [status, setStatus] = useState<Status>("hidden");
  const [config, setConfig] = useState<WebPushConfig | null>(null);

  useEffect(() => {
    if (!pushSupported()) return;
    let active = true;
    void request<WebPushConfig>("/me/web-push")
      .then(async (cfg) => {
        if (!active || !cfg.enabled || !cfg.vapid_public_key) return;
        setConfig(cfg);
        if (Notification.permission === "denied") {
          setStatus("denied");
          return;
        }
        const registration = await navigator.serviceWorker.getRegistration(serviceWorkerUrl);
        const existing = await registration?.pushManager.getSubscription();
        if (active) setStatus(existing && Notification.permission === "granted" ? "on" : "idle");
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [request, serviceWorkerUrl]);

  const enable = async () => {
    if (!config?.vapid_public_key) return;
    setStatus("working");
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus(permission === "denied" ? "denied" : "idle");
        return;
      }
      const registration =
        (await navigator.serviceWorker.getRegistration(serviceWorkerUrl)) ??
        (await navigator.serviceWorker.register(serviceWorkerUrl));
      await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.vapid_public_key),
      });
      const json = subscription.toJSON();
      await request("/me/push-subscriptions", {
        method: "PUT",
        body: JSON.stringify({ audience, endpoint: json.endpoint, keys: json.keys }),
      });
      setStatus("on");
    } catch {
      setStatus("failed");
    }
  };

  if (status === "hidden") return null;

  return (
    <div className="v-notif__push" data-testid="web-push-opt-in">
      {status === "on" ? <p className="v-notif__push-note">{labels.enabled}</p> : null}
      {status === "denied" ? <p className="v-notif__push-note">{labels.denied}</p> : null}
      {status === "idle" || status === "working" || status === "failed" ? (
        <>
          <p className="v-notif__push-note">{status === "failed" ? labels.failed : labels.hint}</p>
          <button
            type="button"
            className="v-notif__more"
            onClick={() => void enable()}
            disabled={status === "working"}
          >
            {labels.enable}
          </button>
        </>
      ) : null}
    </div>
  );
}
