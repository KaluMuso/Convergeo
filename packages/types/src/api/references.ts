/** Lenco / platform reference charset: `[-._A-Za-z0-9]` */

export type ReferenceCharset = string & { readonly __brand: "reference_charset" };

export type OrderReference = `ord-${string}` & { readonly __brand: "order_reference" };
export type PaymentReference = `pay-${string}` & { readonly __brand: "payment_reference" };
export type RefundReference = `rfd-${string}` & { readonly __brand: "refund_reference" };

const REFERENCE_RE = /^[-._A-Za-z0-9]+$/;

function assertReferenceSuffix(prefix: string, value: string): string {
  if (!value.startsWith(prefix)) {
    throw new Error(`reference must start with ${prefix}`);
  }
  const suffix = value.slice(prefix.length);
  if (!suffix || !REFERENCE_RE.test(suffix)) {
    throw new Error("reference suffix has invalid charset");
  }
  return value;
}

export function asOrderReference(value: string): OrderReference {
  return assertReferenceSuffix("ord-", value) as OrderReference;
}

export function asPaymentReference(value: string): PaymentReference {
  return assertReferenceSuffix("pay-", value) as PaymentReference;
}

export function asRefundReference(value: string): RefundReference {
  return assertReferenceSuffix("rfd-", value) as RefundReference;
}
