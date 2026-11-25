import type { ListingFieldLabels } from "../_components/listing-fields";

type Translate = (key: string) => string;

/** One place that maps vendor.listings.fields.* i18n keys to the form labels. */
export function buildListingFieldLabels(t: Translate): ListingFieldLabels {
  return {
    priceLabel: t("listings.fields.priceLabel"),
    pricePlaceholder: t("listings.fields.pricePlaceholder"),
    priceHelp: t("listings.fields.priceHelp"),
    pricePerStepHelp: t("listings.fields.pricePerStepHelp"),
    priceInvalid: t("listings.fields.priceInvalid"),
    productClassLabel: t("listings.fields.productClassLabel"),
    classA: t("listings.fields.classA"),
    classB: t("listings.fields.classB"),
    classC: t("listings.fields.classC"),
    classD: t("listings.fields.classD"),
    classE: t("listings.fields.classE"),
    standaloneClassHint: t("listings.fields.standaloneClassHint"),
    saleUnitLabel: t("listings.fields.saleUnitLabel"),
    unitEach: t("listings.fields.unitEach"),
    unitMetre: t("listings.fields.unitMetre"),
    unitKg: t("listings.fields.unitKg"),
    unitLitre: t("listings.fields.unitLitre"),
    unitBag: t("listings.fields.unitBag"),
    unitSqm: t("listings.fields.unitSqm"),
    unitStepLabel: t("listings.fields.unitStepLabel"),
    unitStepHelp: t("listings.fields.unitStepHelp"),
    unitStepInvalid: t("listings.fields.unitStepInvalid"),
    minStepsLabel: t("listings.fields.minStepsLabel"),
    conditionLabel: t("listings.fields.conditionLabel"),
    conditionNew: t("listings.fields.conditionNew"),
    conditionRefurbished: t("listings.fields.conditionRefurbished"),
    conditionUsed: t("listings.fields.conditionUsed"),
    defectNotesLabel: t("listings.fields.defectNotesLabel"),
    defectNotesPlaceholder: t("listings.fields.defectNotesPlaceholder"),
    defectNotesHelp: t("listings.fields.defectNotesHelp"),
    defectNotesInvalid: t("listings.fields.defectNotesInvalid"),
    fulfilmentLabel: t("listings.fields.fulfilmentLabel"),
    fulfilmentStocked: t("listings.fields.fulfilmentStocked"),
    fulfilmentMadeToOrder: t("listings.fields.fulfilmentMadeToOrder"),
    leadTimeLabel: t("listings.fields.leadTimeLabel"),
    leadTimeHelp: t("listings.fields.leadTimeHelp"),
    leadTimeInvalid: t("listings.fields.leadTimeInvalid"),
    capacityLabel: t("listings.fields.capacityLabel"),
    capacityHelp: t("listings.fields.capacityHelp"),
    capacityInvalid: t("listings.fields.capacityInvalid"),
    stockModeLabel: t("listings.fields.stockModeLabel"),
    stockTracked: t("listings.fields.stockTracked"),
    stockAlways: t("listings.fields.stockAlways"),
    stockQtyLabel: t("listings.fields.stockQtyLabel"),
    wholesaleSectionHeading: t("listings.fields.wholesaleSectionHeading"),
    wholesaleBuyersHint: t("listings.fields.wholesaleBuyersHint"),
    wholesaleLabel: t("listings.fields.wholesaleLabel"),
    wholesaleHelp: t("listings.fields.wholesaleHelp"),
    wholesaleMeasureUnavailable: t("listings.fields.wholesaleMeasureUnavailable"),
    moqLabel: t("listings.fields.moqLabel"),
    evidenceDraftNotice: t("listings.fields.evidenceDraftNotice"),
    saveDraft: t("listings.fields.saveDraft"),
    savingDraft: t("listings.fields.savingDraft"),
    classHintD: t("listings.fields.classHintD"),
    classHintE: t("listings.fields.classHintE"),
    conditionUsedHint: t("listings.fields.conditionUsedHint"),
    conditionGradeLabel: t("listings.fields.conditionGradeLabel"),
    gradeExcellent: t("listings.fields.gradeExcellent"),
    gradeGood: t("listings.fields.gradeGood"),
    gradeFair: t("listings.fields.gradeFair"),
    gradeParts: t("listings.fields.gradeParts"),
    fulfilmentLockedHint: t("listings.fields.fulfilmentLockedHint"),
    fulfilmentOptionsLabel: t("listings.fields.fulfilmentOptionsLabel"),
    fulfilmentOptionsHelp: t("listings.fields.fulfilmentOptionsHelp"),
    fulfilmentOptionsInvalid: t("listings.fields.fulfilmentOptionsInvalid"),
    optionLusakaDelivery: t("listings.fields.optionLusakaDelivery"),
    optionPickupShop: t("listings.fields.optionPickupShop"),
    optionPickupNationwide: t("listings.fields.optionPickupNationwide"),
    stockLockedHint: t("listings.fields.stockLockedHint"),
    required: t("listings.errors.required"),
  };
}

/**
 * Message-object key read with `t.raw` (an object of code -> text, not a leaf, so
 * it is not a literal `t()` key for the i18n missing-key sweep).
 */
export const FIELD_ERRORS_KEY = "listings.fieldErrors";

/** vendor.listings.fieldErrors.* : server field-error code -> localized text. */
export function readFieldErrorMessages(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object") return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
