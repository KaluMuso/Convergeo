"use client";

import { useEffect, useState } from "react";

export type CountdownLabels = {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
  expired: string;
  /** Accessible summary, e.g. "Ends in {time}". Receives a human string. */
  ariaLabel: (time: string) => string;
};

export type CountdownProps = {
  /** Target instant, ISO 8601. */
  endsAt: string;
  labels: CountdownLabels;
  className?: string;
};

type Remaining = {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
  done: boolean;
};

function computeRemaining(endsAtMs: number): Remaining {
  const ms = Math.max(0, endsAtMs - Date.now());
  const totalSeconds = Math.floor(ms / 1000);
  return {
    days: Math.floor(totalSeconds / 86400),
    hours: Math.floor((totalSeconds % 86400) / 3600),
    minutes: Math.floor((totalSeconds % 3600) / 60),
    seconds: totalSeconds % 60,
    done: ms <= 0,
  };
}

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

/**
 * Live HH:MM:SS(+days) countdown. Client-only ticking: the value is computed in
 * an effect (not during render) so server and first client render agree — the
 * blocks show "--" until mount, then tick each second. `aria-live` is off so a
 * per-second timer doesn't flood assistive tech; the `aria-label` carries the
 * current remaining time for anyone who focuses it.
 */
export function Countdown({ endsAt, labels, className }: CountdownProps) {
  const endsAtMs = new Date(endsAt).getTime();
  const [remaining, setRemaining] = useState<Remaining | null>(null);

  useEffect(() => {
    if (Number.isNaN(endsAtMs)) {
      return;
    }
    setRemaining(computeRemaining(endsAtMs));
    const timer = window.setInterval(() => {
      const next = computeRemaining(endsAtMs);
      setRemaining(next);
      if (next.done) {
        window.clearInterval(timer);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [endsAtMs]);

  if (remaining?.done) {
    return (
      <span role="status" className={className}>
        {labels.expired}
      </span>
    );
  }

  const values = remaining
    ? [pad(remaining.days), pad(remaining.hours), pad(remaining.minutes), pad(remaining.seconds)]
    : ["--", "--", "--", "--"];
  const blockLabels = [labels.days, labels.hours, labels.minutes, labels.seconds];
  const summary = values.map((value, index) => `${value} ${blockLabels[index]}`).join(" ");

  return (
    <div role="timer" aria-live="off" aria-label={labels.ariaLabel(summary)} className={className}>
      {values.map((value, index) => (
        <span
          key={blockLabels[index]}
          className="inline-flex min-w-9 flex-col items-center"
          aria-hidden
        >
          <span className="font-mono text-lg font-semibold tabular-nums leading-none">{value}</span>
          <span className="mt-0.5 text-[0.6rem] uppercase tracking-wide opacity-80">
            {blockLabels[index]}
          </span>
        </span>
      ))}
    </div>
  );
}
