import Link from "next/link";

export const BROWSE_PAGE_SIZE = 24;

type BrowsePagerProps = {
  locale: string;
  pathname: string;
  searchParams: Record<string, string | undefined>;
  page: number;
  total: number;
  pageSize?: number;
  labels: { previous: string; next: string; page: string };
};

function buildHref(
  locale: string,
  pathname: string,
  searchParams: Record<string, string | undefined>,
  page: number,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (value && key !== "page") params.set(key, value);
  }
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return `/${locale}${pathname}${query ? `?${query}` : ""}`;
}

export function BrowsePager({
  locale,
  pathname,
  searchParams,
  page,
  total,
  pageSize = BROWSE_PAGE_SIZE,
  labels,
}: BrowsePagerProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;
  const prevHref = page > 1 ? buildHref(locale, pathname, searchParams, page - 1) : null;
  const nextHref = page < totalPages ? buildHref(locale, pathname, searchParams, page + 1) : null;
  return (
    <nav
      className="flex flex-wrap items-center justify-center gap-3 pt-2"
      data-testid="browse-pager"
    >
      {prevHref ? (
        <Link
          href={prevHref}
          className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-primary hover:bg-primary-tint"
        >
          {labels.previous}
        </Link>
      ) : null}
      <p className="text-sm text-text-2">
        {labels.page.replace("{page}", String(page)).replace("{total}", String(totalPages))}
      </p>
      {nextHref ? (
        <Link
          href={nextHref}
          className="inline-flex min-h-11 items-center rounded-lg border border-border bg-surface px-4 text-sm font-semibold text-primary hover:bg-primary-tint"
        >
          {labels.next}
        </Link>
      ) : null}
    </nav>
  );
}

export function sliceBrowsePage<T>(items: T[], page: number, pageSize = BROWSE_PAGE_SIZE): T[] {
  return items.slice((Math.max(1, page) - 1) * pageSize, Math.max(1, page) * pageSize);
}

export function parseBrowsePage(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number.parseInt(raw ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}
