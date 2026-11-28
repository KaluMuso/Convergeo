import type { Namespace } from "@vergeo/i18n";

/**
 * Per-route message payloads for the vendor app.
 *
 * The vendor locale layout used to ship the whole `vendor`, `services`, `events` and
 * `notifications` catalogs (~170KB raw) to every page, and they are serialised into the
 * RSC flight payload on every navigation. Now the layout ships only `BASE_SPEC` (shell
 * chrome) and each route segment layout adds what its client views read via
 * `<RouteMessages>`.
 *
 * A spec entry is a dotted path into the namespace. `"listings"` ships the whole
 * `vendor.listings` branch; `"listings.images"` ships only that sub-branch. `true` ships
 * a whole namespace. `route-messages.test.ts` statically walks every route's import graph
 * and fails when a client view reads a key its route does not ship (a raw-key regression).
 */
export type MessageSpec = Partial<Record<Namespace, readonly string[] | true>>;

type Messages = { [key: string]: string | Messages };

/** Chrome rendered on every authenticated page: nav, business switcher, trial banner, bell. */
export const BASE_SPEC = {
  vendor: ["shell", "trial", "vendor", "branches.switcher", "branches.status"],
  notifications: ["center", "inApp"],
} as const satisfies MessageSpec;

const IMAGES = ["listings.images", "plans"] as const;

export const ROUTE_SPEC = {
  home: { vendor: ["home", "requests", "queue", "orders"] },
  analytics: { vendor: ["analytics"] },
  businesses: { vendor: ["branches", "profile"] },
  clips: { vendor: ["clips"] },
  coupons: { vendor: ["coupons"] },
  disputes: { vendor: ["disputes", "requests"] },
  events: {
    vendor: ["events", "eventDashboard", "eventRoster", "scan", "tickets", ...IMAGES],
    events: true,
  },
  extras: { vendor: ["extras"] },
  intake: { vendor: ["intake", "listings"] },
  jobs: { vendor: ["jobs", "requests"], services: true },
  listings: { vendor: ["listings", "plans"] },
  offers: { vendor: ["offers"] },
  onboarding: { vendor: ["onboarding"] },
  orders: { vendor: ["home", "orders", "queue", "requests"] },
  payouts: { vendor: ["payouts"] },
  plan: { vendor: ["plans"] },
  profile: { vendor: ["profile", ...IMAGES] },
  returns: { vendor: ["returns"] },
  reviews: { vendor: ["reviews", "requests"] },
  rfq: { vendor: ["rfq", "requests"] },
  scan: { vendor: ["scan"] },
  // service-form reads vendor.listings.fields.priceInvalid for its price validation.
  services: {
    vendor: ["events", "listings.fields.priceInvalid", ...IMAGES],
    services: true,
    events: true,
  },
  settings: { vendor: ["settings"] },
  source: { vendor: ["source"] },
} as const satisfies Record<string, MessageSpec>;

export type RouteKey = keyof typeof ROUTE_SPEC;

export function specNamespaces(spec: MessageSpec): Namespace[] {
  return Object.keys(spec) as Namespace[];
}

function isBranch(value: unknown): value is Messages {
  return typeof value === "object" && value !== null;
}

/** Copy `path` (dotted) from `source` into `target`, creating intermediate objects. */
function copyPath(source: Messages, target: Messages, path: string): void {
  const parts = path.split(".");
  let from: unknown = source;
  for (const part of parts) {
    if (!isBranch(from) || !Object.hasOwn(from, part)) return;
    from = from[part];
  }
  let to = target;
  for (const part of parts.slice(0, -1)) {
    const next = Object.hasOwn(to, part) ? to[part] : undefined;
    if (isBranch(next)) {
      to = next;
    } else {
      const created: Messages = {};
      to[part] = created;
      to = created;
    }
  }
  const leaf = parts.at(-1) as string;
  const existing = Object.hasOwn(to, leaf) ? to[leaf] : undefined;
  to[leaf] =
    isBranch(existing) && isBranch(from)
      ? { ...existing, ...(from as Messages) }
      : (from as Messages);
}

/** Deep-pick the listed dotted paths out of one namespace's messages. */
export function pickMessages(source: Messages, paths: readonly string[] | true): Messages {
  if (paths === true) return source;
  const out: Messages = {};
  for (const path of paths) copyPath(source, out, path);
  return out;
}

/** Merge two namespace trees (b wins on leaf collisions). */
export function mergeMessageTrees(a: Messages, b: Messages): Messages {
  const out: Messages = { ...a };
  for (const [key, value] of Object.entries(b)) {
    const existing = Object.hasOwn(out, key) ? out[key] : undefined;
    out[key] =
      isBranch(existing) && isBranch(value)
        ? mergeMessageTrees(existing, value)
        : (value as Messages);
  }
  return out;
}

/** True when a dotted key path is shipped by a spec's entry list. */
export function specCovers(
  entries: readonly string[] | true | undefined,
  keyPath: string,
): boolean {
  if (entries === true) return true;
  if (!entries) return false;
  return entries.some((entry) => keyPath === entry || keyPath.startsWith(`${entry}.`));
}
