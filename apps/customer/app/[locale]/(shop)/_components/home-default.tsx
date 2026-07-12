import Link from "next/link";

import { ListingGrid, type CatalogListing } from "./plp/listing-grid";

import type { CategoryRow } from "./merch-data";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

/**
 * Data-driven default homepage (UI-P4).
 *
 * Rendered only when NO active merch slots are configured — admin merch config
 * always takes precedence (see page.tsx). Every rail is empty-safe: an empty or
 * failed catalog query renders nothing rather than a broken section, and the
 * page falls back to the existing welcome hero when there is no data at all.
 */

const RAIL_DEPARTMENT_COUNT = 3;
const NEW_RAIL_LIMIT = 8;
const DEPARTMENT_RAIL_LIMIT = 4;

type CatalogApiItem = {
  id: string;
  title: string;
  product_slug: string | null;
  vendor_name: string;
  price_ngwee: number;
  condition: string;
  in_stock: boolean;
  image_public_id: string | null;
  rating: number;
  review_count: number;
  distance_m: number | null;
};

type CatalogApiResponse = {
  items: CatalogApiItem[];
};

export type DepartmentRail = {
  category: CategoryRow;
  listings: CatalogListing[];
};

export type HomeDefaultData = {
  newest: CatalogListing[];
  departmentRails: DepartmentRail[];
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

function mapListing(item: CatalogApiItem): CatalogListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    condition: item.condition,
    inStock: item.in_stock,
    imagePublicId: item.image_public_id,
    rating: item.rating,
    reviewCount: item.review_count,
    distanceM: item.distance_m,
  };
}

/** Empty-safe catalog fetch: any error or non-OK response yields an empty rail. */
async function fetchRailListings(query: string): Promise<CatalogListing[]> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/catalog/listings?${query}`, {
      next: { revalidate: 60 },
    });
    if (!response.ok) {
      return [];
    }
    const data = (await response.json()) as CatalogApiResponse;
    return (data.items ?? []).map(mapListing);
  } catch {
    return [];
  }
}

export function pickRailDepartments(
  categories: CategoryRow[],
  max: number = RAIL_DEPARTMENT_COUNT,
): CategoryRow[] {
  return categories.slice(0, max);
}

export function hasDefaultHomeContent(categories: CategoryRow[], data: HomeDefaultData): boolean {
  return (
    categories.length > 0 ||
    data.newest.length > 0 ||
    data.departmentRails.some((rail) => rail.listings.length > 0)
  );
}

export async function loadHomeDefaultData(categories: CategoryRow[]): Promise<HomeDefaultData> {
  const departments = pickRailDepartments(categories);
  const [newest, ...departmentListings] = await Promise.all([
    fetchRailListings(`sort=newest&limit=${NEW_RAIL_LIMIT}`),
    ...departments.map((category) =>
      fetchRailListings(
        `category_path=${encodeURIComponent(category.path)}&sort=newest&limit=${DEPARTMENT_RAIL_LIMIT}`,
      ),
    ),
  ]);

  return {
    newest,
    departmentRails: departments.map((category, index) => ({
      category,
      listings: departmentListings[index] ?? [],
    })),
  };
}

type HomeHeroBandProps = {
  locale: string;
  t: CatalogTranslator;
};

/**
 * Default hero band — escrow/trust messaging on the token gradient
 * (from-primary-deep to-primary). Text uses --primary-btn-fg, the on-primary
 * foreground token that stays AA in both light and dark themes.
 */
export function HomeHeroBand({ locale, t }: HomeHeroBandProps) {
  const escrowSteps = [
    t("home.hero.escrowStep1"),
    t("home.hero.escrowStep2"),
    t("home.hero.escrowStep3"),
  ];

  return (
    <section
      aria-labelledby="home-hero-heading"
      className="motion-rise overflow-hidden rounded-lg bg-gradient-to-br from-primary-deep to-primary p-6 text-[var(--primary-btn-fg)] shadow-2 lg:p-12"
    >
      <div className="flex flex-col gap-4 lg:max-w-3xl">
        <p className="text-micro font-semibold uppercase opacity-80">{t("home.hero.eyebrow")}</p>
        <h1 id="home-hero-heading" className="font-display text-hero">
          {t("home.hero.fallbackTitle")}
        </h1>
        <p className="text-body opacity-90">{t("home.hero.escrowLine")}</p>
        <ol className="flex list-none flex-wrap items-center gap-2 p-0">
          {escrowSteps.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              {index > 0 ? (
                <span aria-hidden className="opacity-70">
                  {"→"}
                </span>
              ) : null}
              <span className="rounded-pill border border-current px-3 py-1 text-micro font-semibold uppercase opacity-90">
                {step}
              </span>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap gap-2 pt-2">
          <Link
            href={`/${locale}/search`}
            className="inline-flex min-h-11 items-center justify-center rounded-pill bg-surface px-5 text-sm font-semibold text-primary"
          >
            {t("home.hero.primaryCta")}
          </Link>
          <Link
            href={`/${locale}/sell`}
            className="inline-flex min-h-11 items-center justify-center rounded-pill border border-current px-5 text-sm font-semibold"
          >
            {t("home.hero.secondaryCta")}
          </Link>
        </div>
      </div>
    </section>
  );
}

type RailLabels = {
  vendor: string;
  noReviews: string;
  reviewCount: string;
  quickAdd: string;
  wishlist: string;
  outOfStock: string;
  distance: string;
};

type HomeProductRailProps = {
  id: string;
  title: string;
  viewAllHref: string;
  viewAllLabel: string;
  listings: CatalogListing[];
  locale: string;
  labels: RailLabels;
  priorityCount?: number;
};

export function HomeProductRail({
  id,
  title,
  viewAllHref,
  viewAllLabel,
  listings,
  locale,
  labels,
  priorityCount = 0,
}: HomeProductRailProps) {
  if (listings.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby={id} className="motion-rise flex flex-col gap-3 lg:gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="font-display text-h2 text-display-ink">
          {title}
        </h2>
        <Link href={viewAllHref} className="shrink-0 text-sm font-medium text-primary">
          {viewAllLabel}
        </Link>
      </div>
      <ListingGrid
        locale={locale}
        listings={listings}
        labels={labels}
        priorityCount={priorityCount}
      />
    </section>
  );
}

type HomeSellCtaProps = {
  locale: string;
  t: CatalogTranslator;
};

export function HomeSellCta({ locale, t }: HomeSellCtaProps) {
  return (
    <section
      aria-labelledby="home-sell-cta-heading"
      className="motion-rise flex flex-col gap-4 rounded-lg bg-panel p-6 text-panel-text shadow-2 lg:flex-row lg:items-center lg:justify-between lg:gap-8 lg:p-10"
    >
      <div className="flex flex-col gap-2 lg:max-w-2xl">
        <h2 id="home-sell-cta-heading" className="font-display text-h2 text-panel-text">
          {t("home.sellCta.title")}
        </h2>
        <p className="text-body text-panel-muted">{t("home.sellCta.body")}</p>
      </div>
      <Link
        href={`/${locale}/sell`}
        className="inline-flex min-h-11 shrink-0 items-center justify-center self-start rounded-pill bg-primary px-6 text-sm font-semibold text-[var(--primary-btn-fg)] lg:self-center"
      >
        {t("home.sellCta.cta")}
      </Link>
    </section>
  );
}
