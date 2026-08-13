import { formatSaleQuantity } from "@vergeo/i18n";

export const SALE_UNITS = ["each", "metre", "kg", "litre", "bag", "sqm"] as const;

export type SaleUnit = (typeof SALE_UNITS)[number];
export type SaleUnitLabels = Record<SaleUnit, string>;
export type FulfilmentMode = "stocked" | "made_to_order";

export function resolveSaleUnit(value: string | null | undefined): SaleUnit {
  return SALE_UNITS.includes(value as SaleUnit) ? (value as SaleUnit) : "each";
}

export function resolveUnitStepMilli(value: number | null | undefined): number {
  return Number.isSafeInteger(value) && (value ?? 0) > 0 ? (value as number) : 1_000;
}

export function resolveMinimumSteps(value: number | null | undefined): number {
  return Number.isSafeInteger(value) && (value ?? 0) > 0 ? (value as number) : 1;
}

export function catalogSaleUnitLabels(
  t: (key: string, values?: Record<string, string | number>) => string,
): SaleUnitLabels {
  return {
    each: t("pdp.buyBox.units.each"),
    metre: t("pdp.buyBox.units.metre"),
    kg: t("pdp.buyBox.units.kg"),
    litre: t("pdp.buyBox.units.litre"),
    bag: t("pdp.buyBox.units.bag"),
    sqm: t("pdp.buyBox.units.sqm"),
  };
}

export function formatListingQuantity(
  steps: number,
  saleUnit: string | null | undefined,
  unitStepMilli: number | null | undefined,
  locale: string,
  unitLabels: SaleUnitLabels,
): string {
  const unit = resolveSaleUnit(saleUnit);
  if (unit === "each") {
    return formatSaleQuantity(steps, 1_000, locale);
  }

  return `${formatSaleQuantity(steps, resolveUnitStepMilli(unitStepMilli), locale)} ${unitLabels[unit]}`;
}

export function formatSaleIncrement(
  saleUnit: string | null | undefined,
  unitStepMilli: number | null | undefined,
  locale: string,
  unitLabels: SaleUnitLabels,
): string {
  return formatListingQuantity(1, saleUnit, unitStepMilli, locale, unitLabels);
}

export function formatMadeToOrderLeadTime(
  fulfilmentMode: string | null | undefined,
  leadTimeDays: number | null | undefined,
  template: string,
): string | null {
  if (
    fulfilmentMode !== "made_to_order" ||
    !Number.isSafeInteger(leadTimeDays) ||
    (leadTimeDays ?? 0) <= 0
  ) {
    return null;
  }

  return template.replace("{days}", String(leadTimeDays));
}
