"use client";

import { EVENT_ARCHETYPES, isEventArchetype } from "@vergeo/ui/src/event-archetype";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useTransition } from "react";

/** Price ceilings offered as quick boxes, in integer ngwee (K50 / K100 / K200 / K500). */
export const PRICE_PRESETS_NGWEE = [5_000, 10_000, 20_000, 50_000] as const;

export type EventFilterBoxLabels = {
  typeLabel: string;
  typeAll: string;
  types: Record<string, string>;
  priceLabel: string;
  priceAny: string;
  priceUpTo: string;
  freeLabel: string;
};

type Props = {
  labels: EventFilterBoxLabels;
  activeArchetype: string | null;
  activePriceMax: number | null;
  freeOnly: boolean;
};

const boxBase =
  "min-h-11 rounded border px-3 text-sm font-medium transition-colors duration-fast focus-visible:outline-none focus-visible:shadow-focusRing";
const boxOn = "border-primary bg-primary text-[var(--primary-btn-fg)]";
const boxOff = "border-border bg-surface text-text hover:bg-bg-2";

/**
 * URL-synced filter boxes for the events listing: type (archetype), price ceiling and
 * free-only. Date, category and area live in `DateFilterChips`; both write the same
 * query string so filters compose and links are shareable.
 */
export function EventFilterBoxes({ labels, activeArchetype, activePriceMax, freeOnly }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const update = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, value);
      }
      // A new filter always restarts pagination.
      params.delete("page");
      startTransition(() => {
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname);
      });
    },
    [pathname, router, searchParams],
  );

  return (
    <div
      className="flex flex-col gap-3"
      data-testid="event-filter-boxes"
      aria-busy={isPending || undefined}
    >
      <div role="group" aria-label={labels.typeLabel} className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`${boxBase} ${activeArchetype === null ? boxOn : boxOff}`}
          aria-pressed={activeArchetype === null}
          onClick={() => update({ archetype: null })}
        >
          {labels.typeAll}
        </button>
        {EVENT_ARCHETYPES.filter((a) => a !== "generic").map((archetype) => (
          <button
            key={archetype}
            type="button"
            className={`${boxBase} ${activeArchetype === archetype ? boxOn : boxOff}`}
            aria-pressed={activeArchetype === archetype}
            onClick={() => update({ archetype })}
          >
            {labels.types[archetype] ?? archetype}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-text-2">
          <span>{labels.priceLabel}</span>
          <select
            className="min-h-11 rounded border border-border bg-surface px-3 text-sm text-text focus-visible:outline-none focus-visible:shadow-focusRing"
            value={activePriceMax === null ? "" : String(activePriceMax)}
            onChange={(event) =>
              update({
                price_max: event.target.value === "" ? null : event.target.value,
              })
            }
          >
            <option value="">{labels.priceAny}</option>
            {PRICE_PRESETS_NGWEE.map((ngwee) => (
              <option key={ngwee} value={ngwee}>
                {labels.priceUpTo.replace("{price}", `K${ngwee / 100}`)}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className={`${boxBase} ${freeOnly ? boxOn : boxOff}`}
          aria-pressed={freeOnly}
          onClick={() => update({ free: freeOnly ? null : "1" })}
        >
          {labels.freeLabel}
        </button>
      </div>
    </div>
  );
}

/** Parse helpers shared with the server page (kept here so they are unit-tested). */
export function parseArchetypeParam(value: string | undefined): string | null {
  return isEventArchetype(value) ? value : null;
}

export function parsePriceMaxParam(value: string | undefined): number | null {
  if (!value || !/^\d{1,9}$/.test(value)) return null;
  return Number.parseInt(value, 10);
}

export function parseFreeParam(value: string | undefined): boolean {
  return value === "1" || value === "true";
}
