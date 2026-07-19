import { createServerClient } from "@vergeo/auth/server-client";
import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { buildCanonicalAlternates, buildLocaleCanonical } from "@vergeo/ui/src/seo/json-ld";
import { cookies } from "next/headers";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { type ApiPriceTier } from "../_components/supplies/qty-price-preview";
import {
  sortSupplyListings,
  TierPriceCards,
  type SupplyListing,
} from "../_components/supplies/tier-price-cards";

import type { Metadata } from "next";

type SuppliesSort = "moq" | "unit_price";

type BusinessStatusResponse = {
  has_application: boolean;
  status: string | null;
  eligible: boolean;
};

type CatalogApiListing = {
  id: string;
  title: string;
  product_slug: string | null;
  vendor_name: string;
  price_ngwee: number;
  image_public_id: string | null;
  wholesale?: boolean;
  moq?: number;
  price_tiers?: ApiPriceTier[] | null;
};

type CatalogApiResponse = {
  items: CatalogApiListing[];
  total: number;
};

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ sort?: string; qty?: string }>;
};

type SuppliesTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

async function getSuppliesTranslator(locale: string): Promise<SuppliesTranslator> {
  const baseMessages = await getMessages();
  const suppliesMessages = await loadNamespace(locale as Locale, "supplies");
  const messages = { ...baseMessages, supplies: suppliesMessages } as AbstractIntlMessages;

  return createTranslator({
    locale,
    messages,
    namespace: "supplies",
  }) as unknown as SuppliesTranslator;
}

function parseSort(value: string | undefined): SuppliesSort {
  if (value === "unit_price") {
    return "unit_price";
  }
  return "moq";
}

function parsePreviewQty(value: string | undefined): number {
  const parsed = Number.parseInt(value ?? "1", 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

async function getOptionalAccessToken(): Promise<string | null> {
  const cookieStore = await cookies();
  const supabase = createServerClient(cookieStore);
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

async function fetchBusinessStatus(token: string): Promise<BusinessStatusResponse | null> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/business/status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as BusinessStatusResponse;
  } catch {
    return null;
  }
}

async function fetchWholesaleCatalog(token: string): Promise<CatalogApiResponse | null> {
  const params = new URLSearchParams({
    wholesale: "true",
    limit: "48",
  });

  try {
    const response = await fetch(`${getApiBaseUrl()}/catalog/listings?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as CatalogApiResponse;
  } catch {
    return null;
  }
}

function mapListing(item: CatalogApiListing): SupplyListing {
  return {
    id: item.id,
    title: item.title,
    productSlug: item.product_slug,
    vendorName: item.vendor_name,
    priceNgwee: item.price_ngwee,
    wholesale: item.wholesale === true,
    moq: item.moq ?? 1,
    priceTiers: item.price_tiers ?? null,
    imagePublicId: item.image_public_id,
  };
}

function filterWholesaleOnly(listings: SupplyListing[]): SupplyListing[] {
  return listings.filter((listing) => listing.wholesale);
}

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getSuppliesTranslator(locale);

  return {
    title: t("title"),
    description: t("description"),
    alternates: buildCanonicalAlternates(locale, "supplies"),
    openGraph: {
      title: t("title"),
      description: t("description"),
      type: "website",
      locale,
      url: buildLocaleCanonical(locale, "supplies"),
    },
    robots: {
      // Wholesale supplies are gated to verified businesses — not public/indexable.
      index: false,
      follow: false,
    },
  };
}

function SuppliesGate({
  t,
  locale,
  signedIn,
  status,
}: {
  t: SuppliesTranslator;
  locale: string;
  signedIn: boolean;
  status: string | null;
}) {
  let title = t("gate.title");
  let body = t("gate.body");
  let ctaLabel = t("gate.apply");
  let href = `/${locale}/account/business`;

  if (!signedIn) {
    body = t("gate.signInBody");
    ctaLabel = t("gate.signIn");
    href = `/${locale}/login?next=/${locale}/supplies`;
  } else if (status === "pending") {
    title = t("gate.pendingTitle");
    body = t("gate.pendingBody");
  } else if (status === "rejected") {
    title = t("gate.rejectedTitle");
    body = t("gate.rejectedBody");
  }

  return (
    <div className="flex flex-col gap-4 lg:mx-auto lg:w-full lg:max-w-3xl">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-[var(--fs-h1)] text-[var(--text)]">{t("title")}</h1>
      </header>
      <div
        className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5"
        data-testid="supplies-business-gate"
      >
        <p className="font-display text-h3 text-text">{title}</p>
        <p className="text-sm text-text-2">{body}</p>
        <Link
          href={href}
          className="inline-flex min-h-11 w-fit items-center rounded-md bg-primary px-4 text-sm font-medium text-surface"
        >
          {ctaLabel}
        </Link>
      </div>
    </div>
  );
}

export default async function SuppliesPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const resolvedSearch = await searchParams;
  setRequestLocale(locale);

  const t = await getSuppliesTranslator(locale);

  // B2B gate: wholesale supplies are visible only to verified business buyers.
  const accessToken = await getOptionalAccessToken();
  const business = accessToken ? await fetchBusinessStatus(accessToken) : null;
  if (!accessToken || !business?.eligible) {
    return (
      <SuppliesGate
        t={t}
        locale={locale}
        signedIn={Boolean(accessToken)}
        status={business?.status ?? null}
      />
    );
  }

  const sort = parseSort(resolvedSearch.sort);
  const previewQty = parsePreviewQty(resolvedSearch.qty);

  const catalog = await fetchWholesaleCatalog(accessToken);
  const wholesaleListings = sortSupplyListings(
    filterWholesaleOnly((catalog?.items ?? []).map(mapListing)),
    sort,
    previewQty,
  );

  const labels = {
    vendor: t("card.vendor"),
    quantityLabel: t("card.quantityLabel"),
    decrease: t("card.decrease"),
    increase: t("card.increase"),
    decreaseSymbol: t("card.decreaseSymbol"),
    increaseSymbol: t("card.increaseSymbol"),
    noImage: t("card.noImage"),
    viewListing: t("card.viewListing"),
    tierQuantityHeader: t("tier.quantityHeader"),
    tierPriceHeader: t("tier.priceHeader"),
    moqBadge: t("moq.badge"),
    moqTableLabel: t("moq.tableLabel"),
    previewLine: t("preview.line"),
  };

  return (
    <div className="flex flex-col gap-4 lg:mx-auto lg:w-full lg:max-w-3xl">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-[var(--fs-h1)] text-[var(--text)]">{t("title")}</h1>
        <p className="text-sm text-[var(--text-2)]">
          {t("results", { count: wholesaleListings.length })}
        </p>
      </header>

      <aside
        className="rounded-lg border border-border bg-bg-2 px-3 py-3 text-sm text-text-2"
        data-testid="supplies-t2-notice"
      >
        <p className="font-semibold text-text">{t("t2Notice.title")}</p>
        <p className="mt-1">{t("t2Notice.body")}</p>
      </aside>

      <form className="flex items-center gap-2" method="get">
        <label htmlFor="supplies-sort" className="text-sm text-text-2">
          {t("sort.label")}
        </label>
        <select
          id="supplies-sort"
          name="sort"
          defaultValue={sort}
          className="h-11 min-w-[10rem] rounded-md border border-border bg-surface px-3 text-sm text-text"
        >
          <option value="moq">{t("sort.moq")}</option>
          <option value="unit_price">{t("sort.unitPrice")}</option>
        </select>
        <button
          type="submit"
          className="h-11 rounded-md border border-border bg-surface px-4 text-sm font-medium text-text"
        >
          {t("sort.label")}
        </button>
      </form>

      {wholesaleListings.length === 0 ? (
        <EmptyState title={t("empty.title")} body={t("empty.body")} data-testid="supplies-empty" />
      ) : (
        <TierPriceCards
          locale={locale}
          listings={wholesaleListings}
          labels={labels}
          previewQty={previewQty}
        />
      )}
    </div>
  );
}
