type ExternalUrlImageProps = {
  src: string;
  alt: string;
  className?: string;
  width?: number;
  height?: number;
};

/** Absolute logo/cover URLs — lazy native img (not CSS background-image). */
export function ExternalUrlImage({
  src,
  alt,
  className,
  width = 112,
  height = 112,
}: ExternalUrlImageProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- arbitrary vendor URLs; Cloudinary uses CloudinaryImageStatic.
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading="lazy"
      decoding="async"
      className={className}
    />
  );
}
