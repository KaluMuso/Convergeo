"use client";

import { isValidUnitDecimal, unitDecimalToMilli } from "../_lib/measure";
import { isValidZmwDecimal, zmwDecimalToNgwee } from "../_lib/money";
import { FormField, Input, Select, Switch, Textarea } from "../_lib/ui";

import type {
  FulfilmentMode,
  ListingCondition,
  ConditionDetail,
  PricingMode,
  ProductClass,
  SaleUnit,
  StockMode,
} from "../_lib/types";
import type { ChangeEvent } from "react";

export type ListingFieldValues = {
  priceZmw: string;
  productClass: ProductClass;
  saleUnit: SaleUnit;
  unitStep: string;
  minSteps: string;
  condition: ListingCondition;
  conditionDetail: ConditionDetail;
  pricingMode: PricingMode;
  defectNotes: string;
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
  conditionDetail: "new",
  pricingMode: "fixed",
  defectNotes: "",
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
  conditionDetailLabel: string;
  conditionOpenBox: string;
  conditionUsedExcellent: string;
  conditionUsedGood: string;
  conditionUsedFair: string;
  conditionParts: string;
  pricingModeLabel: string;
  pricingFixed: string;
  pricingMeasured: string;
  pricingBundle: string;
  pricingTiered: string;
  pricingRange: string;
  pricingFrom: string;
  pricingQuoteOnly: string;
  pricingQuoteHelp: string;
  defectNotesLabel: string;
  defectNotesPlaceholder: string;
  defectNotesHelp: string;
  defectNotesInvalid: string;
  fulfilmentLabel: string;
  fulfilmentStocked: string;
  fulfilmentMadeToOrder: string;
  leadTimeLabel: string;
  leadTimeHelp: string;
  leadTimeInvalid: string;
  capacityLabel: string;
  capacityHelp: string;
  capacityInvalid: string;
  stockModeLabel: string;
  stockTracked: string;
  stockAlways: string;
  stockQtyLabel: string;
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
  if (patch.condition === "new") {
    next.conditionDetail = "new";
  } else if (patch.condition === "refurbished") {
    next.conditionDetail = next.conditionDetail === "open_box" ? "open_box" : "refurbished";
  } else if (patch.condition === "used") {
    if (
      next.conditionDetail === "new" ||
      next.conditionDetail === "open_box" ||
      next.conditionDetail === "refurbished"
    ) {
      next.conditionDetail = "used_good";
    }
  }
  if (patch.fulfilmentMode === "stocked") {
    next.leadTimeDays = "";
  }
  if (patch.productClass && patch.productClass !== "E") {
    next.vendorCapacityPerWeek = "";
  }

  if (next.productClass === "D") {
    next.condition = "used";
    if (
      next.conditionDetail === "new" ||
      next.conditionDetail === "open_box" ||
      next.conditionDetail === "refurbished"
    ) {
      next.conditionDetail = "used_good";
    }
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

export function requiresListingEvidence(values: ListingFieldValues): boolean {
  return values.productClass === "D" || values.condition === "used";
}

export function parseListingFieldValues(values: ListingFieldValues): {
  priceNgwee: number;
  unitStepMilli: number;
  minSteps: number;
  defectNotes: string | null;
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
  if (values.productClass === "D" && values.condition !== "used") {
    return labels.defectNotesInvalid;
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
  return null;
}

export function ListingFields({
  values,
  onChange,
  wholesaleEnabled,
  labels,
  allowStandaloneClasses = true,
}: ListingFieldsProps) {
  const priceError =
    values.priceZmw && !isValidZmwDecimal(values.priceZmw) ? labels.priceInvalid : undefined;
  const evidenceRequired = requiresListingEvidence(values);
  const handleChange = (patch: Partial<ListingFieldValues>) => {
    onChange(applyListingFieldPatch(values, patch));
  };

  return (
    <div className="flex flex-col gap-4">
      <FormField label={labels.productClassLabel}>
        <Select
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

      <FormField label={labels.saleUnitLabel}>
        <Select
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
          <FormField label={labels.unitStepLabel} helpText={labels.unitStepHelp}>
            <Input
              inputMode="decimal"
              value={values.unitStep}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                handleChange({ unitStep: event.target.value })
              }
            />
          </FormField>
          <FormField label={labels.minStepsLabel}>
            <Input
              inputMode="numeric"
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

      <FormField label={labels.conditionLabel}>
        <Select
          value={values.condition}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ condition: event.target.value as ListingCondition })
          }
        >
          <option value="new" disabled={values.productClass === "D"}>
            {labels.conditionNew}
          </option>
          <option value="refurbished" disabled={values.productClass === "D"}>
            {labels.conditionRefurbished}
          </option>
          <option value="used">{labels.conditionUsed}</option>
        </Select>
      </FormField>

      <FormField label={labels.conditionDetailLabel}>
        <Select
          value={values.conditionDetail}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ conditionDetail: event.target.value as ConditionDetail })
          }
        >
          {values.condition === "new" ? <option value="new">{labels.conditionNew}</option> : null}
          {values.condition === "refurbished" ? (
            <>
              <option value="open_box">{labels.conditionOpenBox}</option>
              <option value="refurbished">{labels.conditionRefurbished}</option>
            </>
          ) : null}
          {values.condition === "used" ? (
            <>
              <option value="used_excellent">{labels.conditionUsedExcellent}</option>
              <option value="used_good">{labels.conditionUsedGood}</option>
              <option value="used_fair">{labels.conditionUsedFair}</option>
              <option value="parts_not_working">{labels.conditionParts}</option>
            </>
          ) : null}
        </Select>
      </FormField>

      <FormField
        label={labels.pricingModeLabel}
        helpText={
          values.pricingMode === "quote_only" || values.pricingMode === "range"
            ? labels.pricingQuoteHelp
            : undefined
        }
      >
        <Select
          value={values.pricingMode}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ pricingMode: event.target.value as PricingMode })
          }
        >
          <option value="fixed">{labels.pricingFixed}</option>
          <option value="measured">{labels.pricingMeasured}</option>
          <option value="bundle">{labels.pricingBundle}</option>
          <option value="tiered">{labels.pricingTiered}</option>
          <option value="range">{labels.pricingRange}</option>
          <option value="from">{labels.pricingFrom}</option>
          <option value="quote_only">{labels.pricingQuoteOnly}</option>
        </Select>
      </FormField>

      {values.condition === "used" ? (
        <FormField label={labels.defectNotesLabel} helpText={labels.defectNotesHelp}>
          <Textarea
            value={values.defectNotes}
            maxLength={2_000}
            placeholder={labels.defectNotesPlaceholder}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
              handleChange({ defectNotes: event.target.value })
            }
          />
        </FormField>
      ) : null}

      {evidenceRequired ? (
        <p
          className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-text"
          role="note"
        >
          {labels.evidenceDraftNotice}
        </p>
      ) : null}

      <FormField label={labels.fulfilmentLabel}>
        <Select
          value={values.fulfilmentMode}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            handleChange({ fulfilmentMode: event.target.value as FulfilmentMode })
          }
        >
          <option value="stocked" disabled={values.productClass === "E"}>
            {labels.fulfilmentStocked}
          </option>
          <option value="made_to_order">{labels.fulfilmentMadeToOrder}</option>
        </Select>
      </FormField>

      {values.fulfilmentMode === "made_to_order" ? (
        <FormField label={labels.leadTimeLabel} helpText={labels.leadTimeHelp}>
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
        <FormField label={labels.capacityLabel} helpText={labels.capacityHelp}>
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

      <FormField label={labels.stockModeLabel}>
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

      {values.stockMode === "tracked" ? (
        <FormField label={labels.stockQtyLabel}>
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

      {wholesaleEnabled && values.saleUnit === "each" ? (
        <div className="space-y-3 rounded-lg border border-border p-3">
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
            <FormField label={labels.moqLabel}>
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
        </div>
      ) : wholesaleEnabled && values.saleUnit !== "each" ? (
        <p className="text-xs text-text-2" role="note">
          {labels.wholesaleMeasureUnavailable}
        </p>
      ) : null}
    </div>
  );
}
