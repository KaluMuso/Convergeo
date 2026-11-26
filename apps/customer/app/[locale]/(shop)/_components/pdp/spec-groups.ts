import type { SpecRow } from "./specs-table";

export type SpecGroup = {
  id: string;
  title: string;
  rows: SpecRow[];
};

export function groupSpecRows(rows: SpecRow[], groupTitles: Record<string, string>): SpecGroup[] {
  const buckets = new Map<string, SpecRow[]>();
  const ungrouped: SpecRow[] = [];

  for (const row of rows) {
    const slash = row.key.indexOf("/");
    const dot = row.key.indexOf(".");
    const splitAt = slash > 0 ? slash : dot > 0 ? dot : -1;
    if (splitAt > 0) {
      const groupKey = row.key.slice(0, splitAt);
      const rest = row.key.slice(splitAt + 1);
      const list = buckets.get(groupKey) ?? [];
      list.push({ key: rest, value: row.value });
      buckets.set(groupKey, list);
    } else {
      ungrouped.push(row);
    }
  }

  const groups: SpecGroup[] = [];
  for (const [id, groupRows] of buckets) {
    if (groupRows.length === 0) {
      continue;
    }
    groups.push({
      id,
      title: groupTitles[id] ?? formatSpecKey(id),
      rows: groupRows,
    });
  }
  if (ungrouped.length > 0) {
    groups.push({
      id: "details",
      title: groupTitles.details ?? "Item details",
      rows: ungrouped,
    });
  }
  return groups;
}

export function formatSpecKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
