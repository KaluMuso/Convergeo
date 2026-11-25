import type { ReactNode } from "react";

import { IconTile } from "./icon-tile";
import type { IconHue } from "./icon-hues";

export type StatCardProps = {
  label: string;
  value: ReactNode;
  /** Optional delta chip, e.g. "+12%". */
  delta?: { text: string; trend: "up" | "down" | "neutral" };
  icon?: ReactNode;
  iconHue?: IconHue;
  sparkline?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const deltaStyle: Record<"up" | "down" | "neutral", { background: string; color: string }> = {
  up: {
    background: "color-mix(in srgb, var(--success) 12%, transparent)",
    color: "var(--success)",
  },
  down: {
    background: "color-mix(in srgb, var(--danger) 12%, transparent)",
    color: "var(--danger)",
  },
  neutral: { background: "var(--bg-2)", color: "var(--text-2)" },
};

/**
 * Dashboard metric card with optional icon tile, delta chip and sparkline slot.
 */
export function StatCard({
  label,
  value,
  delta,
  icon,
  iconHue = "slate",
  sparkline,
  className,
  "data-testid": dataTestId,
}: StatCardProps) {
  return (
    <article
      data-testid={dataTestId ?? "stat-card"}
      className={cx(
        "card-lift flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-1",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-sm font-medium text-text-2">{label}</p>
          <p className="font-display text-2xl font-semibold tabular-nums tracking-tight text-display-ink">
            {value}
          </p>
        </div>
        {icon ? (
          <IconTile hue={iconHue} size={40}>
            {icon}
          </IconTile>
        ) : null}
      </div>
      {(delta || sparkline) && (
        <div className="flex items-end justify-between gap-2">
          {delta ? (
            <span
              className="inline-flex rounded-pill px-2 py-0.5 text-micro font-medium tabular-nums"
              style={deltaStyle[delta.trend]}
            >
              {delta.text}
            </span>
          ) : (
            <span />
          )}
          {sparkline ? <div className="max-w-[8rem] shrink-0">{sparkline}</div> : null}
        </div>
      )}
    </article>
  );
}
