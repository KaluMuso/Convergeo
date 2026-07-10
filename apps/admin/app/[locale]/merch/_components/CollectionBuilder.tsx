"use client";

import { useTranslations } from "next-intl";

export type CollectionQueryType = "listings" | "category" | "tag";
export type CollectionSortOrder = "position" | "newest" | "price_asc" | "price_desc";

export type CollectionDraft = {
  key: string;
  title_key: string;
  query: {
    type: CollectionQueryType;
    listing_ids?: string[];
    category_slug?: string;
    tag?: string;
    order: CollectionSortOrder;
  };
};

type CollectionBuilderProps = {
  collections: CollectionDraft[];
  onChange: (collections: CollectionDraft[]) => void;
};

function emptyCollection(index: number): CollectionDraft {
  return {
    key: `collection-${index}`,
    title_key: "",
    query: { type: "category", category_slug: "", order: "newest" },
  };
}

export function CollectionBuilder({ collections, onChange }: CollectionBuilderProps) {
  const t = useTranslations("admin.merch.collection");

  const updateCollection = (index: number, patch: Partial<CollectionDraft>) => {
    onChange(
      collections.map((collection, collectionIndex) =>
        collectionIndex === index ? { ...collection, ...patch } : collection,
      ),
    );
  };

  const updateQuery = (index: number, patch: Partial<CollectionDraft["query"]>) => {
    const current = collections[index];
    if (!current) {
      return;
    }
    updateCollection(index, { query: { ...current.query, ...patch } });
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-[#2A2118]">{t("title")}</h3>
        <p className="text-xs text-[#6B5E4C]">{t("subtitle")}</p>
      </div>

      {collections.map((collection, index) => (
        <div
          key={collection.key}
          className="space-y-2 rounded-lg border border-[#E8DFD0] bg-[#FAF7F2] p-3"
        >
          <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
            {t("collectionTitleKey")}
            <input
              type="text"
              value={collection.title_key}
              onChange={(event) => updateCollection(index, { title_key: event.target.value })}
              className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
            {t("queryType")}
            <select
              value={collection.query.type}
              onChange={(event) =>
                updateQuery(index, { type: event.target.value as CollectionQueryType })
              }
              className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
            >
              <option value="listings">{t("queryListingIds")}</option>
              <option value="category">{t("queryCategory")}</option>
              <option value="tag">{t("queryTag")}</option>
            </select>
          </label>

          {collection.query.type === "listings" ? (
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("queryListingIds")}
              <input
                type="text"
                value={(collection.query.listing_ids ?? []).join(", ")}
                onChange={(event) =>
                  updateQuery(index, {
                    listing_ids: event.target.value
                      .split(",")
                      .map((id) => id.trim())
                      .filter(Boolean),
                  })
                }
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
          ) : null}

          {collection.query.type === "category" ? (
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("queryCategory")}
              <input
                type="text"
                value={collection.query.category_slug ?? ""}
                onChange={(event) => updateQuery(index, { category_slug: event.target.value })}
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
          ) : null}

          {collection.query.type === "tag" ? (
            <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
              {t("queryTag")}
              <input
                type="text"
                value={collection.query.tag ?? ""}
                onChange={(event) => updateQuery(index, { tag: event.target.value })}
                className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
              />
            </label>
          ) : null}

          <label className="flex flex-col gap-1 text-xs text-[#6B5E4C]">
            {t("queryOrder")}
            <select
              value={collection.query.order}
              onChange={(event) =>
                updateQuery(index, { order: event.target.value as CollectionSortOrder })
              }
              className="min-h-11 rounded-md border border-[#E8DFD0] bg-white px-3 text-sm"
            >
              <option value="position">{t("orderPosition")}</option>
              <option value="newest">{t("orderNewest")}</option>
              <option value="price_asc">{t("orderPriceAsc")}</option>
              <option value="price_desc">{t("orderPriceDesc")}</option>
            </select>
          </label>
        </div>
      ))}

      <button
        type="button"
        onClick={() => onChange([...collections, emptyCollection(collections.length)])}
        className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
      >
        {t("addCollection")}
      </button>
    </div>
  );
}
