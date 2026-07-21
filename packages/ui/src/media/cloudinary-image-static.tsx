import { cldLqipUrl, cldSrcSet, cldUrl } from "./cloudinary-url";

import type { CSSProperties } from "react";

const DEFAULT_SIZES = "(max-width: 360px) 100vw, (max-width: 720px) 50vw, 33vw";

export type CloudinaryImageStaticProps = {
  publicId: string;
  alt: string;
  width?: number;
  sizes?: string;
  ratio?: number | `${number}/${number}`;
  priority?: boolean;
  cloudName?: string;
  className?: string;
  /** Shown instead of an empty stage when the public id cannot resolve a URL. */
  fallbackLabel?: string;
};

function resolveAspectRatio(ratio: CloudinaryImageStaticProps["ratio"]): string | undefined {
  if (ratio === undefined) {
    return undefined;
  }
  if (typeof ratio === "number") {
    return String(ratio);
  }
  return ratio;
}

/** Intrinsic pixel height for CLS reservation when `ratio` is known. */
function resolveIntrinsicHeight(
  width: number,
  ratio: CloudinaryImageStaticProps["ratio"],
): number | undefined {
  if (ratio === undefined) {
    return undefined;
  }
  if (typeof ratio === "number" && ratio > 0) {
    return Math.round(width / ratio);
  }
  if (typeof ratio === "string") {
    const parts = ratio.split("/");
    const w = Number(parts[0]);
    const h = Number(parts[1]);
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
      return Math.round((width * h) / w);
    }
  }
  return undefined;
}

/**
 * RSC-safe Cloudinary image — no client JS, no shimmer hydration.
 * Prefer this on server-rendered grids; use `CloudinaryImage` when load/error UX matters.
 */
export function CloudinaryImageStatic({
  publicId,
  alt,
  width = 720,
  sizes = DEFAULT_SIZES,
  ratio,
  priority = false,
  cloudName,
  className,
  fallbackLabel,
}: CloudinaryImageStaticProps) {
  const src = cldUrl(publicId, { width, cloudName });
  const aspectRatio = resolveAspectRatio(ratio);
  const intrinsicHeight = resolveIntrinsicHeight(width, ratio);
  const lqip = src ? cldLqipUrl(publicId, { cloudName }) : undefined;

  const containerStyle: CSSProperties = {
    position: "relative",
    overflow: "hidden",
    borderRadius: "var(--r)",
    width: "100%",
    ...(aspectRatio ? { aspectRatio } : {}),
    backgroundImage: lqip ? `url(${lqip})` : undefined,
    backgroundColor: src ? undefined : "var(--bg-2)",
    backgroundSize: "cover",
    backgroundPosition: "center",
  };

  if (!src) {
    return (
      <div
        className={className}
        style={{
          ...containerStyle,
          backgroundImage: undefined,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-3)",
          textAlign: "center",
          padding: "var(--sp-4)",
        }}
        data-testid="cloudinary-image-fallback"
        role="img"
        aria-label={fallbackLabel ?? alt}
      >
        <span style={{ fontSize: "0.875rem", lineHeight: 1.4 }}>{fallbackLabel ?? alt}</span>
      </div>
    );
  }

  return (
    <div className={className} style={containerStyle} data-testid="cloudinary-image-box">
      <img
        src={src}
        srcSet={cldSrcSet(publicId, { cloudName })}
        sizes={sizes}
        width={width}
        height={intrinsicHeight}
        alt={alt}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        style={{
          display: "block",
          width: "100%",
          height: aspectRatio ? "100%" : "auto",
          objectFit: "cover",
        }}
      />
    </div>
  );
}
