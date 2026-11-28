/**
 * Render a catalogue spec value (the API sends free-form JSON) as plain text.
 * Arrays and nested objects must never reach the page via String(), which
 * prints "[object Object]".
 */
export function formatSpecValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    return value
      .map((item) => formatSpecValue(item))
      .filter((text) => text !== "")
      .join(", ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, inner]) => `${key}: ${formatSpecValue(inner)}`)
      .join(", ");
  }
  return String(value);
}
