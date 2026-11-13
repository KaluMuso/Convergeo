/**
 * Maps `POST /tickets/verify` failures onto the organiser scanner's result
 * flash kinds.
 *
 * Every branch here is a *server* verdict being reported honestly to the door
 * staff: the browser never decides that a ticket is (or is not) checked in. In
 * particular `ticket_invalid_pin` and `ticket_already_checked_in` map to their
 * own kinds rather than the generic `rejected` one, because `rejected` is the
 * only kind that offers the organiser-override form — a wrong PIN or a
 * spent single-use ticket must never be overridable straight from the failure.
 */

import type { ScanResultKind } from "../_components/scan-result-flash";

/** Error codes raised by `services/api/app/routers/ticket_verify.py`. */
const KIND_BY_ERROR_CODE: Record<string, ScanResultKind> = {
  // Single-use enforcement: the ticket was already spent (409).
  ticket_already_checked_in: "conflict",
  // Wrong PIN for a real ticket (422).
  ticket_invalid_pin: "invalid_pin",
  // Caller holds no SCAN_ROLES membership on this event, or the ticket belongs
  // to another organiser (403).
  forbidden: "unauthorized",
  // No such ticket, or no such event (404).
  not_found: "unknown_ticket",
};

export function manualVerifyErrorKind(code: string | undefined): ScanResultKind {
  if (!code) {
    return "rejected";
  }
  return KIND_BY_ERROR_CODE[code] ?? "rejected";
}
