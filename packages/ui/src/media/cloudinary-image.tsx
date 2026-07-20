"use client";

import { useCallback, useState, type CSSProperties } from "react";

import { cldLqipUrl, cldSrcSet, cldUrl } from "./cloudinary-url";

const DEFAULT_SIZES = "(max-width: 360px) 100vw, (max-width: 720px) 50vw, 33vw";

export type CloudinaryImageProps = {
  publicId: string;
  alt: string;
  width?: number;
  sizes?: string;
  ratio?: number | `${number}/${number}`;
  priority?: boolean;
  cloudName?: string;
  className?: string;
  /** Shown instead of an empty/beige stage when the image fails to load. */
  fallbackLabel?: string;
  onError?: () => void;
};

function resolveAspectRatio(ratio: CloudinaryImageProps["ratio"]): string | undefined {
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
  ratio: CloudinaryImageProps["ratio"],
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

const shimmerStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  borderRadius: "var(--r)",
  background: "linear-gradient(90deg, var(--bg-2) 25%, var(--bg) 50%, var(--bg-2) 75%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.5s infinite",
};

export function CloudinaryImage({
  publicId,
  alt,
  width = 720,
  sizes = DEFAULT_SIZES,
  ratio,
  priority = false,
  cloudName,
  className,
  fallbackLabel,
  onError,
}: CloudinaryImageProps) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const aspectRatio = resolveAspectRatio(ratio);
  const intrinsicHeight = resolveIntrinsicHeight(width, ratio);
  const lqip = failed ? undefined : cldLqipUrl(publicId, { cloudName });

  const markLoaded = useCallback(() => {
    setLoaded(true);
    setFailed(false);
  }, []);

  const handleError = useCallback(() => {
    setFailed(true);
    setLoaded(false);
    onError?.();
  }, [onError]);

  // Cached images often finish before React attaches onLoad — sync from the
  // element so we never leave a permanent opacity-0 / beige stage.
  const imgRef = useCallback(
    (node: HTMLImageElement | null) => {
      if (!node || failed) {
        return;
      }
      if (node.complete && node.naturalWidth > 0) {
        markLoaded();
      }
    },
    [failed, markLoaded],
  );

  const containerStyle: CSSProperties = {
    position: "relative",
    overflow: "hidden",
    borderRadius: "var(--r)",
    width: "100%",
    ...(aspectRatio ? { aspectRatio } : {}),
    backgroundImage: !loaded && lqip ? `url(${lqip})` : undefined,
    backgroundColor: failed ? "var(--bg-2)" : undefined,
    backgroundSize: "cover",
    backgroundPosition: "center",
    filter: loaded || failed ? undefined : "blur(8px)",
    transition: "filter var(--dur) var(--ease-std)",
  };

  if (failed) {
    return (
      <div
        className={className}
        style={{
          ...containerStyle,
          filter: undefined,
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
      {!loaded ? (
        <div aria-hidden="true" style={shimmerStyle} data-testid="cloudinary-shimmer" />
      ) : null}
      <img
        ref={imgRef}
        src={cldUrl(publicId, { width, cloudName })}
        srcSet={cldSrcSet(publicId, { cloudName })}
        sizes={sizes}
        width={width}
        height={intrinsicHeight}
        alt={alt}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        onLoad={markLoaded}
        onError={handleError}
        style={{
          display: "block",
          width: "100%",
          height: aspectRatio ? "100%" : "auto",
          objectFit: "cover",
          opacity: loaded ? 1 : 0,
          transition: "opacity var(--dur) var(--ease-std)",
        }}
      />
    </div>
  );
}
