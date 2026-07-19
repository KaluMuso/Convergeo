"use client";

import { useSession } from "@vergeo/auth/use-session";
import { createApiClient } from "@vergeo/config";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { Spinner } from "../../listings/new/_lib/ui";

type DisputeSummary = {
  id: string;
  order_id: string;
  status: string;
  created_at: string;
};

function statusLabel(status: string, t: (key: string) => string): string {
  const key = `disputes.detail.status.${status}`;
  try {
    return t(key);
  } catch {
    return status;
  }
}

export function VendorDisputesListView() {
  const t = useTranslations("vendor");
  const { session } = useSession();
  const [disputes, setDisputes] = useState<DisputeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const client = useMemo(
    () =>
      createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => session?.access_token ?? null,
      }),
    [session?.access_token],
  );

  const load = useCallback(async () => {
    if (!session?.access_token) {
      return;
    }
    setLoading(true);
    setError(undefined);
    try {
      const rows = await client.request<DisputeSummary[]>("/disputes/vendor/mine");
      setDisputes(rows);
    } catch {
      setError(t("disputes.detail.error"));
    } finally {
      setLoading(false);
    }
  }, [client, session?.access_token, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-40 items-center justify-center">
        <Spinner label={t("disputes.list.title")} />
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <header>
        <h1 className="font-display text-h2 text-display-ink">{t("disputes.list.title")}</h1>
      </header>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {disputes.length === 0 ? (
        <p className="text-sm text-text-2">{t("disputes.list.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {disputes.map((dispute) => (
            <li key={dispute.id}>
              <Link
                href={`disputes/${dispute.id}`}
                className="flex min-h-11 flex-col justify-center rounded border border-border bg-surface px-4 py-3"
              >
                <span className="text-sm font-medium text-display-ink">
                  {t("disputes.list.order", {
                    orderId: dispute.order_id.slice(0, 8).toUpperCase(),
                  })}
                </span>
                <span className="text-xs text-text-2">
                  {t("disputes.list.status", {
                    status: statusLabel(dispute.status, t),
                  })}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
