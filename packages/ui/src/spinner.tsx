import type { CSSProperties } from "react";

export type SpinnerProps = {
  /** Visually hidden label for screen readers. */
  label: string;
  size?: "sm" | "md" | "lg";
  color?: string;
  className?: string;
  "data-testid"?: string;
};

const sizeMap: Record<NonNullable<SpinnerProps["size"]>, string> = {
  sm: "1.25rem",
  md: "2rem",
  lg: "2.75rem",
};

export function Spinner({
  label,
  size = "md",
  color = "var(--primary)",
  className,
  "data-testid": dataTestId,
}: SpinnerProps) {
  const dimension = sizeMap[size];

  const ringStyle: CSSProperties = {
    width: dimension,
    height: dimension,
    border: `3px solid color-mix(in srgb, ${color} 20%, transparent)`,
    borderTopColor: color,
    borderRadius: "50%",
    animation: "spin var(--dur-slow) linear infinite",
  };

  return (
    <div
      role="status"
      className={className}
      data-testid={dataTestId ?? "spinner"}
      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center" }}
    >
      <span style={ringStyle} aria-hidden="true" />
      <span
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
      >
        {label}
      </span>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes spin {
            from, to { transform: none; opacity: 1; }
          }
        }
      `}</style>
    </div>
  );
}
