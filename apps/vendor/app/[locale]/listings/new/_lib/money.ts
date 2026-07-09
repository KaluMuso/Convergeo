/**
 * Convert a ZMW decimal string (e.g. "1,234.56") to integer ngwee without float drift.
 */
export function zmwDecimalToNgwee(input: string): number {
  const cleaned = input.replace(/,/g, "").trim();
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) {
    throw new Error("invalid_zmw_decimal");
  }

  const major = BigInt(match[1] ?? "0");
  const minorPart = match[2] ?? "00";
  const minor = BigInt(minorPart.padEnd(2, "0"));
  const ngwee = major * 100n + minor;

  if (ngwee > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new Error("amount_too_large");
  }

  return Number(ngwee);
}

export function isValidZmwDecimal(input: string): boolean {
  try {
    const ngwee = zmwDecimalToNgwee(input);
    return ngwee > 0;
  } catch {
    return false;
  }
}
