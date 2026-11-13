export type BusinessSectionKey = "products" | "services" | "events" | "offers" | "clips";

export type SectionInput = {
  counts: Record<BusinessSectionKey, number>;
  /** API verdict per section (flag ON and ≥1 live item). Absent on older builds. */
  sections?: Partial<Record<BusinessSectionKey, boolean>>;
  offersEnabled?: boolean;
};

/**
 * Founder rule: a Business Home section shows only when its feature is switched
 * on AND the business has at least one live item in it. The API owns the flags;
 * the page still refuses to render a section with nothing in it.
 */
export function visibleSections({
  counts,
  sections,
  offersEnabled,
}: SectionInput): Record<BusinessSectionKey, boolean> {
  // Older API builds: products/services/events were always on, clips were
  // already flag-filtered server-side, offers follow `offers_enabled`.
  const fallback: Record<BusinessSectionKey, boolean> = {
    products: true,
    services: true,
    events: true,
    offers: offersEnabled ?? false,
    clips: true,
  };
  const keys = Object.keys(counts) as BusinessSectionKey[];
  return Object.fromEntries(
    keys.map((key) => [key, (sections?.[key] ?? fallback[key]) && counts[key] > 0]),
  ) as Record<BusinessSectionKey, boolean>;
}
