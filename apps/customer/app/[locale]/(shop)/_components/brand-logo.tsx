import Image from "next/image";

type BrandLogoProps = {
  appName: string;
  /** Compact for sticky header; default keeps wordmark readable. */
  compact?: boolean;
  className?: string;
};

/**
 * Founder artwork wordmark (`public/brand/`): high-contrast serif CONVERGEO
 * with the glass pinwheel as the "O". The supplied files are opaque (black on
 * white / white on black), so a blend mode drops the solid ground onto any
 * surface: `multiply` erases white on light themes, `screen` erases black on
 * dark. next/image serves a resized WebP, so the header pays a few KB.
 */
export function BrandLogo({ appName, compact = false, className }: BrandLogoProps) {
  // Artwork ratio ≈ 5.85:1 (1024×175).
  const height = compact ? 22 : 26;
  const width = Math.round(height * 5.85);
  const imgClass = "h-auto w-auto max-w-[9.5rem] sm:max-w-[10.5rem]";

  return (
    <span
      className={["inline-flex items-center", className].filter(Boolean).join(" ")}
      data-testid="brand-logo"
    >
      <Image
        src="/brand/convergeo-wordmark-on-light.webp"
        alt={appName}
        width={width}
        height={height}
        priority
        className={`${imgClass} mix-blend-multiply dark:hidden`}
        style={{ height }}
      />
      <Image
        src="/brand/convergeo-wordmark-on-dark.webp"
        alt={appName}
        width={width}
        height={height}
        loading="lazy"
        className={`${imgClass} hidden mix-blend-screen dark:block`}
        style={{ height }}
      />
    </span>
  );
}
