"use client";

import { useSession } from "@vergeo/auth/use-session";
import { ApiError, createApiClient } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { StatusChip } from "@vergeo/ui/src/status-chip";
import { notify } from "@vergeo/ui/src/toast";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "../../../../lib/api-base-url";
import { ListSkeleton } from "../../_components/vendor-skeletons";
import { formatOrderCode } from "../../_lib/order-code";
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

type PendingAction = { returnId: string; action: "accept" | "contest"; item: VendorReturnItem };

export function VendorReturnsQueue({ locale }: { locale: string }) {
  const t = useTranslations("vendor.returns");
  const { session } = useSession();
  const [items, setItems] = useState<VendorReturnItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [actingId, setActingId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);

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
    async (returnId: string, action: "accept" | "contest", item: VendorReturnItem) => {
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
        notify.success(
          action === "accept"
            ? t("toast.accepted", { amount: formatK(item.fee_breakdown.total_ngwee ?? 0) })
            : t("toast.contested"),
        );
      } catch {
        setError(t("errors.actionFailed"));
      } finally {
        setActingId(null);
        setPending(null);
      }
    },
    [actingId, session?.access_token, t],
  );

  const laneReason = useCallback(
    (lane: number) => {
      if (lane === 1) {
        return t("card.reasonLane1");
      }
      if (lane === 2) {
        return t("card.reasonLane2");
      }
      return t("card.reasonGeneric");
    },
    [t],
  );

  if (loading) {
    return <ListSkeleton label={t("loading")} rows={2} />;
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="font-display text-h2 text-display-ink">{t("title")}</h1>
        <p className="text-sm text-text-2">{t("intro")}</p>
      </header>

      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}

      {items.length === 0 ? (
        <p className="text-sm text-text-2">{t("empty")}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id} className="space-y-3 rounded border border-border bg-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip tone="info" label={t("card.status", { status: item.status })} />
                <StatusChip tone="neutral" label={t("card.lane", { lane: item.lane })} />
              </div>
              <div className="space-y-1">
                <p className="font-medium text-display-ink">
                  {t("card.item", { title: item.item_title, qty: item.item_qty })}
                </p>
                <p className="text-sm text-text-2">
                  {t("card.order", { id: formatOrderCode(item.order_id) })}
                </p>
                <p className="text-sm text-text-2">{laneReason(item.lane)}</p>
                <p className="font-mono text-sm text-display-ink">
                  {t("card.refund", {
                    amount: formatK(item.fee_breakdown.total_ngwee ?? 0),
                  })}
                </p>
                {item.evidence_count > 0 ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-sm text-text-2">
                      {t("card.evidence", { count: item.evidence_count })}
                    </p>
                    <div className="flex flex-wrap gap-2" aria-hidden>
                      {Array.from({ length: Math.min(item.evidence_count, 4) }, (_, index) => (
                        <span
                          key={index}
                          className="inline-flex size-14 items-center justify-center rounded-md border border-border bg-bg-2 text-xs text-text-3"
                        >
                          {t("card.evidenceThumb", { n: index + 1 })}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-text-3">{t("card.noEvidence")}</p>
                )}
              </div>
              <div className="grid grid-cols-1 gap-2">
                <Button
                  className="min-h-11 w-full"
                  disabled={actingId === item.id}
                  loading={actingId === item.id && pending?.action === "accept"}
                  loadingLabel={t("actions.accepting")}
                  onClick={() => setPending({ returnId: item.id, action: "accept", item })}
                >
                  {t("actions.accept")}
                </Button>
                <Button
                  variant="secondary"
                  className="min-h-11 w-full"
                  disabled={actingId === item.id}
                  loading={actingId === item.id && pending?.action === "contest"}
                  loadingLabel={t("actions.contesting")}
                  onClick={() => setPending({ returnId: item.id, action: "contest", item })}
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

      {pending ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4"
          role="presentation"
          onClick={() => {
            if (!actingId) {
              setPending(null);
            }
          }}
        >
          <div
            className="w-full max-w-[360px] rounded-t-2xl bg-surface p-4 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="returns-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="returns-confirm-title" className="text-base font-semibold text-text">
              {pending.action === "accept" ? t("confirm.acceptTitle") : t("confirm.contestTitle")}
            </h2>
            <p className="mt-2 text-sm text-text-2">
              {pending.action === "accept"
                ? t("confirm.acceptBody", {
                    amount: formatK(pending.item.fee_breakdown.total_ngwee ?? 0),
                    title: pending.item.item_title,
                  })
                : t("confirm.contestBody", { title: pending.item.item_title })}
            </p>
            <div className="mt-4 flex flex-col gap-2">
              <Button
                type="button"
                className="min-h-12 w-full text-base"
                loading={actingId === pending.returnId}
                loadingLabel={
                  pending.action === "accept" ? t("actions.accepting") : t("actions.contesting")
                }
                onClick={() => void respond(pending.returnId, pending.action, pending.item)}
              >
                {pending.action === "accept" ? t("confirm.acceptCta") : t("confirm.contestCta")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="min-h-11 w-full"
                loadingLabel=""
                disabled={Boolean(actingId)}
                onClick={() => setPending(null)}
              >
                {t("confirm.cancel")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
