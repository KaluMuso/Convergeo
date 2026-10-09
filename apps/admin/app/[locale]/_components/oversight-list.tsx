"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { rolesApi } from "../../../lib/roles-api";

export function OversightList({ kind }: { kind: "services" | "inventory" }) {
  const t = useTranslations("admin.oversightUi");
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void rolesApi.request<{ items: Record<string, unknown>[] }>(`/admin/${kind}`).then(
      (result) => {
        if (active) setItems(result.items);
      },
      (cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load");
      },
    );
    return () => {
      active = false;
    };
  }, [kind]);
  return (
    <div className="space-y-3">
      <h1 className="font-serif text-xl">{t(kind)}</h1>
      <p className="text-sm text-muted">{t("subtitle")}</p>
      {error ? (
        <p role="alert">{error}</p>
      ) : items.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={String(item.id)} className="rounded border p-3 text-sm">
              <strong>{String(item.title ?? item.title_override ?? item.id)}</strong>
              <span className="block text-muted">
                {t("vendor", { vendorId: String(item.vendor_id), status: String(item.status) })}
                {kind === "inventory"
                  ? ` · ${t("stock", { quantity: String(item.stock_qty ?? "unknown") })}`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
