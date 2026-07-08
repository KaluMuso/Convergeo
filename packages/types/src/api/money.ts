/**
 * Money amounts in API payloads are integer ngwee (1 ZMW = 100 ngwee).
 * Never use floating-point for money — display via formatK() on the client.
 */
export type Ngwee = number & { readonly __brand: "ngwee" };

/** Helper to document ngwee ints at API boundaries (no runtime coercion). */
export function asNgwee(value: number): Ngwee {
  if (!Number.isInteger(value)) {
    throw new TypeError("ngwee must be an integer");
  }
  if (value < 0) {
    throw new RangeError("ngwee must be non-negative");
  }
  return value as Ngwee;
}

export type MoneyFields = {
  amount_ngwee: Ngwee;
};
