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

/**
 * Spoken-style lead time templates (`{count}` placeholder), one per form that
 * {@link describeLeadTime} can return. Resolved from `*.leadTime.when.*` messages.
 */
export type LeadTimePhrases = {
  oneDay: string;
  days: string;
  oneWeek: string;
  weeks: string;
  oneMonth: string;
  months: string;
};

export type LeadTimeForm = keyof LeadTimePhrases;

/**
 * Express a lead time in words rather than a raw day count: 1 day = "within a day",
 * 7 days = "within a week", whole weeks / months round to "about N weeks / months",
 * anything else stays an honest "about N days".
 */
export function describeLeadTime(days: number): { form: LeadTimeForm; count: number } {
  const whole = Math.max(1, Math.round(days));
  if (whole === 1) return { form: "oneDay", count: 1 };
  if (whole === 7) return { form: "oneWeek", count: 1 };
  if (whole === 30) return { form: "oneMonth", count: 1 };
  if (whole % 30 === 0 && whole > 30) return { form: "months", count: whole / 30 };
  if (whole % 7 === 0 && whole > 7 && whole < 30) return { form: "weeks", count: whole / 7 };
  return { form: "days", count: whole };
}

/** Build {@link LeadTimePhrases} from a raw-message reader (`form` → template). */
export function readLeadTimePhrases(read: (form: LeadTimeForm) => string): LeadTimePhrases {
  return {
    oneDay: read("oneDay"),
    days: read("days"),
    oneWeek: read("oneWeek"),
    weeks: read("weeks"),
    oneMonth: read("oneMonth"),
    months: read("months"),
  };
}

/** "Made to order · ready {when}" badge template plus its spoken lead-time phrases. */
export type MadeToOrderLabels = {
  badge: string;
  when: LeadTimePhrases;
};

/** Badge text for a made-to-order listing; null when it is not made to order. */
export function formatMadeToOrderBadge(
  fulfilmentMode: string | null | undefined,
  leadTimeDays: number | null | undefined,
  labels: MadeToOrderLabels,
): string | null {
  return formatMadeToOrderLeadTime(fulfilmentMode, leadTimeDays, labels.badge, labels.when);
}

export function formatLeadTimeWhen(days: number, phrases: LeadTimePhrases): string {
  const { form, count } = describeLeadTime(days);
  return phrases[form].replace("{count}", String(count));
}

/**
 * "Made to order · ready within a week". `template` carries `{when}` (spoken form,
 * needs `phrases`) or the legacy `{days}` placeholder (raw day count).
 */
export function formatMadeToOrderLeadTime(
  fulfilmentMode: string | null | undefined,
  leadTimeDays: number | null | undefined,
  template: string,
  phrases?: LeadTimePhrases,
): string | null {
  if (
    fulfilmentMode !== "made_to_order" ||
    !Number.isSafeInteger(leadTimeDays) ||
    (leadTimeDays ?? 0) <= 0
  ) {
    return null;
  }

  const days = leadTimeDays as number;
  const when = phrases ? formatLeadTimeWhen(days, phrases) : `${days}`;
  return template.replace("{when}", when).replace("{days}", String(days));
}

/** "Made to order · ready within a week" from `catalog.madeToOrder.*` messages. */
export function translateMadeToOrder(
  t: (key: string, values?: Record<string, string | number>) => string,
  days: number,
): string {
  const { form, count } = describeLeadTime(days);
  return t("madeToOrder.badge", { when: t(`madeToOrder.when.${form}`, { count }) });
}
