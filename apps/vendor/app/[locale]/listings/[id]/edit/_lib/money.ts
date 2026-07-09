export function ngweeToZmwInput(ngwee: number): string {
  const major = Math.trunc(ngwee / 100);
  const minor = Math.abs(ngwee % 100);
  return `${major}.${minor.toString().padStart(2, "0")}`;
}

export { isValidZmwDecimal, zmwDecimalToNgwee } from "../../../new/_lib/money";
