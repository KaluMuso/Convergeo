import { IconTile } from "@vergeo/ui/src/icon-tile";
import type { IconHue } from "@vergeo/ui/src/icon-hues";
import type { ReactNode } from "react";

export type CustomerTrustStripItem = {
  id: string;
  label: string;
  hue: IconHue;
  icon: ReactNode;
  testId?: string;
};

export type CustomerTrustStripProps = {
  ariaLabel?: string;
  items: readonly CustomerTrustStripItem[];
  className?: string;
  compact?: boolean;
  "data-testid"?: string;
};

export function CustomerTrustStrip({
  ariaLabel,
  items,
  className,
  compact = false,
  "data-testid": dataTestId,
}: CustomerTrustStripProps) {
  const size = compact ? 32 : 40;

  return (
    <section
      data-testid={dataTestId}
      aria-label={ariaLabel}
      className={["rounded-xl border border-border bg-surface px-2 py-2 sm:px-3", className]
        .filter(Boolean)
        .join(" ")}
    >
      <ul
        className={
          compact
            ? "m-0 grid list-none gap-2 p-0"
            : "m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-4"
        }
      >
        {items.map((item) => (
          <li
            key={item.id}
            data-testid={item.testId}
            className="flex min-h-11 items-center gap-2 rounded-lg px-1.5 py-1 text-left text-xs font-medium leading-snug text-text-2 sm:justify-start sm:text-sm"
          >
            <IconTile hue={item.hue} size={size} className="shrink-0">
              {item.icon}
            </IconTile>
            <span className="min-w-0 flex-1 text-text">{item.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
