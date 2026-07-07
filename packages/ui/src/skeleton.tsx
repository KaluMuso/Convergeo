import type { CSSProperties } from "react";

export type SkeletonShape = "block" | "line" | "circle";

export type SkeletonProps = {
  shape?: SkeletonShape;
  width?: string | number;
  height?: string | number;
  className?: string;
  "data-testid"?: string;
};

const baseStyle: CSSProperties = {
  background: "linear-gradient(90deg, var(--bg-2) 0%, var(--surface) 50%, var(--bg-2) 100%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.4s var(--ease-std) infinite",
  borderRadius: "var(--r-sm)",
};

const shapeDefaults: Record<SkeletonShape, CSSProperties> = {
  block: { width: "100%", height: "8rem", borderRadius: "var(--r)" },
  line: { width: "100%", height: "0.875rem", borderRadius: "var(--r-sm)" },
  circle: { width: "3rem", height: "3rem", borderRadius: "50%" },
};

export function Skeleton({
  shape = "block",
  width,
  height,
  className,
  "data-testid": dataTestId,
}: SkeletonProps) {
  const style: CSSProperties = {
    ...baseStyle,
    ...shapeDefaults[shape],
    ...(width !== undefined ? { width } : {}),
    ...(height !== undefined ? { height } : {}),
  };

  return (
    <div
      role="presentation"
      aria-hidden="true"
      className={className}
      data-testid={dataTestId ?? "skeleton"}
      data-shape={shape}
      style={style}
    />
  );
}
