/**
 * Analytics v2 identifiers (plan §R-A / §R-B). Browser-only, SSR-safe, never throws.
 *
 * - `anon_id`  — pseudonymous visitor id (localStorage `vg_anon_id`). Seeded ONCE from the
 *   legacy v1 `vg_session_id` so existing visitors are not re-counted as new; deleted
 *   (rotated) when the visitor opts out.
 * - `session`  — rotating journey id (localStorage `vg_sess2` = `{id,last,seq}`). A new one
 *   starts after 30 minutes of inactivity. We never record an exit: the session end is
 *   always an ESTIMATE derived server-side from the last event.
 * - Counts-only mode — consent cookie `denied` or Global Privacy Control: no identifier is
 *   sent; events still carry an unlinkable `event_id` so counts stay deduplicated.
 *
 * No fingerprinting: no UA, screen, IP, raw referrer or URL ever leaves the browser.
 */

import { getAnalyticsConsent, isGlobalPrivacyControlOn } from "../consent";

export const ANON_KEY = "vg_anon_id";
export const SESSION_KEY_V2 = "vg_sess2";
const LEGACY_KEY = "vg_session_id";
export const SESSION_IDLE_MS = 30 * 60 * 1000;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface SessionState {
  id: string;
  last: number;
  seq: number;
}

let memorySession: SessionState | null = null;
let memoryAnon: string | null = null;

/** Random UUIDv4 (crypto when available; opaque grouping key, never a secret). */
export function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage blocked — memory fallback keeps ids stable for this page
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

/** Opt-out (consent cookie `denied`) or Global Privacy Control ⇒ counts-only. */
export function isCountsOnly(): boolean {
  if (getAnalyticsConsent() === "denied") {
    return true;
  }
  return isGlobalPrivacyControlOn();
}

/** Visitor id, created on first use (seeded from the legacy v1 id). Null during SSR. */
export function getAnonId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = read(ANON_KEY);
  if (stored && UUID_RE.test(stored)) {
    return stored;
  }
  const legacy = read(LEGACY_KEY);
  const fresh = memoryAnon ?? (legacy && UUID_RE.test(legacy) ? legacy : newId());
  memoryAnon = fresh;
  write(ANON_KEY, fresh);
  return fresh;
}

/** Forget the visitor id (opt-out). Opting back in yields a NEW, unlinked id. */
export function forgetAnonId(): void {
  memoryAnon = null;
  if (typeof window !== "undefined") {
    remove(ANON_KEY);
  }
}

function loadSession(): SessionState | null {
  const raw = read(SESSION_KEY_V2);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<SessionState>;
      if (
        typeof parsed.id === "string" &&
        UUID_RE.test(parsed.id) &&
        typeof parsed.last === "number" &&
        typeof parsed.seq === "number"
      ) {
        return { id: parsed.id, last: parsed.last, seq: parsed.seq };
      }
    } catch {
      // malformed — fall through
    }
  }
  return memorySession;
}

export interface SessionTouch {
  id: string;
  seq: number;
  isNew: boolean;
}

/**
 * Register activity at `now`: rotates the session after 30 min idle and returns the
 * next sequence number. `reserve` sequence numbers are consumed (session_start + event).
 */
export function touchSession(now: number, reserve = 1): SessionTouch | null {
  if (typeof window === "undefined") {
    return null;
  }
  const current = loadSession();
  const isNew =
    current === null || now - current.last > SESSION_IDLE_MS || now < current.last - 60_000;
  const state: SessionState = isNew
    ? { id: newId(), last: now, seq: 0 }
    : { id: current.id, last: now, seq: current.seq };
  const seq = state.seq;
  state.seq += reserve;
  memorySession = state;
  write(SESSION_KEY_V2, JSON.stringify(state));
  return { id: state.id, seq, isNew };
}

/** Current session id without registering activity (used when flushing). */
export function currentSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return loadSession()?.id ?? null;
}

/** Test-only: reset in-memory fallbacks. */
export function __resetIdsMemory(): void {
  memorySession = null;
  memoryAnon = null;
}
