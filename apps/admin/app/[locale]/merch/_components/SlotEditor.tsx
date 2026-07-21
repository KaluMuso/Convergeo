"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { type HeroVariant, type MerchSlot, merchApi } from "./api";
import { type BannerItemDraft, BannerEditor } from "./BannerEditor";
import { type CollectionDraft, CollectionBuilder } from "./CollectionBuilder";
import { HeroVariantPicker } from "./HeroVariantPicker";
import { type MegaMenuMiniDraft, MegaMenuEditor } from "./MegaMenuEditor";

type SlotEditorProps = {
  slot: MerchSlot;
  variants: HeroVariant[];
  onSaved: (slot: MerchSlot) => void;
  onClose: () => void;
};

function toLocalDatetime(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromLocalDatetime(value: string): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}

function parseBannerItems(payload: Record<string, unknown>): BannerItemDraft[] {
  const raw = payload.items;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }
    const record = entry as Record<string, unknown>;
    return [
      {
        key: typeof record.key === "string" ? record.key : `banner-${index}`,
        title: typeof record.title === "string" ? record.title : "",
        href: typeof record.href === "string" ? record.href : "/en/search",
        image_public_id:
          typeof record.image_public_id === "string" ? record.image_public_id : undefined,
        subtitle: typeof record.subtitle === "string" ? record.subtitle : undefined,
        tag: typeof record.tag === "string" ? record.tag : undefined,
      },
    ];
  });
}

function parseCollections(payload: Record<string, unknown>): CollectionDraft[] {
  const raw = payload.collections;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }
    const record = entry as Record<string, unknown>;
    const queryRaw = record.query;
    const query =
      queryRaw && typeof queryRaw === "object" ? (queryRaw as Record<string, unknown>) : {};
    const type =
      query.type === "listings" || query.type === "category" || query.type === "tag"
        ? query.type
        : "category";
    const order =
      query.order === "position" ||
      query.order === "newest" ||
      query.order === "price_asc" ||
      query.order === "price_desc"
        ? query.order
        : "newest";

    return [
      {
        key: typeof record.key === "string" ? record.key : `collection-${index}`,
        title_key: typeof record.title_key === "string" ? record.title_key : "",
        query: {
          type,
          listing_ids: Array.isArray(query.listing_ids)
            ? query.listing_ids.filter((id): id is string => typeof id === "string")
            : undefined,
          category_slug: typeof query.category_slug === "string" ? query.category_slug : "",
          tag: typeof query.tag === "string" ? query.tag : "",
          order,
        },
      },
    ];
  });
}

function parseMegaMenuMinis(payload: Record<string, unknown>): MegaMenuMiniDraft[] {
  const raw = payload.featured_minis;
  if (!Array.isArray(raw) || raw.length === 0) {
    return [{ key: "mini-0", title: "", href: "/en/search" }];
  }
  return raw.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object") {
      return [];
    }
    const record = entry as Record<string, unknown>;
    return [
      {
        key: typeof record.key === "string" ? record.key : `mini-${index}`,
        title: typeof record.title === "string" ? record.title : "",
        href: typeof record.href === "string" ? record.href : "/en/search",
        price_label: typeof record.price_label === "string" ? record.price_label : undefined,
      },
    ];
  });
}

export function SlotEditor({ slot, variants, onSaved, onClose }: SlotEditorProps) {
  const tHero = useTranslations("admin.merch.hero");
  const tBoard = useTranslations("admin.merch.board");
  const tCommon = useTranslations("admin.merch.common");

  const merged = useMemo(() => {
    const draft = slot.draft;
    return {
      variant_key: draft?.variant_key ?? slot.variant_key,
      payload: { ...slot.payload, ...(draft?.payload ?? {}) },
      schedule_from: draft?.schedule_from ?? slot.schedule_from,
      schedule_to: draft?.schedule_to ?? slot.schedule_to,
      position: draft?.position ?? slot.position,
      active: draft?.active ?? slot.active,
    };
  }, [slot]);

  const [variantKey, setVariantKey] = useState(merged.variant_key);
  const [titleKey, setTitleKey] = useState(
    typeof merged.payload.title_key === "string" ? merged.payload.title_key : "",
  );
  const [subtitleKey, setSubtitleKey] = useState(
    typeof merged.payload.subtitle_key === "string" ? merged.payload.subtitle_key : "",
  );
  const [imagePublicId, setImagePublicId] = useState(
    typeof merged.payload.image_public_id === "string" ? merged.payload.image_public_id : "",
  );
  const [primaryHref, setPrimaryHref] = useState(
    typeof merged.payload.primary_cta_href === "string" ? merged.payload.primary_cta_href : "",
  );
  const [secondaryHref, setSecondaryHref] = useState(
    typeof merged.payload.secondary_cta_href === "string" ? merged.payload.secondary_cta_href : "",
  );
  const [bannerItems, setBannerItems] = useState(() => parseBannerItems(merged.payload));
  const [collections, setCollections] = useState(() => parseCollections(merged.payload));
  const [megaMenuMinis, setMegaMenuMinis] = useState(() => parseMegaMenuMinis(merged.payload));
  const [megaMenuPromoText, setMegaMenuPromoText] = useState(
    typeof merged.payload.promo_text === "string" ? merged.payload.promo_text : "",
  );
  const [megaMenuPromoCta, setMegaMenuPromoCta] = useState(
    typeof merged.payload.promo_cta_label === "string" ? merged.payload.promo_cta_label : "",
  );
  const [megaMenuPromoHref, setMegaMenuPromoHref] = useState(
    typeof merged.payload.promo_href === "string" ? merged.payload.promo_href : "/search",
  );
  const [scheduleFrom, setScheduleFrom] = useState(toLocalDatetime(merged.schedule_from));
  const [scheduleTo, setScheduleTo] = useState(toLocalDatetime(merged.schedule_to));
  const [position, setPosition] = useState(merged.position);
  const [active, setActive] = useState(merged.active);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildPayload = (): Record<string, unknown> => {
    if (slot.slot_key === "hero") {
      return {
        title_key: titleKey,
        subtitle_key: subtitleKey,
        image_public_id: imagePublicId || undefined,
        primary_cta_href: primaryHref || undefined,
        secondary_cta_href: secondaryHref || undefined,
        is_default: slot.payload.is_default,
      };
    }
    if (slot.slot_key === "banner_row") {
      return { items: bannerItems.filter((item) => item.title.trim().length > 0) };
    }
    if (slot.slot_key === "featured_collections") {
      return { collections };
    }
    if (slot.slot_key === "mega_menu") {
      return {
        featured_minis: megaMenuMinis
          .filter((mini) => mini.title.trim().length > 0)
          .map(({ title, href, price_label }) => ({
            title: title.trim(),
            href: href.trim(),
            ...(price_label?.trim() ? { price_label: price_label.trim() } : {}),
          })),
        promo_text: megaMenuPromoText.trim(),
        promo_cta_label: megaMenuPromoCta.trim(),
        promo_href: megaMenuPromoHref.trim() || "/search",
      };
    }
    return { ...slot.payload };
  };

  const saveDraft = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await merchApi.request<MerchSlot>(`/admin/merch/slots/${slot.id}/draft`, {
        method: "POST",
        body: JSON.stringify({
          variant_key: variantKey,
          payload: buildPayload(),
          schedule_from: fromLocalDatetime(scheduleFrom),
          schedule_to: fromLocalDatetime(scheduleTo),
          position,
          active,
        }),
      });
      onSaved(updated);
    } catch {
      setError(tCommon("failure"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface p-4 shadow-sm">
      {slot.slot_key === "hero" ? (
        <>
          <HeroVariantPicker variants={variants} selected={variantKey} onSelect={setVariantKey} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-muted">
              {tHero("titleKey")}
              <input
                type="text"
                value={titleKey}
                onChange={(event) => setTitleKey(event.target.value)}
                className="min-h-11 rounded-md border border-border px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {tHero("subtitleKey")}
              <input
                type="text"
                value={subtitleKey}
                onChange={(event) => setSubtitleKey(event.target.value)}
                className="min-h-11 rounded-md border border-border px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {tHero("imagePublicId")}
              <input
                type="text"
                value={imagePublicId}
                onChange={(event) => setImagePublicId(event.target.value)}
                className="min-h-11 rounded-md border border-border px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {tHero("primaryCtaHref")}
              <input
                type="text"
                value={primaryHref}
                onChange={(event) => setPrimaryHref(event.target.value)}
                className="min-h-11 rounded-md border border-border px-3 text-sm"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {tHero("secondaryCtaHref")}
              <input
                type="text"
                value={secondaryHref}
                onChange={(event) => setSecondaryHref(event.target.value)}
                className="min-h-11 rounded-md border border-border px-3 text-sm"
              />
            </label>
          </div>
        </>
      ) : null}

      {slot.slot_key === "banner_row" ? (
        <BannerEditor
          items={bannerItems}
          scheduleFrom={scheduleFrom}
          scheduleTo={scheduleTo}
          onItemsChange={setBannerItems}
          onScheduleFromChange={setScheduleFrom}
          onScheduleToChange={setScheduleTo}
        />
      ) : null}

      {slot.slot_key === "featured_collections" ? (
        <CollectionBuilder collections={collections} onChange={setCollections} />
      ) : null}

      {slot.slot_key === "mega_menu" ? (
        <MegaMenuEditor
          minis={megaMenuMinis}
          promoText={megaMenuPromoText}
          promoCtaLabel={megaMenuPromoCta}
          promoHref={megaMenuPromoHref}
          onMinisChange={setMegaMenuMinis}
          onPromoTextChange={setMegaMenuPromoText}
          onPromoCtaLabelChange={setMegaMenuPromoCta}
          onPromoHrefChange={setMegaMenuPromoHref}
        />
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-xs text-muted">
          {tBoard("position")}
          <input
            type="number"
            value={position}
            onChange={(event) => setPosition(Number(event.target.value))}
            className="min-h-11 rounded-md border border-border px-3 text-sm"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
            className="h-4 w-4"
          />
          {tBoard("active")}
        </label>
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={() => void saveDraft()}
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
        >
          {saving ? tCommon("saving") : tCommon("save")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
        >
          {tCommon("cancel")}
        </button>
      </div>
    </div>
  );
}
