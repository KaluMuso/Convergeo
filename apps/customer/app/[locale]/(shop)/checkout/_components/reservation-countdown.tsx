"use client";

import { useEffect, useState } from "react";

type ReservationCountdownProps = {
  expiresAt: string;
  label: string;
  expiredLabel: string;
  ariaLiveLabel: (time: string) => string;
  onExpired: () => void;
};

function formatRemaining(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function ReservationCountdown({
  expiresAt,
  label,
  expiredLabel,
  ariaLiveLabel,
  onExpired,
}: ReservationCountdownProps) {
  const [remainingMs, setRemainingMs] = useState(() => {
    return new Date(expiresAt).getTime() - Date.now();
  });

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = new Date(expiresAt).getTime() - Date.now();
      setRemainingMs(next);
      if (next <= 0) {
        window.clearInterval(timer);
        onExpired();
      }
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [expiresAt, onExpired]);

  const expired = remainingMs <= 0;
  const display = expired ? expiredLabel : formatRemaining(remainingMs);

  return (
    <div
      className="flex items-center justify-between gap-3 rounded-card border border-warning/30 bg-warning/10 px-4 py-3"
      role="status"
      aria-live="polite"
      aria-label={ariaLiveLabel(display)}
    >
      <span className="font-body text-sm text-text">{label}</span>
      <span className="font-mono text-lg font-semibold tabular-nums text-warning">{display}</span>
    </div>
  );
}
