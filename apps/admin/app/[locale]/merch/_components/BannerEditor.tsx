"use client";

import { useTranslations } from "next-intl";

export type BannerItemDraft = {
  key: string;
  title: string;
  href: string;
  image_public_id?: string;
  subtitle?: string;
  tag?: string;
};

type BannerEditorProps = {
  items: BannerItemDraft[];
  scheduleFrom: string;
  scheduleTo: string;
  onItemsChange: (items: BannerItemDraft[]) => void;
  onScheduleFromChange: (value: string) => void;
  onScheduleToChange: (value: string) => void;
};

function emptyBanner(index: number): BannerItemDraft {
  return {
    key: `banner-${index}`,
    title: "",
    href: "/en/search",
  };
}

export function BannerEditor({
  items,
  scheduleFrom,
  scheduleTo,
  onItemsChange,
  onScheduleFromChange,
  onScheduleToChange,
}: BannerEditorProps) {
  const t = useTranslations("admin.merch.banner");

  const updateItem = (index: number, patch: Partial<BannerItemDraft>) => {
    const next = items.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...patch } : item,
    );
    onItemsChange(next);
  };

  const addItem = () => {
    if (items.length >= 4) {
      return;
    }
    onItemsChange([...items, emptyBanner(items.length)]);
  };

  const removeItem = (index: number) => {
    onItemsChange(items.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-[#2A2118]">{t("title")}</h3>
        <p className="text-xs text-[#6B5E4C]">{t("subtitle")}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
          {t("scheduleFrom")}
          <input
            type="datetime-local"
            value={scheduleFrom}
            onChange={(event) => onScheduleFromChange(event.target.value)}
            className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm text-[#2A2118]"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
          {t("scheduleTo")}
          <input
            type="datetime-local"
            value={scheduleTo}
            onChange={(event) => onScheduleToChange(event.target.value)}
            className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm text-[#2A2118]"
          />
        </label>
      </div>

      <div className="space-y-3">
        {items.map((item, index) => (
          <div
            key={item.key}
            className="space-y-2 rounded-lg border border-[#E8DFD0] bg-[#FAF7F2] p-3"
          >
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("itemTitle")}
              <input
                type="text"
                value={item.title}
                onChange={(event) => updateItem(index, { title: event.target.value })}
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("itemHref")}
              <input
                type="text"
                value={item.href}
                onChange={(event) => updateItem(index, { href: event.target.value })}
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("itemImage")}
              <input
                type="text"
                value={item.image_public_id ?? ""}
                onChange={(event) =>
                  updateItem(index, { image_public_id: event.target.value || undefined })
                }
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
            <button
              type="button"
              onClick={() => removeItem(index)}
              className="text-xs text-[#9B2C2C] underline"
            >
              {t("removeItem")}
            </button>
          </div>
        ))}
      </div>

      {items.length < 4 ? (
        <button
          type="button"
          onClick={addItem}
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
        >
          {t("addItem")}
        </button>
      ) : null}
    </div>
  );
}
