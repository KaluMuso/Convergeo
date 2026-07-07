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
}: CloudinaryImageProps) {
  const [loaded, setLoaded] = useState(false);
  const aspectRatio = resolveAspectRatio(ratio);
  const lqip = cldLqipUrl(publicId, { cloudName });

  const handleLoad = useCallback(() => {
    setLoaded(true);
  }, []);

  const containerStyle: CSSProperties = {
    position: "relative",
    overflow: "hidden",
    borderRadius: "var(--r)",
    width: "100%",
    ...(aspectRatio ? { aspectRatio } : {}),
    backgroundImage: loaded ? undefined : `url(${lqip})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
    filter: loaded ? undefined : "blur(8px)",
    transition: "filter var(--dur) var(--ease-std)",
  };

  return (
    <div className={className} style={containerStyle} data-testid="cloudinary-image-box">
      {!loaded ? (
        <div aria-hidden="true" style={shimmerStyle} data-testid="cloudinary-shimmer" />
      ) : null}
      <img
        src={cldUrl(publicId, { width, cloudName })}
        srcSet={cldSrcSet(publicId, { cloudName })}
        sizes={sizes}
        alt={alt}
        loading={priority ? "eager" : "lazy"}
        decoding="async"
        onLoad={handleLoad}
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
