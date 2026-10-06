export type DetailEntry = { name: string; value: string };

/** Blank rows are optional; half-filled or duplicate rows must never silently overwrite details. */
export function buildCanonicalSpec(entries: DetailEntry[]): Record<string, string> | null {
  if (entries.length > 32) return null;
  const pairs: [string, string][] = [];
  const names = new Set<string>();
  for (const entry of entries) {
    const name = entry.name.trim();
    const value = entry.value.trim();
    if (!name && !value) continue;
    if (!name || !value || name.length > 80 || value.length > 2000 || names.has(name.toLowerCase()))
      return null;
    names.add(name.toLowerCase());
    pairs.push([name, value]);
  }
  const spec = Object.fromEntries(pairs);
  return new TextEncoder().encode(JSON.stringify(spec)).length > 32000 ? null : spec;
}
