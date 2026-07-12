"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * PWA install prompt + safe SW-update prompt — M16-P02.
 *
 * Install: captures `beforeinstallprompt`, shows a dismissible CTA, and
 * FREQUENCY-CAPS re-prompts via a localStorage timestamp (no nagging).
 *
 * Update: watches for a waiting service worker and offers a USER-TRIGGERED
 * reload. Activation posts `SKIP_WAITING` to the waiting worker — there is no
 * forced/silent skip-waiting that could serve a half-updated app.
 */

/** localStorage key holding the last time the install CTA was dismissed. */
export const INSTALL_DISMISS_KEY = "vergeo:pwa-install-dismissed-at";
/** Minimum gap before re-prompting after a dismissal (14 days). */
export const INSTALL_REPROMPT_MS = 14 * 24 * 60 * 60 * 1000;

/** Frequency cap: show only if never dismissed, or the cap window has elapsed. */
export function shouldShowInstallPrompt(lastDismissedAt: number | null, now: number): boolean {
  if (lastDismissedAt === null || Number.isNaN(lastDismissedAt)) {
    return true;
  }
  return now - lastDismissedAt >= INSTALL_REPROMPT_MS;
}

/** Ask a waiting service worker to activate — the app then reloads on takeover. */
export function promptSkipWaiting(registration: ServiceWorkerRegistration): void {
  registration.waiting?.postMessage({ type: "SKIP_WAITING" });
}

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function readLastDismissed(): number | null {
  try {
    const raw = window.localStorage.getItem(INSTALL_DISMISS_KEY);
    return raw === null ? null : Number.parseInt(raw, 10);
  } catch {
    return null;
  }
}

export default function InstallPrompt() {
  const t = useTranslations("common.install");
  const deferredRef = useRef<BeforeInstallPromptEvent | null>(null);
  const [installVisible, setInstallVisible] = useState(false);
  const [updateVisible, setUpdateVisible] = useState(false);
  const updateRegRef = useRef<ServiceWorkerRegistration | null>(null);

  // Install prompt capture + frequency cap.
  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      deferredRef.current = event as BeforeInstallPromptEvent;
      if (shouldShowInstallPrompt(readLastDismissed(), Date.now())) {
        setInstallVisible(true);
      }
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  // Safe SW-update detection (never silently activates a new worker).
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }
    let reloading = false;
    const onControllerChange = () => {
      if (reloading) return;
      reloading = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);

    void navigator.serviceWorker.getRegistration().then((registration) => {
      if (!registration) return;
      updateRegRef.current = registration;
      if (registration.waiting) {
        setUpdateVisible(true);
      }
      registration.addEventListener("updatefound", () => {
        const installing = registration.installing;
        if (!installing) return;
        installing.addEventListener("statechange", () => {
          if (installing.state === "installed" && navigator.serviceWorker.controller) {
            updateRegRef.current = registration;
            setUpdateVisible(true);
          }
        });
      });
    });

    return () => {
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    };
  }, []);

  const dismissInstall = useCallback(() => {
    try {
      window.localStorage.setItem(INSTALL_DISMISS_KEY, String(Date.now()));
    } catch {
      // Ignore storage failures — worst case we ask again next visit.
    }
    setInstallVisible(false);
  }, []);

  const install = useCallback(async () => {
    const deferred = deferredRef.current;
    setInstallVisible(false);
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    deferredRef.current = null;
  }, []);

  const applyUpdate = useCallback(() => {
    const registration = updateRegRef.current;
    setUpdateVisible(false);
    if (registration) {
      promptSkipWaiting(registration);
    }
  }, []);

  if (!installVisible && !updateVisible) {
    return null;
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-[360px] p-3">
      {updateVisible ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-2">
          <p className="text-body font-medium text-text">{t("updateBody")}</p>
          <button
            type="button"
            onClick={applyUpdate}
            className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
          >
            {t("updateAction")}
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-2">
          <p className="text-body font-medium text-text">{t("title")}</p>
          <p className="text-sm text-text-2">{t("body")}</p>
          <div className="mt-1 flex gap-2">
            <button
              type="button"
              onClick={() => void install()}
              className="inline-flex min-h-11 flex-1 items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface"
            >
              {t("action")}
            </button>
            <button
              type="button"
              onClick={dismissInstall}
              className="inline-flex min-h-11 items-center justify-center rounded border border-border px-4 text-body font-medium text-text"
            >
              {t("dismiss")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
