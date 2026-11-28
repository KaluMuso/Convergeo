"use client";

import { Button } from "@vergeo/ui/src/button";
import { glassClass } from "@vergeo/ui/src/glass";
import { Input } from "@vergeo/ui/src/input";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { VendorPageSkeleton } from "../../_components/page-skeleton";
import {
  SOURCE_TABS,
  TAB_LABEL_KEY,
  buildPageQuery,
  buildSearchPath,
  categoryEnabled,
  parseTab,
  type SourceTab,
  type SourcingItem,
  type SourcingSearchResponse,
} from "../_lib/source";
import { useSourceApi } from "../_lib/use-source-api";

import { ImportPanel } from "./import-panel";
import { SourceCard } from "./source-card";

type Category = { id: string; name: string; parent_id: string | null };

/**
 * Sourcing hub: Zambian suppliers, Made in Zambia, Import and business services.
 * Tab, search and category live in the URL so a view can be shared and reloaded.
 * Read-only discovery plus a data-only import request form: no payments here.
 */
export function SourceHub() {
  const t = useTranslations("vendor.source");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = parseTab(params.get("tab"));
  const urlQuery = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const { client, ready } = useSourceApi();

  const [draft, setDraft] = useState(urlQuery);
  const [items, setItems] = useState<SourcingItem[] | null>(null);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);

  const go = useCallback(
    (next: { tab?: SourceTab; q?: string; category?: string }) => {
      const state = {
        tab: next.tab ?? tab,
        q: next.q ?? urlQuery,
        category: next.category ?? category,
      };
      router.replace(`${pathname}${buildPageQuery(state)}`, { scroll: false });
    },
    [router, pathname, tab, urlQuery, category],
  );

  useEffect(() => setDraft(urlQuery), [urlQuery]);

  useEffect(() => {
    if (!ready || !categoryEnabled(tab) || categories.length > 0) return;
    client
      .request<Category[]>("/categories")
      .then((rows) => setCategories(rows.filter((row) => row.parent_id === null)))
      .catch(() => undefined);
  }, [client, ready, tab, categories.length]);

  useEffect(() => {
    if (!ready || tab === "import") return;
    let cancelled = false;
    setItems(null);
    setFailed(false);
    client
      .request<SourcingSearchResponse>(buildSearchPath({ tab, q: urlQuery, category }, 0))
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setNextOffset(data.next_offset);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [client, ready, tab, urlQuery, category]);

  async function loadMore() {
    if (nextOffset === null) return;
    try {
      const data = await client.request<SourcingSearchResponse>(
        buildSearchPath({ tab, q: urlQuery, category }, nextOffset),
      );
      setItems((current) => [...(current ?? []), ...data.items]);
      setNextOffset(data.next_offset);
    } catch {
      setFailed(true);
    }
  }

  return (
    <div className="space-y-4">
      <div className={`${glassClass("bar")} sticky top-0 z-10 -mx-1 px-1 py-2`}>
        <div role="tablist" aria-label={t("tabsLabel")} className="flex gap-2 overflow-x-auto">
          {SOURCE_TABS.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => go({ tab: key, category: "" })}
              className={`h-11 min-h-11 shrink-0 rounded-full px-4 text-sm font-medium ${
                tab === key
                  ? "bg-primary text-[var(--primary-btn-fg)]"
                  : "border border-border bg-surface text-text"
              }`}
            >
              {t(TAB_LABEL_KEY[key])}
            </button>
          ))}
        </div>
      </div>

      {tab === "import" ? (
        <ImportPanel />
      ) : (
        <>
          <form
            role="search"
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              go({ q: draft });
            }}
          >
            <label className="sr-only" htmlFor="source-search">
              {t("searchLabel")}
            </label>
            <Input
              id="source-search"
              type="search"
              value={draft}
              maxLength={80}
              placeholder={t("searchPlaceholder")}
              onChange={(event) => setDraft(event.target.value)}
              className="sm:flex-1"
            />
            {categoryEnabled(tab) ? (
              <>
                <label className="sr-only" htmlFor="source-category">
                  {t("categoryLabel")}
                </label>
                <select
                  id="source-category"
                  value={category}
                  onChange={(event) => go({ category: event.target.value })}
                  className="h-11 min-h-11 rounded-md border border-border bg-surface px-3 text-body text-text"
                >
                  <option value="">{t("categoryAll")}</option>
                  {categories.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
            <Button type="submit" loadingLabel={t("loading")}>
              {t("searchLabel")}
            </Button>
          </form>

          {failed ? (
            <p role="alert" className="text-sm text-text-2">
              {t("errors.load")}
            </p>
          ) : items === null ? (
            <VendorPageSkeleton rows={3} label={t("loading")} />
          ) : items.length === 0 ? (
            <p className="text-sm text-text-2">{t("empty")}</p>
          ) : (
            <ul
              className="m-0 grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 xl:grid-cols-3"
              data-testid="source-results"
            >
              {items.map((item) => (
                <SourceCard key={`${item.kind}-${item.id}`} item={item} />
              ))}
            </ul>
          )}
          {nextOffset !== null && !failed ? (
            <Button
              type="button"
              variant="secondary"
              loadingLabel={t("loading")}
              onClick={() => void loadMore()}
            >
              {t("loadMore")}
            </Button>
          ) : null}
        </>
      )}
      <p>
        <Link href={`/${locale}/source/profile`} className="text-sm text-primary underline">
          {t("profile.manage")}
        </Link>
      </p>
    </div>
  );
}
