type BrandLogoProps = {
  appName: string;
  /** Compact for sticky header; default keeps wordmark readable. */
  compact?: boolean;
  className?: string;
};

/**
 * SVG wordmark placeholder (replaces the raster pinwheel). One-colour mark
 * drawn with `currentColor` so it works on light, dark and panel grounds;
 * the name is live text in the display face so it follows the brand copy
 * (`common.app.name`). Swap the <svg> paths for the final mark when the
 * identity is signed off — the component API stays the same.
 */
export function BrandLogo({ appName, compact = false, className }: BrandLogoProps) {
  const size = compact ? 22 : 26;
  return (
    <span
      className={["inline-flex items-center gap-2 text-primary", className]
        .filter(Boolean)
        .join(" ")}
      data-testid="brand-logo"
    >
      <svg
        aria-hidden
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        className="shrink-0"
      >
        {/* Seal: outer ring (copper accent) around a malachite "V" monogram. */}
        <circle cx="16" cy="16" r="14.5" stroke="var(--accent)" strokeWidth="3" />
        <path
          d="M9.5 10.5 16 22.5l6.5-12"
          stroke="currentColor"
          strokeWidth="3.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className={`font-display font-extrabold leading-none tracking-tight text-text ${
          compact ? "text-lg" : "text-xl"
        }`}
      >
        {appName}
      </span>
    </span>
  );
}
