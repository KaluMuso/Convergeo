const UNIT_DECIMAL_PATTERN = /^(0|[1-9]\d*)(?:\.(\d{1,3}))?$/;

export function isValidUnitDecimal(value: string): boolean {
  if (!UNIT_DECIMAL_PATTERN.test(value.trim())) {
    return false;
  }
  try {
    return unitDecimalToMilli(value) > 0;
  } catch {
    return false;
  }
}

/** Convert a unit decimal to thousandths using string arithmetic (never a float). */
export function unitDecimalToMilli(value: string): number {
  const trimmed = value.trim();
  const match = UNIT_DECIMAL_PATTERN.exec(trimmed);
  if (!match) {
    throw new Error("Invalid unit decimal");
  }

  const [whole = "0", fraction = ""] = trimmed.split(".");
  const milli = Number(whole) * 1_000 + Number(fraction.padEnd(3, "0"));
  if (!Number.isSafeInteger(milli)) {
    throw new Error("Unit decimal is too large");
  }
  return milli;
}

export function milliToUnitInput(value: number): string {
  if (!Number.isSafeInteger(value) || value < 1) {
    return "1";
  }
  const whole = Math.floor(value / 1_000);
  const fraction = String(value % 1_000)
    .padStart(3, "0")
    .replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}
