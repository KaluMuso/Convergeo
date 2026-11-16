/**
 * Kwacha decimal string ("1,234.56") -> integer ngwee, without float arithmetic.
 * Returns null for anything that is not a positive amount with at most 2 decimals.
 */
export function kwachaToNgwee(input: string): number | null {
  const cleaned = input.replace(/,/g, "").trim();
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) {
    return null;
  }
  const ngwee = BigInt(match[1] ?? "0") * 100n + BigInt((match[2] ?? "00").padEnd(2, "0"));
  if (ngwee <= 0n || ngwee > BigInt(Number.MAX_SAFE_INTEGER)) {
    return null;
  }
  return Number(ngwee);
}

export const REPAYMENT_REFERENCE_PATTERN = /^[A-Za-z0-9._-]{3,80}$/;
