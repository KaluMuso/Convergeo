import { formatK } from "@vergeo/i18n";
import { SignalBadgeRow, type SignalBadgeKind } from "@vergeo/ui/src/signal-badge";
import { SignalRibbon, type SignalRibbonKind } from "@vergeo/ui/src/signal-ribbon";

import type { ReactNode } from "react";

/** Wire shape of `signals` from the API (docs/plan/product-signals.md). */
export type ListingSignalsWire = {
  ribbon?: SignalRibbonKind | null;
  badges?: SignalBadgeKind[];
  seller_count?: number | null;
  lowest_price_ngwee?: number | null;
  deal_percent?: number | null;
  distance_km?: number | null;
};

export type SignalLabels = {
  badge: Record<SignalBadgeKind, string>;
  /** "{km} km away" — appended to the near-you badge when a distance is known. */
  nearYouKm?: string;
  ribbon: Record<SignalRibbonKind, string>;
  /** "In {count} shops from {price}" */
  inShops: string;
};

const BADGE_KINDS: SignalBadgeKind[] = [
  "cheapest",
  "near_you",
  "made_in_zambia",
  "top_rated",
  "fast_delivery",
  "low_stock",
  "new",
];
const RIBBON_KINDS: SignalRibbonKind[] = ["preferred", "verified_business", "verified_id"];

/** Build labels from a next-intl translator for the `catalog` namespace. */
export function buildSignalLabels(t: (key: string) => string): SignalLabels {
  return {
    badge: Object.fromEntries(
      BADGE_KINDS.map((kind) => [kind, t(`signals.badge.${kind}`)]),
    ) as SignalLabels["badge"],
    nearYouKm: t("signals.badge.near_you_km"),
    ribbon: Object.fromEntries(
      RIBBON_KINDS.map((kind) => [kind, t(`signals.ribbon.${kind}`)]),
    ) as SignalLabels["ribbon"],
    inShops: t("signals.inShops"),
  };
}

export function signalBadgeEntries(
  signals: ListingSignalsWire | undefined | null,
  labels: SignalLabels | undefined,
): Array<{ kind: SignalBadgeKind; label: string }> {
  if (!signals || !labels) return [];
  const out: Array<{ kind: SignalBadgeKind; label: string }> = [];
  for (const kind of signals.badges ?? []) {
    const base = labels.badge[kind];
    if (!base) continue;
    const km = signals.distance_km;
    const label =
      kind === "near_you" && typeof km === "number" && labels.nearYouKm
        ? labels.nearYouKm.replace("{km}", String(km))
        : base;
    out.push({ kind, label });
  }
  return out.slice(0, 2);
}

export function inShopsLine(
  signals: ListingSignalsWire | undefined | null,
  labels: SignalLabels | undefined,
): string | null {
  if (!signals || !labels) return null;
  const count = signals.seller_count;
  const lowest = signals.lowest_price_ngwee;
  if (
    typeof count !== "number" ||
    count < 2 ||
    typeof lowest !== "number" ||
    !Number.isInteger(lowest)
  ) {
    return null;
  }
  return labels.inShops.replace("{count}", String(count)).replace("{price}", formatK(lowest));
}

export function signalSlots(
  signals: ListingSignalsWire | undefined | null,
  labels: SignalLabels | undefined,
): { ribbon: ReactNode; badges: ReactNode } {
  const entries = signalBadgeEntries(signals, labels);
  const ribbonKind = signals?.ribbon ?? null;
  return {
    ribbon:
      ribbonKind && labels?.ribbon[ribbonKind] ? (
        <SignalRibbon kind={ribbonKind} label={labels.ribbon[ribbonKind]} />
      ) : null,
    badges: entries.length > 0 ? <SignalBadgeRow badges={entries} /> : null,
  };
}
