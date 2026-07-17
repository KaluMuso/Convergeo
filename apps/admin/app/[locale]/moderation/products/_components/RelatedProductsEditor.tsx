"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import {
  getProductRelations,
  type ProductRelationItem,
  type ProductSummary,
  searchProducts,
  setProductRelations,
} from "./api";

const MAX_RELATED = 12;

type RelatedRow = {
  related_product_id: string;
  name: string;
  slug: string;
};

function toRow(item: ProductRelationItem | ProductSummary): RelatedRow {
  const id = "related_product_id" in item ? item.related_product_id : item.id;
  return { related_product_id: id, name: item.name, slug: item.slug };
}

export function RelatedProductsEditor() {
  const t = useTranslations("admin.moderation.related");

  const [anchor, setAnchor] = useState<ProductSummary | null>(null);
  const [anchorQuery, setAnchorQuery] = useState("");
  const [anchorResults, setAnchorResults] = useState<ProductSummary[] | null>(null);
  const [anchorSearching, setAnchorSearching] = useState(false);

  const [related, setRelated] = useState<RelatedRow[]>([]);
  const [loadingRelated, setLoadingRelated] = useState(false);

  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState<ProductSummary[] | null>(null);
  const [addSearching, setAddSearching] = useState(false);

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAnchorSearch = useCallback(async () => {
    const query = anchorQuery.trim();
    if (!query) return;
    setAnchorSearching(true);
    setError(null);
    try {
      setAnchorResults(await searchProducts(query));
    } catch {
      setError(t("searchError"));
    } finally {
      setAnchorSearching(false);
    }
  }, [anchorQuery, t]);

  const selectAnchor = useCallback(
    async (product: ProductSummary) => {
      setAnchor(product);
      setAnchorResults(null);
      setAnchorQuery("");
      setAddResults(null);
      setAddQuery("");
      setMessage(null);
      setError(null);
      setLoadingRelated(true);
      try {
        const response = await getProductRelations(product.id);
        setRelated(response.related.map(toRow));
      } catch {
        setError(t("loadError"));
        setRelated([]);
      } finally {
        setLoadingRelated(false);
      }
    },
    [t],
  );

  const clearAnchor = () => {
    setAnchor(null);
    setRelated([]);
    setAddResults(null);
    setAddQuery("");
    setMessage(null);
    setError(null);
  };

  const runAddSearch = useCallback(async () => {
    const query = addQuery.trim();
    if (!query) return;
    setAddSearching(true);
    setError(null);
    try {
      setAddResults(await searchProducts(query));
    } catch {
      setError(t("searchError"));
    } finally {
      setAddSearching(false);
    }
  }, [addQuery, t]);

  const addRelated = (product: ProductSummary) => {
    setMessage(null);
    setRelated((current) => {
      if (
        current.length >= MAX_RELATED ||
        product.id === anchor?.id ||
        current.some((row) => row.related_product_id === product.id)
      ) {
        return current;
      }
      return [...current, toRow(product)];
    });
  };

  const removeRelated = (id: string) => {
    setMessage(null);
    setRelated((current) => current.filter((row) => row.related_product_id !== id));
  };

  const move = (index: number, delta: number) => {
    setMessage(null);
    setRelated((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      const moved = next[index];
      const displaced = next[target];
      if (!moved || !displaced) return current;
      next[index] = displaced;
      next[target] = moved;
      return next;
    });
  };

  const save = useCallback(async () => {
    if (!anchor) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await setProductRelations(
        anchor.id,
        related.map((row) => row.related_product_id),
      );
      setRelated(response.related.map(toRow));
      setMessage(t("saved"));
    } catch {
      setError(t("saveError"));
    } finally {
      setSaving(false);
    }
  }, [anchor, related, t]);

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-text">{t("title")}</h2>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {anchor ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-4">
            <div className="min-w-0">
              <p className="truncate font-medium text-text">{anchor.name}</p>
              <p className="truncate text-xs text-muted">{anchor.slug}</p>
            </div>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
              onClick={clearAnchor}
            >
              {t("changeAnchor")}
            </button>
          </div>

          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted">
              {t("currentTitle", { count: related.length, max: MAX_RELATED })}
            </p>
            {loadingRelated ? (
              <p className="text-sm text-muted">{t("loading")}</p>
            ) : related.length === 0 ? (
              <p className="text-sm text-muted">{t("empty")}</p>
            ) : (
              <ol className="space-y-2">
                {related.map((row, index) => (
                  <li
                    key={row.related_product_id}
                    className="flex items-center gap-2 rounded-md border border-border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-text">{row.name}</p>
                      <p className="truncate text-xs text-muted">{row.slug}</p>
                    </div>
                    <button
                      type="button"
                      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-sm disabled:opacity-40"
                      onClick={() => move(index, -1)}
                      disabled={index === 0}
                      aria-label={t("moveUp")}
                    >
                      <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4">
                        <path d="M4 10l4-4 4 4" fill="none" stroke="currentColor" strokeWidth="2" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-sm disabled:opacity-40"
                      onClick={() => move(index, 1)}
                      disabled={index === related.length - 1}
                      aria-label={t("moveDown")}
                    >
                      <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4">
                        <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="2" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-danger px-3 text-sm text-danger"
                      onClick={() => removeRelated(row.related_product_id)}
                    >
                      {t("remove")}
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {related.length >= MAX_RELATED ? (
              <p className="text-xs text-muted">{t("maxReached", { max: MAX_RELATED })}</p>
            ) : null}
          </div>

          <div className="space-y-2 rounded-lg border border-border p-4">
            <p className="text-xs uppercase tracking-wide text-muted">{t("addTitle")}</p>
            <div className="flex gap-2">
              <input
                type="search"
                className="min-h-11 flex-1 rounded-md border border-border px-3 text-sm"
                value={addQuery}
                placeholder={t("searchPlaceholder")}
                onChange={(event) => setAddQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void runAddSearch();
                }}
              />
              <button
                type="button"
                className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                onClick={() => void runAddSearch()}
                disabled={addSearching || addQuery.trim().length === 0}
              >
                {addSearching ? t("searching") : t("searchAction")}
              </button>
            </div>
            {addResults ? (
              addResults.length === 0 ? (
                <p className="text-sm text-muted">{t("noResults")}</p>
              ) : (
                <ul className="space-y-2">
                  {addResults.map((product) => {
                    const isAnchor = product.id === anchor.id;
                    const isAdded = related.some((row) => row.related_product_id === product.id);
                    const isActive = product.status === "active";
                    const disabled =
                      isAnchor || isAdded || !isActive || related.length >= MAX_RELATED;
                    let hint: string | null = null;
                    if (isAnchor) hint = t("isAnchor");
                    else if (isAdded) hint = t("alreadyAdded");
                    else if (!isActive) hint = t("notActive");
                    return (
                      <li
                        key={product.id}
                        className="flex items-center gap-2 rounded-md border border-border p-3"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-text">{product.name}</p>
                          <p className="truncate text-xs text-muted">{product.slug}</p>
                          {hint ? <p className="truncate text-xs text-muted">{hint}</p> : null}
                        </div>
                        <button
                          type="button"
                          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm disabled:opacity-40"
                          onClick={() => addRelated(product)}
                          disabled={disabled}
                        >
                          {t("add")}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-5 text-sm text-white disabled:opacity-40"
              onClick={() => void save()}
              disabled={saving || loadingRelated}
            >
              {saving ? t("saving") : t("save")}
            </button>
            {message ? <p className="text-sm text-primary">{message}</p> : null}
          </div>
        </div>
      ) : (
        <div className="space-y-2 rounded-lg border border-border p-4">
          <p className="text-xs uppercase tracking-wide text-muted">{t("anchorTitle")}</p>
          <div className="flex gap-2">
            <input
              type="search"
              className="min-h-11 flex-1 rounded-md border border-border px-3 text-sm"
              value={anchorQuery}
              placeholder={t("searchPlaceholder")}
              onChange={(event) => setAnchorQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void runAnchorSearch();
              }}
            />
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
              onClick={() => void runAnchorSearch()}
              disabled={anchorSearching || anchorQuery.trim().length === 0}
            >
              {anchorSearching ? t("searching") : t("searchAction")}
            </button>
          </div>
          {anchorResults ? (
            anchorResults.length === 0 ? (
              <p className="text-sm text-muted">{t("noResults")}</p>
            ) : (
              <ul className="space-y-2">
                {anchorResults.map((product) => (
                  <li
                    key={product.id}
                    className="flex items-center gap-2 rounded-md border border-border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-text">{product.name}</p>
                      <p className="truncate text-xs text-muted">{product.slug}</p>
                    </div>
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                      onClick={() => void selectAnchor(product)}
                    >
                      {t("pick")}
                    </button>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      )}
    </section>
  );
}
