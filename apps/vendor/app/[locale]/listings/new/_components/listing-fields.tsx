"use client";

import { isValidZmwDecimal, zmwDecimalToNgwee } from "../_lib/money";
import { FormField, Input, Select, Switch } from "../_lib/ui";

import type { ListingCondition, StockMode } from "../_lib/types";
import type { ChangeEvent } from "react";

export type ListingFieldValues = {
  priceZmw: string;
  condition: ListingCondition;
  stockMode: StockMode;
  stockQty: string;
  wholesale: boolean;
  moq: string;
};

type ListingFieldsProps = {
  values: ListingFieldValues;
  onChange: (patch: Partial<ListingFieldValues>) => void;
  wholesaleEnabled: boolean;
  labels: {
    priceLabel: string;
    pricePlaceholder: string;
    priceHelp: string;
    priceInvalid: string;
    conditionLabel: string;
    conditionNew: string;
    conditionRefurbished: string;
    stockModeLabel: string;
    stockTracked: string;
    stockAlways: string;
    stockQtyLabel: string;
    wholesaleLabel: string;
    wholesaleHelp: string;
    moqLabel: string;
    required: string;
  };
};

export function parseListingFieldValues(values: ListingFieldValues): {
  priceNgwee: number;
  stockQty: number | null;
  moq: number;
} {
  return {
    priceNgwee: zmwDecimalToNgwee(values.priceZmw),
    stockQty: values.stockMode === "tracked" ? Number(values.stockQty) : null,
    moq: values.wholesale ? Number(values.moq) : 1,
  };
}

export function validateListingFields(
  values: ListingFieldValues,
  labels: ListingFieldsProps["labels"],
): string | null {
  if (!isValidZmwDecimal(values.priceZmw)) {
    return labels.priceInvalid;
  }
  if (values.stockMode === "tracked" && (!values.stockQty || Number(values.stockQty) < 0)) {
    return labels.required;
  }
  if (values.wholesale && (!values.moq || Number(values.moq) < 1)) {
    return labels.required;
  }
  return null;
}

export function ListingFields({ values, onChange, wholesaleEnabled, labels }: ListingFieldsProps) {
  const priceError =
    values.priceZmw && !isValidZmwDecimal(values.priceZmw) ? labels.priceInvalid : undefined;

  return (
    <div className="flex flex-col gap-4">
      <FormField label={labels.priceLabel} helpText={labels.priceHelp} errorMessage={priceError}>
        <Input
          inputMode="decimal"
          placeholder={labels.pricePlaceholder}
          value={values.priceZmw}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            onChange({ priceZmw: event.target.value })
          }
          error={Boolean(priceError)}
        />
      </FormField>

      <FormField label={labels.conditionLabel}>
        <Select
          value={values.condition}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onChange({ condition: event.target.value as ListingCondition })
          }
        >
          <option value="new">{labels.conditionNew}</option>
          <option value="refurbished">{labels.conditionRefurbished}</option>
        </Select>
      </FormField>

      <FormField label={labels.stockModeLabel}>
        <Select
          value={values.stockMode}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            onChange({ stockMode: event.target.value as StockMode })
          }
        >
          <option value="tracked">{labels.stockTracked}</option>
          <option value="always_available">{labels.stockAlways}</option>
        </Select>
      </FormField>

      {values.stockMode === "tracked" ? (
        <FormField label={labels.stockQtyLabel}>
          <Input
            inputMode="numeric"
            value={values.stockQty}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              onChange({ stockQty: event.target.value })
            }
          />
        </FormField>
      ) : null}

      {wholesaleEnabled ? (
        <div className="space-y-3 rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-text">{labels.wholesaleLabel}</p>
              <p className="text-xs text-text-2">{labels.wholesaleHelp}</p>
            </div>
            <Switch
              label={labels.wholesaleLabel}
              checked={values.wholesale}
              onChange={(event) => onChange({ wholesale: event.target.checked })}
            />
          </div>
          {values.wholesale ? (
            <FormField label={labels.moqLabel}>
              <Input
                inputMode="numeric"
                value={values.moq}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  onChange({ moq: event.target.value })
                }
              />
            </FormField>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
