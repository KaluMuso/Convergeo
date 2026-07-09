export type SpecRow = {
  key: string;
  value: string;
};

export type SpecsTableProps = {
  rows: SpecRow[];
  heading: string;
  emptyLabel: string;
};

function formatSpecKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function SpecsTable({ rows, heading, emptyLabel }: SpecsTableProps) {
  return (
    <section data-testid="pdp-specs-table" className="flex flex-col gap-3">
      <h2 className="font-display text-lg font-semibold text-text">{heading}</h2>

      {rows.length === 0 ? (
        <p className="text-sm text-text-3">{emptyLabel}</p>
      ) : (
        <dl className="overflow-hidden rounded border border-border bg-surface">
          {rows.map((row) => (
            <div
              key={row.key}
              className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3 border-b border-border px-3 py-2 text-sm last:border-b-0"
            >
              <dt className="font-medium text-text-2">{formatSpecKey(row.key)}</dt>
              <dd className="text-text">{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export function specRowsFromJson(spec: Record<string, unknown>): SpecRow[] {
  return Object.entries(spec)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
    .map(([key, value]) => ({
      key,
      value: String(value),
    }));
}
