"use client";

import { useEffect, useState } from "react";

type DealCountdownProps = {
  endsAt: string;
  /** Server clock at render — corrects for a skewed device clock. */
  serverTime: string;
  template: string;
  endedLabel: string;
};

function format(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** Live "Ends in 2:14:09" — ticks each second, never announced to screen readers. */
export function DealCountdown({
  endsAt,
  serverTime,
  template,
  endedLabel,
}: DealCountdownProps) {
  const [skew] = useState(() => Date.parse(serverTime) - Date.now());
  const end = Date.parse(endsAt);
  const [now, setNow] = useState(() => Date.now() + skew);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() + skew), 1000);
    return () => window.clearInterval(timer);
  }, [skew]);

  const left = end - now;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm bg-discount px-1.5 py-0.5 text-xs font-bold tabular-nums text-[var(--on-danger)]"
      data-testid="deal-countdown"
      suppressHydrationWarning
    >
      {left > 0 ? template.replace("{time}", format(left)) : endedLabel}
    </span>
  );
}
