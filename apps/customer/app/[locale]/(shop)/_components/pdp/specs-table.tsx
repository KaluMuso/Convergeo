export type SpecRow = {
  key: string;
  value: string;
};

export type SpecsTableProps = {
  rows: SpecRow[];
  heading: string;
  emptyLabel: string;
  hideHeading?: boolean;
};

function formatSpecKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function SpecsTable({ rows, heading, emptyLabel, hideHeading = false }: SpecsTableProps) {
  return (
    <section data-testid="pdp-specs-table" className="flex flex-col gap-3">
      {hideHeading ? null : (
        <h2 className="font-display text-lg font-semibold text-text">{heading}</h2>
      )}

      {rows.length === 0 ? (
        <p className="text-sm text-text-3">{emptyLabel}</p>
      ) : (
        <dl className="overflow-hidden rounded border border-border bg-surface">
          {rows.map((row) => (
            <div
              key={row.key}
              className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 border-b border-border px-3 py-2 text-sm last:border-b-0"
            >
              <dt className="min-w-0 break-words font-medium text-text-2">
                {formatSpecKey(row.key)}
              </dt>
              <dd className="min-w-0 whitespace-pre-wrap break-words text-text [overflow-wrap:anywhere]">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export function specRowsFromJson(spec: Record<string, unknown>): SpecRow[] {
  return Object.entries(spec).flatMap(([key, value]) => {
    if (!key.trim() || value === null || value === undefined) return [];
    const text = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
    return text.trim() ? [{ key, value: text }] : [];
  });
}
