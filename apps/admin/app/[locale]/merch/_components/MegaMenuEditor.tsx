"use client";

import { useTranslations } from "next-intl";

export type MegaMenuMiniDraft = {
  key: string;
  title: string;
  href: string;
  price_label?: string;
};

type MegaMenuEditorProps = {
  minis: MegaMenuMiniDraft[];
  promoText: string;
  promoCtaLabel: string;
  promoHref: string;
  onMinisChange: (minis: MegaMenuMiniDraft[]) => void;
  onPromoTextChange: (value: string) => void;
  onPromoCtaLabelChange: (value: string) => void;
  onPromoHrefChange: (value: string) => void;
};

function emptyMini(index: number): MegaMenuMiniDraft {
  return {
    key: `mini-${index}`,
    title: "",
    href: "/en/search",
  };
}

export function MegaMenuEditor({
  minis,
  promoText,
  promoCtaLabel,
  promoHref,
  onMinisChange,
  onPromoTextChange,
  onPromoCtaLabelChange,
  onPromoHrefChange,
}: MegaMenuEditorProps) {
  const t = useTranslations("admin.merch.megaMenu");

  const updateMini = (index: number, patch: Partial<MegaMenuMiniDraft>) => {
    onMinisChange(
      minis.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-text">{t("title")}</h3>
        <p className="text-xs text-muted">{t("subtitle")}</p>
        <p className="mt-1 text-xs text-muted">{t("previewHint")}</p>
      </div>

      <div className="space-y-3">
        {minis.map((mini, index) => (
          <div
            key={mini.key}
            className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-2"
          >
            <label className="flex flex-col gap-1 text-xs text-muted">
              {t("miniTitle")}
              <input
                type="text"
                value={mini.title}
                onChange={(event) => updateMini(index, { title: event.target.value })}
                className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {t("miniHref")}
              <input
                type="text"
                value={mini.href}
                onChange={(event) => updateMini(index, { href: event.target.value })}
                className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted sm:col-span-2">
              {t("miniPrice")}
              <input
                type="text"
                value={mini.price_label ?? ""}
                onChange={(event) => updateMini(index, { price_label: event.target.value })}
                className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
              />
            </label>
            <button
              type="button"
              onClick={() => onMinisChange(minis.filter((_, itemIndex) => itemIndex !== index))}
              className="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-3 text-sm text-danger sm:col-span-2"
            >
              {t("removeMini")}
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        disabled={minis.length >= 6}
        onClick={() => onMinisChange([...minis, emptyMini(minis.length)])}
        className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm disabled:opacity-50"
      >
        {t("addMini")}
      </button>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-muted sm:col-span-2">
          {t("promoText")}
          <textarea
            value={promoText}
            onChange={(event) => onPromoTextChange(event.target.value)}
            rows={2}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          {t("promoCta")}
          <input
            type="text"
            value={promoCtaLabel}
            onChange={(event) => onPromoCtaLabelChange(event.target.value)}
            className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          {t("promoHref")}
          <input
            type="text"
            value={promoHref}
            onChange={(event) => onPromoHrefChange(event.target.value)}
            className="min-h-11 rounded-md border border-border bg-surface px-3 text-sm text-text"
          />
        </label>
      </div>
    </div>
  );
}
