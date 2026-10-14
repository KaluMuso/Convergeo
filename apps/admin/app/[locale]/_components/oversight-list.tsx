"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { rolesApi, useAdminPermissions } from "../../../lib/roles-api";

type Kind = "services" | "inventory";
type Snapshot = {
  kind: Kind;
  items: Record<string, unknown>[] | null;
  error: boolean;
};

export function OversightList({ kind }: { kind: Kind }) {
  const t = useTranslations("admin.oversightUi");
  const grants = useAdminPermissions();
  const allowed = !!grants && (grants.unrestricted || grants.permissions.includes(`${kind}.read`));
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setSnapshot(null);
    if (!allowed) return;
    let active = true;
    void rolesApi
      .request<{ items: Record<string, unknown>[] }>(`/admin/${kind}`, {
        cache: "no-store",
      })
      .then(
        (result) => {
          if (active)
            setSnapshot({
              kind,
              items: Array.isArray(result?.items) ? result.items : null,
              error: !Array.isArray(result?.items),
            });
        },
        () => {
          if (active) setSnapshot({ kind, items: null, error: true });
        },
      );
    return () => {
      active = false;
    };
  }, [kind, allowed, attempt]);

  const current = snapshot?.kind === kind ? snapshot : null;
  return (
    <div className="space-y-3">
      <h1 className="font-serif text-xl">{t(kind)}</h1>
      <p className="text-sm text-muted">{t("subtitle")}</p>
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
        <p>{t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {current.items.map((item) => (
            <li key={String(item.id)} className="rounded border p-3 text-sm">
              <strong>{String(item.title ?? item.title_override ?? item.id)}</strong>
              <span className="block text-muted">
                {t("vendor", {
                  vendorId: String(item.vendor_id),
                  status: String(item.status),
                })}
                {kind === "inventory"
                  ? ` · ${t("stock", { quantity: String(item.stock_qty ?? t("unknownStock")) })}`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
