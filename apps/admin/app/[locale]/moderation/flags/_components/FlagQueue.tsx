"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { type EntityType, type FlagAction, type FlagQueueItem, flagsApi } from "./api";
import { FlagActionDialog } from "./FlagActionDialog";
import { RepeatOffenderBadge } from "./RepeatOffenderBadge";

type FlagQueueProps = {
  locale: string;
};

type PendingAction = {
  item: FlagQueueItem;
  action: FlagAction;
};

const ENTITY_TYPES: Array<EntityType | "all"> = ["all", "listing", "review", "prohibited"];

export function FlagQueue({ locale }: FlagQueueProps) {
  const t = useTranslations("admin.flags.queue");
  const tActions = useTranslations("admin.flags.actions");
  const [items, setItems] = useState<FlagQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [entityFilter, setEntityFilter] = useState<EntityType | "all">("all");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status: "open" });
      if (entityFilter !== "all") {
        params.set("entity_type", entityFilter);
      }
      const data = await flagsApi.request<FlagQueueItem[]>(`/admin/flags?${params.toString()}`);
      setItems(data);
    } catch {
      setError(t("error"));
    } finally {
      setLoading(false);
    }
  }, [entityFilter, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const openAction = (item: FlagQueueItem, action: FlagAction) => {
    setPending({ item, action });
  };

  const handleComplete = async () => {
    setPending(null);
    setMessage(t("success"));
    await load();
  };

  const listingActions: FlagAction[] = [
    "dismiss",
    "unpublish",
    "remove",
    "warn-vendor",
    "escalate-suspend",
  ];
  const reviewActions: FlagAction[] = ["dismiss", "remove", "warn-vendor", "escalate-suspend"];
  const prohibitedActions: FlagAction[] = [
    "dismiss",
    "unpublish",
    "remove",
    "warn-vendor",
    "escalate-suspend",
  ];

  const actionsFor = (entityType: EntityType): FlagAction[] => {
    if (entityType === "review") {
      return reviewActions;
    }
    if (entityType === "prohibited") {
      return prohibitedActions;
    }
    return listingActions;
  };

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
          onClick={() => void load()}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-[#6B5E4C]">{t("filterEntity")}</span>
        {ENTITY_TYPES.map((value) => (
          <button
            key={value}
            type="button"
            className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
              entityFilter === value
                ? "border-[#2D4A7A] bg-[#2D4A7A]/5 text-[#2D4A7A]"
                : "border-[#E8DFD0] text-[#6B5E4C]"
            }`}
            onClick={() => setEntityFilter(value)}
          >
            {t(`entityType.${value}`)}
          </button>
        ))}
      </div>

      {message ? <p className="text-sm text-[#2D4A7A]">{message}</p> : null}

      {items.length === 0 ? (
        <p className="text-sm text-[#6B5E4C]">{t("empty")}</p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <article
              key={item.id}
              className="rounded-lg border border-[#E8DFD0] bg-white p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-[#6B5E4C]">
                      {t(`entityType.${item.entity_type}`)}
                    </span>
                    <RepeatOffenderBadge count={item.repeat_offender_count} />
                  </div>
                  <h2 className="font-medium text-[#2A2118]">
                    {item.entity_label ?? item.entity_id}
                  </h2>
                  {item.vendor_display_name ? (
                    <p className="text-sm text-[#6B5E4C]">
                      {t("vendor", { name: item.vendor_display_name })}
                    </p>
                  ) : null}
                  <p className="text-sm text-[#6B5E4C]">{item.reason}</p>
                  <p className="text-xs text-[#6B5E4C]">
                    {t("reported", { at: new Date(item.created_at).toLocaleString(locale) })}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {actionsFor(item.entity_type).map((action) => (
                    <button
                      key={action}
                      type="button"
                      className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
                        action === "remove" || action === "escalate-suspend"
                          ? "border-[#9B2C2C] text-[#9B2C2C]"
                          : "border-[#2D4A7A] text-[#2D4A7A]"
                      }`}
                      onClick={() => openAction(item, action)}
                    >
                      {tActions(`${action}.button`)}
                    </button>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {pending ? (
        <FlagActionDialog
          item={pending.item}
          action={pending.action}
          onClose={() => setPending(null)}
          onComplete={() => void handleComplete()}
        />
      ) : null}
    </div>
  );
}
