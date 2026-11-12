/**
 * Best-effort reader for the plain-text courier message served by
 * GET /admin/dispatch/requests/{id}/message (services/dispatch/message.py).
 * The order endpoint carries no address, so this is the only existing source of
 * landmark + GPS. Anything that does not parse is simply left out.
 */
export type ParsedPlace = {
  /** Full line as the rider sees it. */
  line: string;
  /** Address / landmark text without the GPS link. */
  text: string;
  mapsUrl: string | null;
};

export type ParsedCourierMessage = {
  pickup: ParsedPlace | null;
  dropoff: ParsedPlace | null;
  payment: string | null;
  contacts: string | null;
};

const GPS_RE = /\s*-?\s*GPS (https:\/\/maps\.google\.com\/\?q=-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?)/;

function parsePlace(line: string | undefined): ParsedPlace | null {
  if (!line) return null;
  const match = GPS_RE.exec(line);
  const text = (match ? line.replace(GPS_RE, "") : line).trim();
  return { line, text, mapsUrl: match?.[1] ?? null };
}

function field(lines: string[], label: string): string | undefined {
  const prefix = `${label}: `;
  const hit = lines.find((line) => line.startsWith(prefix));
  return hit?.slice(prefix.length).trim();
}

export function parseCourierMessage(text: string): ParsedCourierMessage {
  const lines = text.split(/\r?\n/);
  return {
    pickup: parsePlace(field(lines, "Pickup")),
    dropoff: parsePlace(field(lines, "Drop-off")),
    payment: field(lines, "Payment") ?? null,
    contacts: field(lines, "Contacts") ?? null,
  };
}
