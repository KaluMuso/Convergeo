/**
 * Demo inventory signals for honest disclosure (CUST-HOME-01 / CUST-02).
 * Only label listings when media public IDs prove the `demo/` seed prefix.
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
