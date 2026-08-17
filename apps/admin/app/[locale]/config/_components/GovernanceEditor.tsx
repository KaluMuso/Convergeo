"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { configApi, type VendorGovernanceResponse } from "./api";

function formatRate(rate: number): string {
  return `${Math.round(rate * 1000) / 10}%`;
}

export function GovernanceEditor() {
  const t = useTranslations("admin.config");
  const [data, setData] = useState<VendorGovernanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await configApi.request<VendorGovernanceResponse>(
        "/admin/governance/vendors?severity=warn",
      );
      setData(payload);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const reinstate = async (vendorId: string) => {
    setActingId(vendorId);
    setError(null);
    try {
      await configApi.request(`/admin/governance/vendors/${vendorId}/reinstate`, {
        method: "POST",
      });
      await load();
    } catch {
      setError(t("governance.reinstateError"));
    } finally {
      setActingId(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted">{t("common.loading")}</p>;
  }

  if (error && !data) {
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

  const vendors = data?.vendors ?? [];

  return (
    <div className="space-y-4" data-testid="admin-governance-editor">
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <p className="text-sm text-muted">
        {t("governance.thresholds", {
          warn: formatRate(data?.warn_threshold ?? 0.05),
          critical: formatRate(data?.critical_threshold ?? 0.1),
          minOrders: data?.min_orders ?? 10,
        })}
      </p>
      {vendors.length === 0 ? (
        <p className="text-sm text-muted">{t("governance.empty")}</p>
      ) : (
        <ul className="space-y-3">
          {vendors.map((vendor) => (
            <li
              key={vendor.vendor_id}
              className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <p className="font-medium text-text">
                  {vendor.display_name ?? vendor.slug ?? vendor.vendor_id}
                </p>
                <p className="text-xs text-muted">
                  {vendor.status} · {vendor.severity} · {formatRate(vendor.cancel_rate)} ·{" "}
                  {vendor.cancelled_orders}/{vendor.total_orders}
                </p>
              </div>
              {vendor.status === "suspended" ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
                  disabled={actingId === vendor.vendor_id}
                  onClick={() => void reinstate(vendor.vendor_id)}
                >
                  {t("governance.reinstate")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
