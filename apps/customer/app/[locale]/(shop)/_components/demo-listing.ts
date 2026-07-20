/**
 * Demo inventory signals for honest disclosure (CUST-HOME-01 / CUST-02 / audit E07).
 * Only label listings when media public IDs prove the `demo/` seed prefix.
 * SAMPLE badges are hidden in production hosts unless explicitly re-enabled.
 */

export function isDemoListingPublicId(publicId: string | null | undefined): boolean {
  if (!publicId) {
    return false;
  }

  const normalized = publicId.trim().replace(/^\/+/, "").toLowerCase();
  if (normalized.length === 0) {
    return false;
  }

  return normalized === "demo" || normalized.startsWith("demo/") || normalized.includes("/demo/");
}

/**
 * Gate for Sample listing badges (audit E07 / §10 P0).
 *
 * - Hidden when `NODE_ENV === "production"` (default prod behaviour).
 * - Hidden when `NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS` is `"0"` / `"false"`.
 * - Shown in development/test, or when the public flag is `"1"` / `"true"`.
 */
export function shouldShowSampleListingBadge(env: NodeJS.ProcessEnv = process.env): boolean {
  const flag = env.NEXT_PUBLIC_SHOW_SAMPLE_LISTINGS?.trim().toLowerCase();
  if (flag === "0" || flag === "false") {
    return false;
  }
  if (flag === "1" || flag === "true") {
    return true;
  }
  return env.NODE_ENV !== "production";
}
