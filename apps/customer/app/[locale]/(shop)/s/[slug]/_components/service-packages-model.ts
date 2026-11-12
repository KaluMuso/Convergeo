/**
 * Service packages — pure view-model helpers (no React), unit-tested.
 * Money arrives as integer ngwee and is only formatted through `formatK`.
 */

export type ServicePackageTier = "basic" | "standard" | "premium";

export type ServicePackage = {
  id: string;
  tier: ServicePackageTier;
  name: string;
  description: string | null;
  /** Integer ngwee, or null = "request a quote". */
  price_ngwee: number | null;
  delivery_days: number;
  revisions: number | null;
  includes: string[];
};

const TIER_ORDER: Record<ServicePackageTier, number> = { basic: 0, standard: 1, premium: 2 };

/** Tier-ordered, at most one per tier, at most three — whatever the API sent. */
export function normalisePackages(input: unknown): ServicePackage[] {
  if (!Array.isArray(input)) return [];
  const seen = new Set<string>();
  const valid: ServicePackage[] = [];
  for (const raw of input) {
    if (!raw || typeof raw !== "object") continue;
    const pkg = raw as Partial<ServicePackage>;
    if (typeof pkg.id !== "string" || !pkg.tier || !(pkg.tier in TIER_ORDER)) continue;
    if (seen.has(pkg.tier)) continue;
    const price =
      typeof pkg.price_ngwee === "number" &&
      Number.isInteger(pkg.price_ngwee) &&
      pkg.price_ngwee > 0
        ? pkg.price_ngwee
        : null;
    seen.add(pkg.tier);
    valid.push({
      id: pkg.id,
      tier: pkg.tier,
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
    });
  }
  return valid.sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier]).slice(0, 3);
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
    tier: t(`tier.${pkg.tier}`),
    name: pkg.name,
    price: pkg.price_ngwee !== null ? formatPrice(pkg.price_ngwee) : t("prefillPriceQuote"),
    days: pkg.delivery_days,
  });
}
