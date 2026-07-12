type StaticMapPreviewProps = {
  lat: number | null;
  lng: number | null;
  alt: string;
  emptyLabel: string;
  coordsLabel?: string;
};

export function StaticMapPreview({
  lat,
  lng,
  alt,
  emptyLabel,
  coordsLabel,
}: StaticMapPreviewProps) {
  if (lat === null || lng === null || Number.isNaN(lat) || Number.isNaN(lng)) {
    return (
      <div
        className="flex h-36 w-full items-center justify-center rounded border border-dashed border-border bg-bg-2 text-sm text-text-2"
        role="img"
        aria-label={alt}
      >
        {emptyLabel}
      </div>
    );
  }

  const x = ((lng + 180) / 360) * 100;
  const y = ((90 - lat) / 180) * 100;

  return (
    <svg
      viewBox="0 0 360 144"
      className="h-36 w-full rounded border border-border bg-bg-2"
      role="img"
      aria-label={alt}
    >
      <defs>
        <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <path
            d="M 24 0 L 0 0 0 24"
            fill="none"
            strokeWidth="1"
            style={{ stroke: "var(--border)" }}
          />
        </pattern>
      </defs>
      <rect width="360" height="144" fill="url(#grid)" />
      <circle
        cx={Math.min(350, Math.max(10, (x / 100) * 360))}
        cy={Math.min(134, Math.max(10, (y / 100) * 144))}
        r="8"
        strokeWidth="2"
        style={{ fill: "var(--danger)", stroke: "var(--surface)" }}
      />
      <text
        x="12"
        y="20"
        fontSize="11"
        fontFamily="system-ui, sans-serif"
        style={{ fill: "var(--text-2)" }}
      >
        {coordsLabel}
      </text>
    </svg>
  );
}
