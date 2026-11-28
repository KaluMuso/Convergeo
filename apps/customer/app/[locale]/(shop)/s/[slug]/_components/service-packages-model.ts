/**
 * Service packages — pure view-model helpers (no React), unit-tested.
 * Money arrives as integer ngwee and is only formatted through `formatK`.
 */

/** Legacy Basic/Standard/Premium label; open-list packages have none. */
export type ServicePackageTier = "basic" | "standard" | "premium";

/** A service shows at most this many packages (the API caps active packages at 10). */
export const MAX_PACKAGES = 10;

export type ServicePackage = {
  id: string;
  tier?: ServicePackageTier | null;
  name: string;
  description: string | null;
  /** Integer ngwee, or null = "request a quote". */
  price_ngwee: number | null;
  delivery_days: number;
  revisions: number | null;
  includes: string[];
  /** Archetype-specific offer attributes (docs/plan/service-type-templates.md). */
  attributes?: Record<string, unknown>;
};

/**
 * Keeps the vendor's order (the API sends `sort_order`), drops duplicates and
 * junk, and caps the list — whatever the API sent.
 */
export function normalisePackages(input: unknown): ServicePackage[] {
  if (!Array.isArray(input)) return [];
  const seen = new Set<string>();
  const valid: ServicePackage[] = [];
  for (const raw of input) {
    if (!raw || typeof raw !== "object") continue;
    const pkg = raw as Partial<ServicePackage>;
    if (typeof pkg.id !== "string" || pkg.id === "" || seen.has(pkg.id)) continue;
    const price =
      typeof pkg.price_ngwee === "number" &&
      Number.isInteger(pkg.price_ngwee) &&
      pkg.price_ngwee > 0
        ? pkg.price_ngwee
        : null;
    seen.add(pkg.id);
    valid.push({
      id: pkg.id,
      tier:
        pkg.tier === "basic" || pkg.tier === "standard" || pkg.tier === "premium" ? pkg.tier : null,
      name: typeof pkg.name === "string" ? pkg.name : "",
      description: typeof pkg.description === "string" ? pkg.description : null,
      price_ngwee: price,
      delivery_days:
        typeof pkg.delivery_days === "number" && Number.isInteger(pkg.delivery_days)
          ? pkg.delivery_days
          : 1,
      revisions:
        typeof pkg.revisions === "number" && Number.isInteger(pkg.revisions) ? pkg.revisions : null,
      includes: Array.isArray(pkg.includes)
        ? pkg.includes.filter((item): item is string => typeof item === "string")
        : [],
      attributes:
        pkg.attributes && typeof pkg.attributes === "object" && !Array.isArray(pkg.attributes)
          ? (pkg.attributes as Record<string, unknown>)
          : {},
    });
  }
  return valid.slice(0, MAX_PACKAGES);
}

/**
 * The quote request text the modal opens with. The template comes from i18n
 * (`services.packages.prefill`); the caller supplies a translator.
 */
export function buildPrefill(
  pkg: ServicePackage,
  t: (key: string, values?: Record<string, string | number>) => string,
  formatPrice: (ngwee: number) => string,
): string {
  return t("prefill", {
    name: pkg.name,
    price: pkg.price_ngwee !== null ? formatPrice(pkg.price_ngwee) : t("prefillPriceQuote"),
    days: pkg.delivery_days,
  });
}
