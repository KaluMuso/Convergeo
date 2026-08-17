"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type CategoryPolicy } from "./api";

const CLASSES = ["A", "B", "C", "D", "E"] as const;

export function CategoryPolicyEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<CategoryPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<CategoryPolicy[]>("/admin/config/category-policies");
      setRows(data);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (row: CategoryPolicy) => {
    setSavingId(row.category_id);
    setError(null);
    try {
      const updated = await configApi.request<CategoryPolicy>(
        `/admin/config/category-policies/${row.category_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            enabled: row.enabled,
            phase: row.phase,
            high_risk: row.high_risk,
            allowed_product_classes: row.allowed_product_classes,
          }),
        },
      );
      setRows((current) =>
        current.map((item) => (item.category_id === updated.category_id ? updated : item)),
      );
    } catch {
      setError(t("categoryPolicies.saveError"));
    } finally {
      setSavingId(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  if (error && rows.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-danger">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="admin-category-policy-editor">
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {rows.map((row) => (
        <article key={row.category_id} className="space-y-3 rounded-md border border-border p-3">
          <div>
            <p className="font-medium text-text">{row.category_name}</p>
            <p className="font-mono text-xs text-muted">{row.path}</p>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="inline-flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                checked={row.enabled}
                onChange={(event) =>
                  setRows((current) =>
                    current.map((item) =>
                      item.category_id === row.category_id
                        ? { ...item, enabled: event.target.checked }
                        : item,
                    ),
                  )
                }
              />
              {row.enabled ? t("common.enabled") : t("common.disabled")}
            </label>
            <label className="inline-flex min-h-11 items-center gap-2">
              {t("categoryPolicies.phase")}
              <select
                className="rounded-md border border-border bg-bg px-2 py-1"
                value={row.phase}
                onChange={(event) =>
                  setRows((current) =>
                    current.map((item) =>
                      item.category_id === row.category_id
                        ? { ...item, phase: Number(event.target.value) }
                        : item,
                    ),
                  )
                }
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
                <option value={3}>3</option>
              </select>
            </label>
            <label className="inline-flex min-h-11 items-center gap-2">
              <input
                type="checkbox"
                checked={row.high_risk}
                onChange={(event) =>
                  setRows((current) =>
                    current.map((item) =>
                      item.category_id === row.category_id
                        ? { ...item, high_risk: event.target.checked }
                        : item,
                    ),
                  )
                }
              />
              {t("categoryPolicies.highRisk")}
            </label>
          </div>
          <fieldset className="flex flex-wrap gap-3 text-sm">
            <legend className="sr-only">{t("categoryPolicies.classes")}</legend>
            {CLASSES.map((productClass) => (
              <label key={productClass} className="inline-flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={row.allowed_product_classes.includes(productClass)}
                  onChange={(event) =>
                    setRows((current) =>
                      current.map((item) => {
                        if (item.category_id !== row.category_id) {
                          return item;
                        }
                        const next = event.target.checked
                          ? [...item.allowed_product_classes, productClass]
                          : item.allowed_product_classes.filter((value) => value !== productClass);
                        return { ...item, allowed_product_classes: next };
                      }),
                    )
                  }
                />
                {productClass}
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
            disabled={savingId === row.category_id}
            onClick={() => void save(row)}
          >
            {t("common.save")}
          </button>
        </article>
      ))}
    </div>
  );
}
