/**
 * Customer-facing title for a cart / checkout line.
 *
 * The API resolves `title_override` -> product name; this only guards the
 * remaining case (neither exists) so the UI never shows the raw listing UUID.
 * `fallback` must be a translated string (e.g. `cart.untitledItem`).
 */
export function cartLineTitle(item: { title_override?: string | null }, fallback?: string): string {
  const title = item.title_override?.trim();
  if (title) {
    return title;
  }
  return fallback?.trim() || "—";
}
