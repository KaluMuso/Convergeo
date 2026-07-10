"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Button } from "../../listings/new/_lib/ui";

type VendorReturnItem = {
  id: string;
  order_id: string;
  order_item_id: string;
  lane: number;
  status: string;
  fee_breakdown: {
    item_ngwee?: number;
    delivery_ngwee?: number;
    total_ngwee?: number;
  };
  evidence_count: number;
  item_title: string;
  item_qty: number;
  created_at: string | null;
};

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export function VendorReturnsQueue({ locale }: { locale: string }) {
  const t = useTranslations("vendor.returns");
  const { session } = useSession();
  const [items, setItems] = useState<VendorReturnItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [actingId, setActingId] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    const token = session?.access_token;
    if (!token) {
      setLoading(false);
      return;
    }
    setError(undefined);
    try {
      const client = createApiClient({
        baseUrl: getApiBaseUrl(),
        getToken: () => token,
      });
      const rows = await client.request<VendorReturnItem[]>("/returns/vendor");
      setItems(rows);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(t("errors.loadFailed"));
      } else {
        setError(t("errors.loadFailed"));
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, t]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const respond = useCallback(
    async (returnId: string, action: "accept" | "contest") => {
      const token = session?.access_token;
      if (!token || actingId) {
        return;
      }
      setActingId(returnId);
      setError(undefined);
      try {
        const client = createApiClient({
          baseUrl: getApiBaseUrl(),
          getToken: () => token,
        });
        await client.request(`/returns/${returnId}/respond`, {
          method: "POST",
          body: JSON.stringify({ action }),
        });
        setItems((current) => current.filter((row) => row.id !== returnId));
      } catch {
        setError(t("errors.actionFailed"));
      } finally {
        setActingId(null);
      }
    },
    [actingId, session?.access_token, t],
  );

  if (loading) {
    return <p className="text-sm text-text-2">{t("loading")}</p>;
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? (
        <p className="text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {items.length === 0 ? (
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id} className="space-y-3 rounded border border-border bg-surface p-4">
              <div className="space-y-1">
                <p className="font-medium text-display-ink">
                  {t("card.item", { title: item.item_title, qty: item.item_qty })}
                </p>
                <p className="text-xs text-text-2">
                  {t("card.order", { id: item.order_id.slice(0, 8).toUpperCase() })}
                </p>
                <p className="font-mono text-sm text-display-ink">
                  {t("card.refund", {
                    amount: formatK(item.fee_breakdown.total_ngwee ?? 0),
                  })}
                </p>
                <p className="text-xs text-text-2">
                  {t("card.evidence", { count: item.evidence_count })}
                </p>
              </div>
              <div className="grid grid-cols-1 gap-2">
                <Button
                  className="min-h-11 w-full"
                  disabled={actingId === item.id}
                  loading={actingId === item.id}
                  loadingLabel={t("actions.accepting")}
                  onClick={() => void respond(item.id, "accept")}
                >
                  {t("actions.accept")}
                </Button>
                <Button
                  variant="secondary"
                  className="min-h-11 w-full"
                  disabled={actingId === item.id}
                  loading={false}
                  loadingLabel={t("actions.contesting")}
                  onClick={() => void respond(item.id, "contest")}
                >
                  {t("actions.contest")}
                </Button>
              </div>
              <Link
                href={`/${locale}/orders/${item.order_id}`}
                className="inline-flex min-h-11 items-center text-sm font-medium text-primary"
              >
                {t("card.viewOrder")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
