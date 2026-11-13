import { formatK, loadNamespace, type Locale } from "@vergeo/i18n";
import { CloudinaryImageStatic } from "@vergeo/ui/src/media/cloudinary-image-static";
import Link from "next/link";
import { createTranslator, type AbstractIntlMessages } from "next-intl";

import { absoluteApiUrl } from "../../../../../lib/api-base-url";

/** GET /directory/{vendor}/elsewhere — items from OTHER active shops. */
export type ElsewherePayload = {
  products: Array<{
    listing_id: string;
    title: string;
    product_slug: string | null;
    price_ngwee: number;
    in_stock: boolean;
    image_public_id: string | null;
    vendor_slug: string;
    vendor_name: string;
  }>;
  services: Array<{
    id: string;
    title: string;
    from_price_ngwee: number | null;
    bookable: boolean;
    booking_price_ngwee: number | null;
    image_public_id: string | null;
    vendor_slug: string;
    vendor_name: string;
  }>;
  events: Array<{
    id: string;
    slug: string;
    title: string;
    image_public_id: string | null;
    next_starts_at: string | null;
    vendor_slug: string;
    vendor_name: string;
  }>;
};

export type ElsewhereKind = "product" | "service" | "event";

export type ElsewhereCard = {
  key: string;
  kind: ElsewhereKind;
  href: string;
  title: string;
  imagePublicId: string | null;
  /** Price, "from" price, quote line or date. */
  detail: string;
  /** Stock line for products; null for services/events. */
  stock: { inStock: boolean; label: string } | null;
  shop: string;
};

type Labels = {
  atShop: (shop: string) => string;
  inStock: string;
  outOfStock: string;
  serviceFrom: (price: string) => string;
  serviceBook: (price: string) => string;
  serviceQuote: string;
  eventDate: (iso: string) => string;
};

export const ELSEWHERE_RAIL_LIMIT = 8;

/**
 * Builds the rail: the page's own kind first (a product page leads with other
 * products), then the other kinds — never the item or shop being viewed.
 */
export function buildElsewhereCards({
  locale,
  data,
  lead,
  excludeIds = [],
  labels,
}: {
  locale: string;
  data: ElsewherePayload;
  lead: ElsewhereKind;
  excludeIds?: string[];
  labels: Labels;
}): ElsewhereCard[] {
  const exclude = new Set(excludeIds);
  const products: ElsewhereCard[] = data.products
    .filter((item) => item.product_slug && !exclude.has(item.listing_id))
    .map((item) => ({
      key: `p-${item.listing_id}`,
      kind: "product",
      href: `/${locale}/p/${item.product_slug}?listing=${encodeURIComponent(item.listing_id)}`,
      title: item.title,
      imagePublicId: item.image_public_id,
      detail: formatK(item.price_ngwee),
      stock: {
        inStock: item.in_stock,
        label: item.in_stock ? labels.inStock : labels.outOfStock,
      },
      shop: labels.atShop(item.vendor_name),
    }));
  const services: ElsewhereCard[] = data.services
    .filter((item) => !exclude.has(item.id))
    .map((item) => ({
      key: `s-${item.id}`,
      kind: "service",
      href: `/${locale}/s/${encodeURIComponent(item.id)}`,
      title: item.title,
      imagePublicId: item.image_public_id,
      detail:
        item.bookable && typeof item.booking_price_ngwee === "number"
          ? labels.serviceBook(formatK(item.booking_price_ngwee))
          : item.from_price_ngwee !== null
            ? labels.serviceFrom(formatK(item.from_price_ngwee))
            : labels.serviceQuote,
      stock: null,
      shop: labels.atShop(item.vendor_name),
    }));
  const events: ElsewhereCard[] = data.events
    .filter((item) => item.slug && !exclude.has(item.id))
    .map((item) => ({
      key: `e-${item.id}`,
      kind: "event",
      href: `/${locale}/e/${encodeURIComponent(item.slug)}`,
      title: item.title,
      imagePublicId: item.image_public_id,
      detail: item.next_starts_at ? labels.eventDate(item.next_starts_at) : "",
      stock: null,
      shop: labels.atShop(item.vendor_name),
    }));
  const byKind = { product: products, service: services, event: events };
  const order: ElsewhereKind[] = [
    lead,
    ...(["product", "service", "event"] as const).filter((k) => k !== lead),
  ];
  return order.flatMap((kind) => byKind[kind]).slice(0, ELSEWHERE_RAIL_LIMIT);
}

async function fetchElsewhere(
  vendorSlug: string,
  focus: { product?: string; service?: string },
): Promise<ElsewherePayload | null> {
  const params = new URLSearchParams();
  if (focus.product) params.set("product", focus.product);
  if (focus.service) params.set("service", focus.service);
  const query = params.toString();
  const url = absoluteApiUrl(
    `/directory/${encodeURIComponent(vendorSlug)}/elsewhere${query ? `?${query}` : ""}`,
  );
  if (!url) return null;
  try {
    const response = await fetch(url, {
      next: { revalidate: 900, tags: ["directory", "elsewhere"] },
    });
    if (!response.ok) return null;
    return (await response.json()) as ElsewherePayload;
  } catch {
    return null;
  }
}

export function OtherShopsRailView({
  heading,
  cards,
  kindLabels,
  cloudName,
}: {
  heading: string;
  cards: ElsewhereCard[];
  kindLabels: Record<ElsewhereKind, string>;
  cloudName?: string;
}) {
  if (cards.length === 0) {
    return null;
  }
  return (
    <section
      aria-labelledby="other-shops-heading"
      data-testid="other-shops-rail"
      className="flex flex-col gap-3"
    >
      <h2 id="other-shops-heading" className="m-0 font-display text-h2 text-display-ink">
        {heading}
      </h2>
      <ul className="-mx-1 m-0 flex list-none gap-3 overflow-x-auto p-0 px-1 pb-1 [scrollbar-width:none]">
        {cards.map((card) => (
          <li key={card.key} className="w-40 shrink-0 sm:w-48">
            <Link
              href={card.href}
              className="card-lift block h-full overflow-hidden rounded-lg border border-border bg-surface no-underline shadow-1 focus-visible:outline-none focus-visible:shadow-focusRing"
              data-kind={card.kind}
            >
              <div className="aspect-[4/3] w-full bg-bg-2">
                {card.imagePublicId ? (
                  <CloudinaryImageStatic
                    publicId={card.imagePublicId}
                    alt={card.title}
                    width={240}
                    sizes="192px"
                    ratio="4/3"
                    cloudName={cloudName}
                    className="h-full w-full object-cover"
                  />
                ) : null}
              </div>
              <div className="space-y-0.5 p-3">
                <p className="m-0 text-xs font-semibold uppercase text-text-2">
                  {kindLabels[card.kind]}
                </p>
                <p className="m-0 truncate text-sm font-medium text-text">{card.title}</p>
                {card.detail ? (
                  <p className="m-0 text-sm font-semibold text-text">{card.detail}</p>
                ) : null}
                {card.stock ? (
                  <p
                    className={`m-0 text-xs ${card.stock.inStock ? "text-success" : "text-text-2"}`}
                  >
                    {card.stock.label}
                  </p>
                ) : null}
                <p className="m-0 truncate text-xs text-text-2">{card.shop}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * "From other shops" — under a product, service or event page (founder
 * addition #2). Server-rendered: zero client JS. Renders nothing when the API
 * has nothing, so it never shows an empty rail. Wrap in <Suspense> so it
 * streams after the main content.
 */
export async function OtherShopsRail({
  locale,
  vendorSlug,
  lead,
  focusProductSlug,
  focusServiceId,
  excludeIds,
}: {
  locale: string;
  vendorSlug: string;
  lead: ElsewhereKind;
  focusProductSlug?: string;
  focusServiceId?: string;
  excludeIds?: string[];
}) {
  const [data, messages] = await Promise.all([
    fetchElsewhere(vendorSlug, { product: focusProductSlug, service: focusServiceId }),
    loadNamespace(locale as Locale, "directory"),
  ]);
  if (!data) {
    return null;
  }
  const t = createTranslator({
    locale,
    messages: { directory: messages } as AbstractIntlMessages,
    namespace: "directory",
  }) as unknown as (key: string, values?: Record<string, string | number>) => string;
  const kindLabels: Record<ElsewhereKind, string> = {
    product: t("elsewhere.kindProduct"),
    service: t("elsewhere.kindService"),
    event: t("elsewhere.kindEvent"),
  };
  const dateFormat = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Africa/Lusaka",
  });
  const cards = buildElsewhereCards({
    locale,
    data,
    lead,
    excludeIds,
    labels: {
      atShop: (shop) => t("elsewhere.atShop", { shop }),
      inStock: t("elsewhere.inStock"),
      outOfStock: t("elsewhere.outOfStock"),
      serviceFrom: (price) => t("profile.serviceFrom", { price }),
      serviceBook: (price) => t("profile.home.serviceBook", { price }),
      serviceQuote: t("profile.home.serviceQuote"),
      eventDate: (iso) => dateFormat.format(new Date(iso)),
    },
  });
  return (
    <OtherShopsRailView
      heading={t("elsewhere.heading")}
      cards={cards}
      kindLabels={kindLabels}
      cloudName={process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME}
    />
  );
}
