import { isValidZmwDecimal, zmwDecimalToNgwee } from "../../../../listings/new/_lib/money";

export { isValidZmwDecimal, zmwDecimalToNgwee };

export function ngweeToZmwInput(ngwee: number): string {
  const major = Math.trunc(ngwee / 100);
  const minor = Math.abs(ngwee % 100);
  return `${major}.${minor.toString().padStart(2, "0")}`;
}

export function isValidFreePrice(input: string): boolean {
  const cleaned = input.replace(/,/g, "").trim();
  return cleaned === "0" || cleaned === "0.00" || cleaned === "0.0";
}

export function isValidPaidPrice(input: string): boolean {
  try {
    return zmwDecimalToNgwee(input) > 0;
  } catch {
    return false;
  }
}
