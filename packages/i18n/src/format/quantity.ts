const MILLIS_PER_UNIT = 1_000;

function assertSafeWholeNumber(value: number, name: string, minimum: number): void {
  if (!Number.isSafeInteger(value) || value < minimum) {
    throw new RangeError(`${name} must be a safe integer greater than or equal to ${minimum}`);
  }
}

function decimalSeparator(locale: string): string {
  return (
    new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === "decimal")
      ?.value ?? "."
  );
}

/**
 * Formats a listing quantity whose stored value is an integer number of sale steps.
 *
 * `unitStepMilli` is the size of one step in thousandths of the advertised unit.
 * The calculation stays in safe integers; locale-aware decimal text is assembled
 * only at the presentation edge so values such as 3 × 250 render exactly as 0.75.
 */
export function formatSaleQuantity(
  steps: number,
  unitStepMilli: number = MILLIS_PER_UNIT,
  locale = "en",
): string {
  assertSafeWholeNumber(steps, "steps", 0);
  assertSafeWholeNumber(unitStepMilli, "unitStepMilli", 1);

  const totalMilli = steps * unitStepMilli;
  if (!Number.isSafeInteger(totalMilli)) {
    throw new RangeError("sale quantity exceeds the safe integer range");
  }

  const wholeUnits = Math.floor(totalMilli / MILLIS_PER_UNIT);
  const remainderMilli = totalMilli % MILLIS_PER_UNIT;
  const whole = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(wholeUnits);

  if (remainderMilli === 0) {
    return whole;
  }

  const fraction = String(remainderMilli).padStart(3, "0").replace(/0+$/, "");
  return `${whole}${decimalSeparator(locale)}${fraction}`;
}
