/** Names only: safe to include in gate annotations and CI failures. */
export function missingSandboxMomoEvidence(config: {
  enabled: boolean;
  publicKey: string;
  secretKey: string;
  testMomoNumber: string;
  environment: string;
}): string[] {
  const missing: string[] = [];
  if (!config.enabled) missing.push("LENCO_SANDBOX");
  if (!config.publicKey.trim()) missing.push("LENCO_SANDBOX_PUBLIC_KEY");
  if (!config.secretKey.trim()) missing.push("LENCO_SANDBOX_SECRET_KEY");
  if (config.environment.trim().toLowerCase() !== "sandbox") {
    missing.push("LENCO_ENV=sandbox");
  }
  if (!/^(?:\+260|0)?[79]\d{8}$/.test(config.testMomoNumber.trim())) {
    missing.push("LENCO_SANDBOX_MOMO_NUMBER");
  }
  return missing;
}

/** Keep the order-placement callback behind the same sandbox preflight. */
export async function runSandboxMomoCheckout<T>(
  config: Parameters<typeof missingSandboxMomoEvidence>[0],
  checkout: () => Promise<T>,
): Promise<T> {
  const missing = missingSandboxMomoEvidence(config);
  if (missing.length > 0) {
    throw new Error(`MoMo checkout requires sandbox evidence: ${missing.join(", ")}`);
  }
  return checkout();
}
