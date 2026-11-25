"use client";

import { isValidUnitDecimal, unitDecimalToMilli } from "../_lib/measure";
import { isValidZmwDecimal, zmwDecimalToNgwee } from "../_lib/money";
import { FULFILMENT_OPTIONS, USED_GRADES } from "../_lib/types";
import { Checkbox, FormField, Input, Select, Switch, Textarea } from "../_lib/ui";

import type {
  FulfilmentMode,
  FulfilmentOption,
  ListingCondition,
  ProductClass,
  SaleUnit,
  StockMode,
  UsedGrade,
} from "../_lib/types";
import type { ChangeEvent } from "react";

export type ListingFieldValues = {
  priceZmw: string;
  productClass: ProductClass;
  saleUnit: SaleUnit;
  unitStep: string;
  minSteps: string;
  condition: ListingCondition;
  conditionDetail: UsedGrade;
  defectNotes: string;
  fulfilmentOptions: FulfilmentOption[];
  fulfilmentMode: FulfilmentMode;
  leadTimeDays: string;
  vendorCapacityPerWeek: string;
  stockMode: StockMode;
  stockQty: string;
  wholesale: boolean;
  moq: string;
};

export const DEFAULT_LISTING_FIELDS: ListingFieldValues = {
  priceZmw: "",
  productClass: "A",
  saleUnit: "each",
  unitStep: "1",
  minSteps: "1",
  condition: "new",
  conditionDetail: "used_good",
  defectNotes: "",
  fulfilmentOptions: ["lusaka_delivery", "pickup_shop"],
  fulfilmentMode: "stocked",
  leadTimeDays: "",
  vendorCapacityPerWeek: "",
  stockMode: "tracked",
  stockQty: "1",
  wholesale: false,
  moq: "10",
};

export type ListingFieldLabels = {
  priceLabel: string;
  pricePlaceholder: string;
  priceHelp: string;
  pricePerStepHelp: string;
  priceInvalid: string;
  productClassLabel: string;
  classA: string;
  classB: string;
  classC: string;
  classD: string;
  classE: string;
  standaloneClassHint: string;
  classHintD: string;
  classHintE: string;
  saleUnitLabel: string;
  unitEach: string;
  unitMetre: string;
  unitKg: string;
  unitLitre: string;
  unitBag: string;
  unitSqm: string;
  unitStepLabel: string;
  unitStepHelp: string;
  unitStepInvalid: string;
  minStepsLabel: string;
  conditionLabel: string;
  conditionNew: string;
  conditionRefurbished: string;
  conditionUsed: string;
  conditionUsedHint: string;
  conditionGradeLabel: string;
  gradeExcellent: string;
  gradeGood: string;
  gradeFair: string;
  gradeParts: string;
  defectNotesLabel: string;
  defectNotesPlaceholder: string;
  defectNotesHelp: string;
  defectNotesInvalid: string;
  fulfilmentLabel: string;
  fulfilmentStocked: string;
  fulfilmentMadeToOrder: string;
  fulfilmentLockedHint: string;
  fulfilmentOptionsLabel: string;
  fulfilmentOptionsHelp: string;
  fulfilmentOptionsInvalid: string;
  optionLusakaDelivery: string;
  optionPickupShop: string;
  optionPickupNationwide: string;
  leadTimeLabel: string;
  leadTimeHelp: string;
  leadTimeInvalid: string;
  capacityLabel: string;
  capacityHelp: string;
  capacityInvalid: string;
  stockModeLabel: string;
  stockTracked: string;
  stockAlways: string;
  stockLockedHint: string;
  stockQtyLabel: string;
  wholesaleSectionHeading: string;
  wholesaleBuyersHint: string;
  wholesaleLabel: string;
  wholesaleHelp: string;
  wholesaleMeasureUnavailable: string;
  moqLabel: string;
  evidenceDraftNotice: string;
  saveDraft: string;
  savingDraft: string;
  required: string;
};

type ListingFieldsProps = {
  values: ListingFieldValues;
  onChange: (patch: Partial<ListingFieldValues>) => void;
  wholesaleEnabled: boolean;
  labels: ListingFieldLabels;
  allowStandaloneClasses?: boolean;
  inventoryReadOnly?: boolean;
  /** Server (or client) field messages keyed by API field name. */
  errors?: Record<string, string>;
};

const POSITIVE_INTEGER_PATTERN = /^[1-9]\d*$/;
const NON_NEGATIVE_INTEGER_PATTERN = /^(0|[1-9]\d*)$/;

function isSafeIntegerInput(value: string, pattern: RegExp): boolean {
  if (!pattern.test(value)) {
    return false;
  }
  return Number.isSafeInteger(Number(value));
}

export function applyListingFieldPatch(
  values: ListingFieldValues,
  patch: Partial<ListingFieldValues>,
): ListingFieldValues {
  const next = { ...values, ...patch };

  if (patch.saleUnit === "each") {
    next.unitStep = "1";
    next.minSteps = "1";
  } else if (patch.saleUnit) {
    next.wholesale = false;
  }

  if (patch.condition && patch.condition !== "used") {
    next.defectNotes = "";
  }
  if (patch.fulfilmentMode === "stocked") {
    next.leadTimeDays = "";
  }
  if (patch.productClass && patch.productClass !== "E") {
    next.vendorCapacityPerWeek = "";
  }

  if (next.productClass === "E") {
    next.fulfilmentMode = "made_to_order";
    next.stockMode = "always_available";
    next.stockQty = "";
  }
  if (next.saleUnit !== "each") {
    next.wholesale = false;
  }

  return next;
}

/** Only second-hand stock needs photo evidence; a new Class D item does not. */
export function requiresListingEvidence(values: ListingFieldValues): boolean {
  return values.condition === "used";
}

export function parseListingFieldValues(values: ListingFieldValues): {
  priceNgwee: number;
  unitStepMilli: number;
  minSteps: number;
  defectNotes: string | null;
  conditionDetail: UsedGrade | null;
  leadTimeDays: number | null;
  vendorCapacityPerWeek: number | null;
  stockQty: number | null;
  moq: number;
} {
  return {
    priceNgwee: zmwDecimalToNgwee(values.priceZmw),
    unitStepMilli: values.saleUnit === "each" ? 1_000 : unitDecimalToMilli(values.unitStep),
    minSteps: values.saleUnit === "each" ? 1 : Number(values.minSteps),
    defectNotes: values.condition === "used" ? values.defectNotes.trim() : null,
    conditionDetail: values.condition === "used" ? values.conditionDetail : null,
    leadTimeDays: values.fulfilmentMode === "made_to_order" ? Number(values.leadTimeDays) : null,
    vendorCapacityPerWeek:
      values.productClass === "E" ? Number(values.vendorCapacityPerWeek) : null,
    stockQty: values.stockMode === "tracked" ? Number(values.stockQty) : null,
    moq: values.wholesale ? Number(values.moq) : 1,
  };
}

export function validateListingFields(
  values: ListingFieldValues,
  labels: ListingFieldLabels,
): string | null {
  if (!isValidZmwDecimal(values.priceZmw)) {
    return labels.priceInvalid;
  }
  if (
    values.saleUnit !== "each" &&
    (!isValidUnitDecimal(values.unitStep) || unitDecimalToMilli(values.unitStep) < 1)
  ) {
    return labels.unitStepInvalid;
  }
  if (
    values.saleUnit !== "each" &&
    !isSafeIntegerInput(values.minSteps, POSITIVE_INTEGER_PATTERN)
  ) {
    return labels.required;
  }
  if (values.condition === "used" && values.defectNotes.trim().length < 10) {
    return labels.defectNotesInvalid;
  }
  if (
    values.fulfilmentMode === "made_to_order" &&
    (!isSafeIntegerInput(values.leadTimeDays, POSITIVE_INTEGER_PATTERN) ||
      Number(values.leadTimeDays) > 365)
  ) {
    return labels.leadTimeInvalid;
  }
  if (
    values.productClass === "E" &&
    (!isSafeIntegerInput(values.vendorCapacityPerWeek, POSITIVE_INTEGER_PATTERN) ||
      Number(values.vendorCapacityPerWeek) > 9_999)
  ) {
    return labels.capacityInvalid;
  }
  if (
    values.stockMode === "tracked" &&
    !isSafeIntegerInput(values.stockQty, NON_NEGATIVE_INTEGER_PATTERN)
  ) {
    return labels.required;
  }
  if (values.wholesale && values.saleUnit !== "each") {
    return labels.wholesaleMeasureUnavailable;
  }
  if (values.wholesale && !isSafeIntegerInput(values.moq, POSITIVE_INTEGER_PATTERN)) {
    return labels.required;
  }
  if (values.fulfilmentOptions.length === 0) {
    return labels.fulfilmentOptionsInvalid;
  }
  return null;
}

/** Field-level client validation, so each problem shows next to its input. */
export function listingFieldErrors(
  values: ListingFieldValues,
  labels: ListingFieldLabels,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!isValidZmwDecimal(values.priceZmw)) errors.price_ngwee = labels.priceInvalid;
  if (
    values.saleUnit !== "each" &&
    (!isValidUnitDecimal(values.unitStep) || unitDecimalToMilli(values.unitStep) < 1)
  ) {
    errors.unit_step_milli = labels.unitStepInvalid;
  }
  if (values.condition === "used" && values.defectNotes.trim().length < 10) {
    errors.defect_notes = labels.defectNotesInvalid;
  }
  if (
    values.fulfilmentMode === "made_to_order" &&
    (!isSafeIntegerInput(values.leadTimeDays, POSITIVE_INTEGER_PATTERN) ||
      Number(values.leadTimeDays) > 365)
  ) {
    errors.lead_time_days = labels.leadTimeInvalid;
  }
  if (
    values.productClass === "E" &&
    (!isSafeIntegerInput(values.vendorCapacityPerWeek, POSITIVE_INTEGER_PATTERN) ||
      Number(values.vendorCapacityPerWeek) > 9_999)
  ) {
    errors.vendor_capacity_per_week = labels.capacityInvalid;
  }
  if (
    values.stockMode === "tracked" &&
    !isSafeIntegerInput(values.stockQty, NON_NEGATIVE_INTEGER_PATTERN)
  ) {
    errors.stock_qty = labels.required;
  }
  if (values.wholesale && !isSafeIntegerInput(values.moq, POSITIVE_INTEGER_PATTERN)) {
    errors.moq = labels.required;
  }
  if (values.fulfilmentOptions.length === 0) {
    errors.fulfilment_options = labels.fulfilmentOptionsInvalid;
  }
  return errors;
}

export function ListingFields({
  values,
  onChange,
  wholesaleEnabled,
  labels,
  allowStandaloneClasses = true,
  inventoryReadOnly = false,
  errors = {},
}: ListingFieldsProps) {
  const priceError =
    values.priceZmw && !isValidZmwDecimal(values.priceZmw)
      ? labels.priceInvalid
      : errors.price_ngwee;
  const evidenceRequired = requiresListingEvidence(values);
  const handleChange = (patch: Partial<ListingFieldValues>) => {
    onChange(applyListingFieldPatch(values, patch));
  };

  return (
    <div className="flex flex-col gap-4">
      <FormField label={labels.productClassLabel} errorMessage={errors.product_class}>
        <Select
          disabled={inventoryReadOnly}
          value={values.productClass}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ productClass: event.target.value as ProductClass })
          }
        >
          <option value="A">{labels.classA}</option>
          <option value="B">{labels.classB}</option>
          <option value="C">{labels.classC}</option>
          <option value="D" disabled={!allowStandaloneClasses}>
            {labels.classD}
          </option>
          <option value="E" disabled={!allowStandaloneClasses}>
            {labels.classE}
          </option>
        </Select>
      </FormField>

      {!allowStandaloneClasses ? (
        <p className="text-xs text-text-2" role="note">
          {labels.standaloneClassHint}
        </p>
      ) : null}
      {values.productClass === "D" ? (
        <p className="text-xs text-text-2" role="note">
          {labels.classHintD}
        </p>
      ) : null}
      {values.productClass === "E" ? (
        <p className="text-xs text-text-2" role="note">
          {labels.classHintE}
        </p>
      ) : null}

      <FormField label={labels.saleUnitLabel}>
        <Select
          disabled={inventoryReadOnly}
          value={values.saleUnit}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ saleUnit: event.target.value as SaleUnit })
          }
        >
          <option value="each">{labels.unitEach}</option>
          <option value="metre">{labels.unitMetre}</option>
          <option value="kg">{labels.unitKg}</option>
          <option value="litre">{labels.unitLitre}</option>
          <option value="bag">{labels.unitBag}</option>
          <option value="sqm">{labels.unitSqm}</option>
        </Select>
      </FormField>

      {values.saleUnit !== "each" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            label={labels.unitStepLabel}
            helpText={labels.unitStepHelp}
            errorMessage={errors.unit_step_milli}
          >
            <Input
              inputMode="decimal"
              disabled={inventoryReadOnly}
              value={values.unitStep}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                handleChange({ unitStep: event.target.value })
              }
            />
          </FormField>
          <FormField label={labels.minStepsLabel} errorMessage={errors.min_steps}>
            <Input
              inputMode="numeric"
              disabled={inventoryReadOnly}
              min={1}
              step={1}
              value={values.minSteps}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                handleChange({ minSteps: event.target.value })
              }
            />
          </FormField>
        </div>
      ) : null}

      <FormField
        label={labels.priceLabel}
        helpText={values.saleUnit === "each" ? labels.priceHelp : labels.pricePerStepHelp}
        errorMessage={priceError}
      >
        <Input
          inputMode="decimal"
          placeholder={labels.pricePlaceholder}
          value={values.priceZmw}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            handleChange({ priceZmw: event.target.value })
          }
          error={Boolean(priceError)}
        />
      </FormField>

      <FormField label={labels.conditionLabel} errorMessage={errors.condition}>
        <Select
          value={values.condition}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ condition: event.target.value as ListingCondition })
          }
        >
          <option value="new">{labels.conditionNew}</option>
          <option value="refurbished">{labels.conditionRefurbished}</option>
          <option value="used">{labels.conditionUsed}</option>
        </Select>
      </FormField>

      {values.condition === "used" ? (
        <>
          <p className="text-xs text-text-2" role="note">
            {labels.conditionUsedHint}
          </p>
          <FormField label={labels.conditionGradeLabel} errorMessage={errors.condition_detail}>
            <Select
              value={values.conditionDetail}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                handleChange({
                  conditionDetail: event.target.value as UsedGrade,
                })
              }
            >
              {USED_GRADES.map((grade) => (
                <option key={grade} value={grade}>
                  {grade === "used_excellent"
                    ? labels.gradeExcellent
                    : grade === "used_good"
                      ? labels.gradeGood
                      : grade === "used_fair"
                        ? labels.gradeFair
                        : labels.gradeParts}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField
            label={labels.defectNotesLabel}
            helpText={labels.defectNotesHelp}
            errorMessage={errors.defect_notes}
          >
            <Textarea
              value={values.defectNotes}
              maxLength={2_000}
              placeholder={labels.defectNotesPlaceholder}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                handleChange({ defectNotes: event.target.value })
              }
            />
          </FormField>
        </>
      ) : null}

      {evidenceRequired ? (
        <p
          className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-text"
          role="note"
        >
          {labels.evidenceDraftNotice}
        </p>
      ) : null}

      <FormField label={labels.fulfilmentLabel} errorMessage={errors.fulfilment_mode}>
        <Select
          disabled={inventoryReadOnly}
          value={values.fulfilmentMode}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({
              fulfilmentMode: event.target.value as FulfilmentMode,
            })
          }
        >
          <option value="stocked" disabled={values.productClass === "E"}>
            {labels.fulfilmentStocked}
          </option>
          <option value="made_to_order">{labels.fulfilmentMadeToOrder}</option>
        </Select>
      </FormField>

      {values.productClass === "E" ? (
        <p className="text-xs text-text-2" role="note">
          {labels.fulfilmentLockedHint}
        </p>
      ) : null}

      {values.fulfilmentMode === "made_to_order" ? (
        <FormField
          label={labels.leadTimeLabel}
          helpText={labels.leadTimeHelp}
          errorMessage={errors.lead_time_days}
        >
          <Input
            inputMode="numeric"
            min={1}
            max={365}
            step={1}
            value={values.leadTimeDays}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              handleChange({ leadTimeDays: event.target.value })
            }
          />
        </FormField>
      ) : null}

      {values.productClass === "E" ? (
        <FormField
          label={labels.capacityLabel}
          helpText={labels.capacityHelp}
          errorMessage={errors.vendor_capacity_per_week}
        >
          <Input
            inputMode="numeric"
            min={1}
            max={9_999}
            step={1}
            value={values.vendorCapacityPerWeek}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              handleChange({ vendorCapacityPerWeek: event.target.value })
            }
          />
        </FormField>
      ) : null}

      {!inventoryReadOnly ? (
        <>
          <FormField label={labels.stockModeLabel} errorMessage={errors.stock_mode}>
            <Select
              value={values.stockMode}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                handleChange({ stockMode: event.target.value as StockMode })
              }
            >
              <option value="tracked" disabled={values.productClass === "E"}>
                {labels.stockTracked}
              </option>
              <option value="always_available">{labels.stockAlways}</option>
            </Select>
          </FormField>

          {values.productClass === "E" ? (
            <p className="text-xs text-text-2" role="note">
              {labels.stockLockedHint}
            </p>
          ) : null}

          {values.stockMode === "tracked" ? (
            <FormField label={labels.stockQtyLabel} errorMessage={errors.stock_qty}>
              <Input
                inputMode="numeric"
                min={0}
                step={1}
                value={values.stockQty}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  handleChange({ stockQty: event.target.value })
                }
              />
            </FormField>
          ) : null}
        </>
      ) : null}

      <FormField
        asGroup
        label={labels.fulfilmentOptionsLabel}
        helpText={labels.fulfilmentOptionsHelp}
        errorMessage={errors.fulfilment_options}
      >
        <div className="flex flex-col">
          {FULFILMENT_OPTIONS.map((option) => (
            <Checkbox
              key={option}
              label={
                option === "lusaka_delivery"
                  ? labels.optionLusakaDelivery
                  : option === "pickup_shop"
                    ? labels.optionPickupShop
                    : labels.optionPickupNationwide
              }
              checked={values.fulfilmentOptions.includes(option)}
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const next = event.target.checked
                  ? [...values.fulfilmentOptions, option]
                  : values.fulfilmentOptions.filter((current) => current !== option);
                handleChange({
                  fulfilmentOptions: FULFILMENT_OPTIONS.filter((candidate) =>
                    next.includes(candidate),
                  ),
                });
              }}
            />
          ))}
        </div>
      </FormField>

      {wholesaleEnabled && values.saleUnit === "each" ? (
        <section
          id="wholesale"
          className="space-y-3 rounded-lg border border-border p-3"
          aria-labelledby="listing-wholesale-heading"
        >
          <div className="space-y-1">
            <h3 id="listing-wholesale-heading" className="font-display text-h4 text-display-ink">
              {labels.wholesaleSectionHeading}
            </h3>
            <p className="text-xs text-text-2">{labels.wholesaleBuyersHint}</p>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-text">{labels.wholesaleLabel}</p>
              <p className="text-xs text-text-2">{labels.wholesaleHelp}</p>
            </div>
            <Switch
              label={labels.wholesaleLabel}
              checked={values.wholesale}
              onChange={(event) => handleChange({ wholesale: event.target.checked })}
            />
          </div>
          {values.wholesale ? (
            <FormField label={labels.moqLabel} errorMessage={errors.moq}>
              <Input
                inputMode="numeric"
                min={1}
                step={1}
                value={values.moq}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  handleChange({ moq: event.target.value })
                }
              />
            </FormField>
          ) : null}
        </section>
      ) : wholesaleEnabled && values.saleUnit !== "each" ? (
        <p className="text-xs text-text-2" role="note">
          {labels.wholesaleMeasureUnavailable}
        </p>
      ) : null}
    </div>
  );
}
