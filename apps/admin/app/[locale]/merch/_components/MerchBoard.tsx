"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type HeroVariant,
  type MerchSlot,
  type PreviewUrl,
  type SlotKey,
  merchApi,
  SLOT_ORDER,
} from "./api";
import { SlotEditor } from "./SlotEditor";

const CUSTOMER_ORIGIN = process.env.NEXT_PUBLIC_VERGEO_CUSTOMER_URL ?? "http://localhost:3000";

type MerchBoardProps = {
  locale: string;
};

function formatSchedule(
  from: string | null,
  to: string | null,
  locale: string,
  openLabel: string,
  rangeLabel: (values: { from: string; to: string }) => string,
): string {
  if (!from && !to) {
    return openLabel;
  }
  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString(locale, { timeZone: "Africa/Lusaka" }) : "—";
  return rangeLabel({ from: fmt(from), to: fmt(to) });
}

export function MerchBoard({ locale }: MerchBoardProps) {
  const tBoard = useTranslations("admin.merch.board");
  const tSlots = useTranslations("admin.merch.slots");
  const tCommon = useTranslations("admin.merch.common");

  const [slots, setSlots] = useState<MerchSlot[]>([]);
  const [variants, setVariants] = useState<HeroVariant[]>([]);
  const [preview, setPreview] = useState<PreviewUrl | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [slotRows, variantRows, previewUrl] = await Promise.all([
        merchApi.request<MerchSlot[]>("/admin/merch/slots"),
        merchApi.request<HeroVariant[]>("/admin/merch/hero-variants"),
        merchApi.request<PreviewUrl>("/admin/merch/preview-url"),
      ]);
      setSlots(slotRows);
      setVariants(variantRows);
      setPreview(previewUrl);
    } catch {
      setError(tBoard("error"));
    } finally {
      setLoading(false);
    }
  }, [tBoard]);

  useEffect(() => {
    void load();
  }, [load]);

  const orderedSlots = useMemo(() => {
    const orderIndex = new Map(SLOT_ORDER.map((key, index) => [key, index]));
    return [...slots].sort((left, right) => {
      const leftOrder = orderIndex.get(left.slot_key as SlotKey) ?? 99;
      const rightOrder = orderIndex.get(right.slot_key as SlotKey) ?? 99;
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return left.position - right.position;
    });
  }, [slots]);

  const publishSlot = async (slot: MerchSlot) => {
    if (!window.confirm(tCommon("confirmPublish"))) {
      return;
    }
    setMessage(null);
    try {
      const updated = await merchApi.request<MerchSlot>(`/admin/merch/slots/${slot.id}/publish`, {
        method: "POST",
      });
      setSlots((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setMessage(tCommon("publishSuccess"));
    } catch {
      setMessage(tCommon("publishFailure"));
    }
  };

  const handleSaved = (updated: MerchSlot) => {
    setSlots((current) => current.map((row) => (row.id === updated.id ? updated : row)));
    setEditingId(null);
    setMessage(tCommon("success"));
  };

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{tBoard("loading")}</p>;
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
          {tBoard("retry")}
        </button>
      </div>
    );
  }

  if (orderedSlots.length === 0) {
    return <p className="text-sm text-[#6B5E4C]">{tBoard("empty")}</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-[#6B5E4C]">{tBoard("lusakaTz")}</p>

      {preview ? (
        <div className="rounded-md border border-[#E8DFD0] bg-[#FAF7F2] p-3 text-sm">
          <a
            href={`${CUSTOMER_ORIGIN}${preview.customer_path}`}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-[#2D4A7A] underline"
          >
            {tBoard("preview")}
          </a>
          <p className="mt-1 text-xs text-[#6B5E4C]">{tBoard("previewHint")}</p>
        </div>
      ) : null}

      {message ? <p className="text-sm text-[#2D4A7A]">{message}</p> : null}

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[#E8DFD0] text-xs uppercase tracking-wide text-[#6B5E4C]">
              <th className="px-2 py-3 font-medium">{tBoard("slotKey")}</th>
              <th className="px-2 py-3 font-medium">{tBoard("variant")}</th>
              <th className="px-2 py-3 font-medium">{tBoard("position")}</th>
              <th className="px-2 py-3 font-medium">{tBoard("schedule")}</th>
              <th className="px-2 py-3 font-medium">{tBoard("status")}</th>
              <th className="px-2 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {orderedSlots.map((slot) => (
              <tr key={slot.id} className="border-b border-[#F0E9DE] align-top">
                <td className="px-2 py-3 font-medium text-[#2A2118]">
                  {tSlots(slot.slot_key as SlotKey)}
                </td>
                <td className="px-2 py-3 text-[#6B5E4C]">{slot.variant_key}</td>
                <td className="px-2 py-3 text-[#6B5E4C]">{slot.position}</td>
                <td className="px-2 py-3 text-[#6B5E4C]">
                  {formatSchedule(
                    slot.schedule_from,
                    slot.schedule_to,
                    locale,
                    tBoard("scheduleOpen"),
                    (values) => tBoard("scheduleRange", values),
                  )}
                </td>
                <td className="px-2 py-3">
                  <span
                    className={[
                      "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                      slot.has_draft
                        ? "bg-[#FEF3C7] text-[#92400E]"
                        : "bg-[#E8F5E9] text-[#1B5E20]",
                    ].join(" ")}
                  >
                    {slot.has_draft ? tBoard("draft") : tBoard("published")}
                  </span>
                  <div className="mt-1 text-xs text-[#6B5E4C]">
                    {slot.active ? tBoard("active") : tBoard("inactive")}
                  </div>
                </td>
                <td className="px-2 py-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-3 text-xs"
                      onClick={() => setEditingId(editingId === slot.id ? null : slot.id)}
                    >
                      {tBoard("edit")}
                    </button>
                    {slot.has_draft ? (
                      <button
                        type="button"
                        className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-3 text-xs text-white"
                        onClick={() => void publishSlot(slot)}
                      >
                        {tBoard("publish")}
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editingId ? (
        <SlotEditor
          slot={orderedSlots.find((slot) => slot.id === editingId)!}
          variants={variants}
          onSaved={handleSaved}
          onClose={() => setEditingId(null)}
        />
      ) : null}
    </div>
  );
}
