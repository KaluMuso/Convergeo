import type { Namespace } from "@vergeo/i18n";

/**
 * Per-route message payloads for the admin app.
 *
 * The locale layout used to ship the whole `admin` (128 kB raw), `services` and
 * `notifications` catalogs inside every document (~36 kB gzip of the ~47 kB HTML). Now the
 * layout ships only `BASE_SPEC` (shell chrome) and each route segment layout adds the
 * branches its client views read through `<RouteMessages>`.
 *
 * A spec entry is a dotted path into the namespace: `"orders"` ships `admin.orders`,
 * `"orders.search"` only that sub-branch, `true` a whole namespace.
 * `route-messages.test.ts` walks every route's import graph and fails when a client view
 * reads a key its route does not ship (a raw-key regression).
 */
export type MessageSpec = Partial<Record<Namespace, readonly string[] | true>>;

type Messages = { [key: string]: string | Messages };

/** Chrome rendered on every authenticated page: header, nav, account menu, notification bell. */
export const BASE_SPEC = {
  admin: ["nav", "shell", "title"],
  notifications: ["center", "inApp"],
} as const satisfies MessageSpec;

export const ROUTE_SPEC = {
  home: { admin: ["dashboard", "today"] },
  accounts: { admin: ["accountsUi", "boards", "common"] },
  advertising: { admin: ["advertising", "common"] },
  analytics: { admin: ["analytics"] },
  "audit-log": { admin: ["auditLogUi", "common"] },
  branches: { admin: ["branches"] },
  business: { admin: ["business"] },
  catalog: { admin: ["catalog", "common"] },
  clips: { admin: ["clips"] },
  config: { admin: ["config", "vendorPlans"] },
  coupons: { admin: ["coupons"] },
  disputes: { admin: ["common", "disputes"] },
  events: { admin: ["common", "events"] },
  "event-sponsors": { admin: ["common", "eventSponsors"] },
  extras: { admin: ["extras"] },
  "home-feed": { admin: ["homeFeed"] },
  intake: { admin: ["intake"] },
  inventory: { admin: ["oversightUi"] },
  kyc: { admin: ["common", "kyc"] },
  merch: { admin: ["merch"] },
  moderation: { admin: ["flags", "moderation"] },
  notifications: {},
  offers: { admin: ["offers"] },
  orders: { admin: ["boards", "common", "dispatch", "orders"], services: ["funding"] },
  roles: { admin: ["common", "rolesUi"] },
  services: { admin: ["oversightUi"] },
  support: { admin: ["boards", "support"] },
  theme: {},
  translations: { admin: ["translations"] },
  trials: { admin: ["trials"] },
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
