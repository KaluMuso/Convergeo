import Image from "next/image";

type BrandLogoProps = {
  appName: string;
  /** Compact for sticky header; default keeps wordmark readable. */
  compact?: boolean;
  className?: string;
};

/**
 * Convergeo wordmark — petal mark replaces the first “O” in verge.webp.
 */
export function BrandLogo({ appName, compact = false, className }: BrandLogoProps) {
  return (
    <span
      className={["inline-flex items-center", className].filter(Boolean).join(" ")}
      data-testid="brand-logo"
    >
      <Image
        src="/verge.webp"
        alt={appName}
        width={compact ? 99 : 126}
        height={compact ? 18 : 23}
        priority
        className={
          compact
            ? "h-5 w-auto max-w-[8.5rem] object-contain object-left sm:h-[1.35rem] sm:max-w-[9.5rem]"
            : "h-6 w-auto max-w-[10rem] object-contain object-left sm:h-7 sm:max-w-[12rem]"
        }
      />
    </span>
  );
}
