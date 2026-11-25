export type ValueTrustStripProps = {
  ariaLabel: string;
  escrow?: string;
  verified?: string;
  returns?: string;
  momoCod?: string;
};

type TrustKey = keyof Omit<ValueTrustStripProps, "ariaLabel">;

const GLYPHS: Record<TrustKey, string> = {
  escrow: "M6 10V8a6 6 0 1 1 12 0v2M5 10h14v10H5zM12 14v2.5",
  verified: "M12 3 4.5 6v5.5c0 4.4 3.1 8.2 7.5 9.5 4.4-1.3 7.5-5.1 7.5-9.5V6L12 3Zm-3 9 2 2 4-4.5",
  returns: "M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4",
  momoCod: "M3 7h18v10H3zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM6.5 10v4M17.5 10v4",
};

const TEST_IDS: Record<TrustKey, string> = {
  escrow: "value-trust-escrow",
  verified: "value-trust-verified",
  returns: "value-trust-returns",
  momoCod: "value-trust-momo",
};

export function ValueTrustStrip({
  ariaLabel,
  escrow,
  verified,
  returns,
  momoCod,
}: ValueTrustStripProps) {
  const values = { escrow, verified, returns, momoCod };
  const items = (Object.keys(GLYPHS) as TrustKey[])
    .map((key) => {
      const label = values[key];
      if (!label?.trim()) {
        return null;
      }
      return { key, label: label.trim(), path: GLYPHS[key], testId: TEST_IDS[key] };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
    .slice(0, 4);

  if (items.length === 0) {
    return null;
  }

  return (
    <section
      data-testid="value-trust-strip"
      aria-label={ariaLabel}
      className="rounded-lg border border-border bg-surface px-2 py-1.5"
    >
      <ul className="m-0 grid list-none gap-x-2 gap-y-1 p-0 sm:grid-cols-2">
        {items.map((item) => (
          <li
            key={item.key}
            data-testid={item.testId}
            className="flex min-h-8 items-center gap-1.5 text-xs font-medium leading-tight text-text-2"
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              className="h-4 w-4 shrink-0 text-primary"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d={item.path} />
            </svg>
            <span>{item.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
