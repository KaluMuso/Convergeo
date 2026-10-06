"use client";

import { useEffect, useRef, type ReactNode } from "react";

type Props = {
  ticketId: string;
  active: boolean;
  horizon: { ticket_id: string } | null;
  labels: {
    refreshInTemplate: string;
    offlineBody: string;
    offlineExpired: string;
  };
  children: ReactNode;
};

/** Owns the lifetime of rotation on both document loads and client navigation. */
export function TicketWalletRuntime({ ticketId, active, horizon, labels, children }: Props) {
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || !active) return;

    const windowSeconds = 60;
    const circumference = 2 * Math.PI * 46;
    let disposed = false;
    function tick() {
      if (disposed || !root?.isConnected) return;
      const seconds = Math.floor(Date.now() / 1000);
      const currentWindow = Math.floor(seconds / windowSeconds);
      const remaining = windowSeconds - (seconds % windowSeconds);
      const countdown = root.querySelector("[data-ticket-countdown]");
      if (countdown) {
        countdown.textContent = labels.refreshInTemplate.replace("__SEC__", String(remaining));
      }
      root
        .querySelector("[data-ticket-ring=progress]")
        ?.setAttribute("stroke-dashoffset", String((circumference * remaining) / windowSeconds));
      let available = false;
      // Only this authorized server render supplies displayable QR windows.
      // Browser storage never supplies authorization or additional payloads.
      for (const node of root.querySelectorAll<HTMLElement>("[data-ticket-qr-window]")) {
        node.hidden = Number(node.dataset.ticketQrWindow) !== currentWindow;
        if (!node.hidden) available = true;
      }
      const expired = root.querySelector<HTMLElement>("[data-ticket-qr-expired]");
      if (expired) expired.hidden = available;
      const offline = !navigator.onLine;
      root.querySelector("[data-ticket-offline-banner]")?.classList.toggle("hidden", !offline);
      const body = root.querySelector("[data-ticket-offline-body]");
      if (body && offline)
        body.textContent = available ? labels.offlineBody : labels.offlineExpired;
      if (remaining <= 1 && navigator.onLine) location.reload();
    }
    function dispose() {
      if (disposed) return;
      disposed = true;
      clearInterval(timer);
      window.removeEventListener("online", tick);
      window.removeEventListener("offline", tick);
      window.removeEventListener("focus", tick);
      window.removeEventListener("pageshow", tick);
      window.removeEventListener("pagehide", pagehide);
      document.removeEventListener("visibilitychange", tick);
    }
    function pagehide(event: PageTransitionEvent) {
      // bfcache freezes the interval; pageshow catches up when restored.
      if (!event.persisted) dispose();
    }
    try {
      if (horizon?.ticket_id === ticketId) {
        localStorage.setItem(
          `vergeo5:ticket-horizon:${ticketId}`,
          JSON.stringify({ ...horizon, cached_at: new Date().toISOString() }),
        );
      }
    } catch {
      // Storage denial or quota must not stop in-memory rotation.
    }
    tick();
    const timer = setInterval(tick, 1000);
    window.addEventListener("online", tick);
    window.addEventListener("offline", tick);
    window.addEventListener("focus", tick);
    window.addEventListener("pageshow", tick);
    window.addEventListener("pagehide", pagehide);
    document.addEventListener("visibilitychange", tick);
    return dispose;
  }, [ticketId, active, horizon, labels]);

  return (
    <section ref={rootRef} className="space-y-5" data-ticket-wallet={ticketId}>
      {children}
    </section>
  );
}
