/**
 * Server-safe gallery label strings for the PDP.
 *
 * Digests like 1378788464 happen when a Server Component passes a function
 * (e.g. `indicator: (current, total) => …`) into a Client Component prop tree.
 * Keep only serializable strings here; format runtime indicator text on the client.
 */
export type PdpGalleryLabelStrings = {
  empty: string;
  previous: string;
  next: string;
};

/** Format an ICU-style gallery indicator template with runtime indices. */
export function formatPdpGalleryIndicator(
  template: string,
  current: number,
  total: number,
): string {
  return template.replaceAll("{current}", String(current)).replaceAll("{total}", String(total));
}

/**
 * Guard used by tests (and callers) to catch RSC-unsafe function props.
 * Mirrors the live failure mode for digest 1378788464.
 */
export function assertRscSafeGalleryLabels(labels: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(labels)) {
    if (typeof value === "function") {
      throw new Error(
        `RSC-unsafe galleryLabels.${key}: functions cannot cross the client boundary (digest 1378788464)`,
      );
    }
  }
}
