import type { FilterBoxesLabels } from "./filter-boxes";

/** Build filter-box labels from the `catalog` namespace (`plp.facets.*`). */
export function buildFilterBoxLabels(
  t: (key: string) => string,
  options: { withCondition?: boolean } = {},
): FilterBoxesLabels {
  return {
    heading: t("plp.facets.heading"),
    category: t("plp.facets.categories"),
    categoryAll: t("plp.facets.allCategories"),
    price: t("plp.facets.priceBands"),
    bands: {
      under500: t("plp.facets.bandUnder500"),
      "500to2000": t("plp.facets.band500to2000"),
      "2000to5000": t("plp.facets.band2000to5000"),
      over5000: t("plp.facets.bandOver5000"),
    },
    minPrice: t("plp.facets.minPrice"),
    maxPrice: t("plp.facets.maxPrice"),
    setPrice: t("plp.facets.applyPrice"),
    seller: t("plp.facets.seller"),
    verified: t("plp.facets.verified"),
    madeInZambia: t("plp.facets.madeInZambia"),
    nearby: t("plp.facets.nearby"),
    nearMe: t("plp.facets.nearMe"),
    deals: t("plp.facets.deals"),
    dealsBox: t("plp.facets.dealsBox"),
    availability: t("plp.facets.availability"),
    inStock: t("plp.facets.inStock"),
    rating: t("plp.facets.rating"),
    rating4Plus: t("plp.facets.rating4Plus"),
    rating3Plus: t("plp.facets.rating3Plus"),
    ...(options.withCondition
      ? {
          condition: t("plp.facets.condition"),
          conditionNew: t("plp.facets.conditionNew"),
          conditionRefurbished: t("plp.facets.conditionRefurbished"),
          conditionUsed: t("plp.facets.conditionUsed"),
        }
      : {}),
    clear: t("plp.facets.clear"),
  };
}
