"use client";

import { formatK } from "@vergeo/i18n";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";

type Kind = "services" | "inventory";
type Snapshot = {
  kind: Kind;
  items: Record<string, unknown>[] | null;
  total: number | null;
  nextOffset: number | null;
  error: boolean;
};
type OversightPage = {
  items: Record<string, unknown>[];
  total?: number | null;
  next_offset?: number | null;
};

export const OVERSIGHT_PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

export function oversightPath(kind: Kind, search: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(OVERSIGHT_PAGE_SIZE) });
  const term = search.trim();
  if (term) params.set("q", term);
  if (offset > 0) params.set("offset", String(offset));
  return `/admin/${kind}?${params.toString()}`;
}

function itemTitle(item: Record<string, unknown>): string | null {
  for (const value of [item.display_title, item.title, item.title_override]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

export function OversightList({ kind }: { kind: Kind }) {
  const t = useTranslations("admin.oversightUi");
  const grants = useAdminPermissions();
  const allowed =
    !!grants &&
    (grants.unrestricted ||
      grants.permissions.includes(`${kind}.read`) ||
      (kind === "services" && grants.permissions.includes("services.manage")));
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setSnapshot(null);
    if (!allowed) return;
    let active = true;
    const current = ++generation.current;
    void rolesApi
      .request<OversightPage>(oversightPath(kind, appliedSearch, 0), { cache: "no-store" })
      .then(
        (result) => {
          if (active && current === generation.current)
            setSnapshot({
              kind,
              items: Array.isArray(result?.items) ? result.items : null,
              total: typeof result?.total === "number" ? result.total : null,
              nextOffset: typeof result?.next_offset === "number" ? result.next_offset : null,
              error: !Array.isArray(result?.items),
            });
        },
        () => {
          if (active && current === generation.current)
            setSnapshot({ kind, items: null, total: null, nextOffset: null, error: true });
        },
      );
    return () => {
      active = false;
    };
  }, [kind, allowed, attempt, appliedSearch]);

  async function loadMore(from: Snapshot) {
    if (from.nextOffset === null || !from.items) return;
    const current = generation.current;
    setLoadingMore(true);
    try {
      const result = await rolesApi.request<OversightPage>(
        oversightPath(kind, appliedSearch, from.nextOffset),
        { cache: "no-store" },
      );
      if (current !== generation.current || !Array.isArray(result?.items)) return;
      setSnapshot({
        ...from,
        items: [...(from.items ?? []), ...result.items],
        total: typeof result.total === "number" ? result.total : from.total,
        nextOffset: typeof result.next_offset === "number" ? result.next_offset : null,
      });
    } catch {
      // Keep the rows already shown; the button stays for another try.
    } finally {
      setLoadingMore(false);
    }
  }

  const current = snapshot?.kind === kind ? snapshot : null;
  return (
    <div className="space-y-3">
      <h1 className="font-serif text-xl">{t(kind)}</h1>
      <p className="text-sm text-muted">{t("subtitle")}</p>
      {allowed ? (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="block w-full max-w-md text-sm">
            {t("search")}
            <input
              type="search"
              value={search}
              placeholder={t(kind === "services" ? "searchServices" : "searchInventory")}
              onChange={(event) => setSearch(event.target.value)}
              className="min-h-11 w-full rounded-md border border-border bg-surface p-2"
              data-testid="oversight-search"
            />
          </label>
          {current?.items && current.total !== null ? (
            <p className="text-sm text-muted" data-testid="oversight-count">
              {t("showing", { shown: current.items.length, total: current.total })}
            </p>
          ) : null}
        </div>
      ) : null}
      {!allowed ? (
        <p role="alert">{t("permissionDenied")}</p>
      ) : current?.error ? (
        <div>
          <p role="alert">{t("loadFailed")}</p>
          <button className="min-h-11 underline" onClick={() => setAttempt((value) => value + 1)}>
            {t("retry")}
          </button>
        </div>
      ) : !current?.items ? (
        <p role="status">{t("loading")}</p>
      ) : current.items.length === 0 ? (
        <p>{appliedSearch.trim() ? t("noMatches") : t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {current.items.map((item) => (
            <li
              key={String(item.id)}
              className="rounded-lg border border-border bg-surface p-3 text-sm"
            >
              <strong>{itemTitle(item) ?? t("untitled")}</strong>
              <span className="block text-muted">
                {t("vendor", {
                  vendorName:
                    typeof item.vendor_display_name === "string"
                      ? item.vendor_display_name
                      : t("unknownVendor"),
                  status: String(item.status),
                })}
                {kind === "inventory" && typeof item.price_ngwee === "number"
                  ? ` · ${t("price", { price: formatK(item.price_ngwee) })}`
                  : null}
                {kind === "inventory" && typeof item.product_name === "string"
                  ? ` · ${t("product", { name: item.product_name })}`
                  : null}
                {kind === "inventory"
                  ? ` · ${t("stock", { quantity: String(item.stock_qty ?? t("unknownStock")) })}`
                  : ""}
              </span>
              {kind === "services" ? <PackageLines raw={item.packages} t={t} /> : null}
            </li>
          ))}
        </ul>
      )}
      {current?.items && current.nextOffset !== null ? (
        <button
          type="button"
          className="min-h-11 rounded-md border border-border px-4 text-sm font-medium"
          disabled={loadingMore}
          onClick={() => void loadMore(current)}
        >
          {loadingMore ? t("loading") : t("more")}
        </button>
      ) : null}
    </div>
  );
}

type ServicePackageRow = {
  id: string;
  tier: string;
  name: string;
  price_ngwee: number | null;
  delivery_days: number | null;
  status: string;
};

/** Service packages (docs/plan/service-packages.md) — read-only, every status. */
function PackageLines({
  raw,
  t,
}: {
  raw: unknown;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const rows = Array.isArray(raw) ? (raw as ServicePackageRow[]) : [];
  return (
    <span className="mt-1 block text-xs text-muted" data-testid="oversight-service-packages">
      {t("packages", { count: rows.length })}
      {rows.map((row) => (
        <span key={row.id} className="block">
          {t("packageLine", {
            tier: row.tier,
            name: row.name,
            price:
              typeof row.price_ngwee === "number" && Number.isInteger(row.price_ngwee)
                ? formatK(row.price_ngwee)
                : t("packagePriceQuote"),
            days: row.delivery_days ?? 0,
            status: row.status,
          })}
        </span>
      ))}
    </span>
  );
}
