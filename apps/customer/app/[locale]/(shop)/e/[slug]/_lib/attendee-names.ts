/**
 * Attendee-name capture helpers for the ticket picker (M10-P11). When a ticket
 * type is `attendee_named`, the buyer must supply one name per ticket; the server
 * enforces this in purchase._validate_attendee_names, and these keep the client
 * inputs in sync with the chosen quantity and gate submission until all are filled.
 */

/** Resize `names` to exactly `qty` entries — truncating extras, padding with "". */
export function resizeNames(names: string[], qty: number): string[] {
  const target = Math.max(0, qty);
  const next = names.slice(0, target);
  while (next.length < target) {
    next.push("");
  }
  return next;
}

/** True when there is exactly one non-blank name for each of the `qty` tickets. */
export function attendeeNamesComplete(names: string[], qty: number): boolean {
  if (qty < 1) {
    return false;
  }
  const resized = resizeNames(names, qty);
  return resized.every((name) => name.trim().length > 0);
}

/** The trimmed names to send to the API (exactly `qty` entries). */
export function cleanedAttendeeNames(names: string[], qty: number): string[] {
  return resizeNames(names, qty).map((name) => name.trim());
}
