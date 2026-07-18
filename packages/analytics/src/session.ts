/**
 * Opaque anonymous session id for the server beacon.
 *
 * A random, non-PII, first-party identifier that lets the server stitch a
 * visitor's events together (and, once they authenticate, link the session to a
 * user id — the forward stitch done by the ingest endpoint). It is NOT a device
 * fingerprint and carries no personal data.
 *
 * Stored in `localStorage` (data-frugal — it is sent inside the beacon body, so it
 * never rides on every request the way a cookie would). When storage is unavailable
 * (private mode / disabled), we fall back to a per-tab in-memory id so a beacon still
 * carries a stable id within the page's lifetime. SSR-safe: returns null on the server.
 */

const SESSION_KEY = "vg_session_id";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let memoryId: string | null = null;

/** A v4-shaped opaque id — `crypto.randomUUID` when available, else a simple shim. */
function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Rare fallback (very old browsers without crypto.randomUUID). This id is an opaque
  // grouping key, never a secret, so a non-cryptographic source is acceptable here.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const rand = Math.floor(Math.random() * 16);
    const value = char === "x" ? rand : (rand & 0x3) | 0x8;
    return value.toString(16);
  });
}

/**
 * The current visitor's opaque session id, creating and persisting one on first use.
 * Returns `null` during SSR (no browser storage). Stable across page loads within a
 * browser; a fresh id after storage is cleared.
 */
export function getSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const existing = window.localStorage.getItem(SESSION_KEY);
    if (existing && UUID_RE.test(existing)) {
      return existing;
    }
    const fresh = generateId();
    window.localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    // localStorage blocked/disabled — stable per-tab fallback for this page's lifetime.
    memoryId = memoryId ?? generateId();
    return memoryId;
  }
}

/** Test-only: reset the in-memory fallback id. */
export function __resetSessionMemory(): void {
  memoryId = null;
}
