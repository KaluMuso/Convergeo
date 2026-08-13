import Image from "next/image";

type BrandLogoProps = {
  appName: string;
  /** Compact for sticky header; default keeps wordmark readable. */
  compact?: boolean;
  className?: string;
};

/** Convergeo pinwheel wordmark — light and dark variants swap via `data-theme`. */
export function BrandLogo({ appName, compact = false, className }: BrandLogoProps) {
  const imgClass = compact
    ? "h-5 w-auto max-w-[8.5rem] object-contain object-left sm:h-[1.35rem] sm:max-w-[9.5rem]"
    : "h-6 w-auto max-w-[10rem] object-contain object-left sm:h-7 sm:max-w-[12rem]";

  return (
    <span
      className={["inline-flex items-center", className].filter(Boolean).join(" ")}
      data-testid="brand-logo"
    >
      <Image
        src="/brand-logo-light.webp"
        alt={appName}
        width={compact ? 103 : 132}
        height={compact ? 18 : 23}
        priority
        className={`${imgClass} dark:hidden`}
      />
      <Image
        src="/brand-logo-dark.webp"
        alt={appName}
        width={compact ? 99 : 126}
        height={compact ? 18 : 23}
        priority
        className={`${imgClass} hidden dark:block`}
      />
    </span>
  );
}
