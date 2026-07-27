/**
 * M17-P04 — byte-size formatting for the D-V5 honesty chip.
 *
 * Deliberately coarse: "~2 MB" is what a person can act on before spending their
 * bundle. Reporting "1.93 MB" would be more precise and less useful, and the
 * number is an approximation of a transcoded file anyway.
 */

import type { Clip, ClipRendition } from "./types";

const BYTES_PER_MB = 1_048_576;
const BYTES_PER_KB = 1024;

export type FormattedSize = { unit: "MB" | "KB"; value: string };

export function formatBytes(bytes: number | null | undefined): FormattedSize | null {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) {
    return null;
  }
  if (bytes >= BYTES_PER_MB) {
    const mb = bytes / BYTES_PER_MB;
    // One decimal below 10 MB, none above: "1.9 MB" is useful, "12.4 MB" is noise.
    return { unit: "MB", value: mb < 10 ? mb.toFixed(1) : String(Math.round(mb)) };
  }
  return { unit: "KB", value: String(Math.round(bytes / BYTES_PER_KB)) };
}

/** The rendition we would actually fetch, falling back to whatever exists. */
export function pickRendition(clip: Clip, preferred: string): ClipRendition | null {
  const exact = clip.renditions?.[preferred];
  if (exact) {
    return exact;
  }
  const available = Object.values(clip.renditions ?? {});
  if (available.length === 0) {
    return null;
  }
  // Smallest available: when the preferred ceiling is missing, err toward the
  // cheaper file rather than surprising someone with the larger one.
  return available.reduce((smallest, current) =>
    (current.bytes ?? Number.MAX_SAFE_INTEGER) < (smallest.bytes ?? Number.MAX_SAFE_INTEGER)
      ? current
      : smallest,
  );
}
