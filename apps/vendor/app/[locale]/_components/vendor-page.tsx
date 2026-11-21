import type { ReactNode } from "react";

const WIDTH_CLASSES = {
  full: "max-w-[1400px]",
  form: "max-w-2xl",
} as const;

const GRID_CLASSES = {
  cards: "grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3",
  stats: "grid gap-3 grid-cols-2 md:grid-cols-4",
  two: "grid gap-4 grid-cols-1 lg:grid-cols-2",
} as const;

export type VendorPageWidth = keyof typeof WIDTH_CLASSES;
export type VendorGridCols = keyof typeof GRID_CLASSES;

type VendorPageProps = {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  width?: VendorPageWidth;
  children: ReactNode;
  className?: string;
};

/** Full-width (or form-narrow) page shell — left-aligned, responsive horizontal padding. */
export function VendorPage({
  title,
  subtitle,
  actions,
  width = "full",
  children,
  className = "",
}: VendorPageProps) {
  return (
    <main
      className={`flex w-full flex-col space-y-4 px-4 py-4 sm:px-6 sm:py-6 lg:px-8 ${WIDTH_CLASSES[width]} ${className}`.trim()}
    >
      {title || subtitle || actions ? (
        <header className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            {title ? <h1 className="text-lg font-semibold text-text">{title}</h1> : null}
            {subtitle ? <p className="text-sm text-text-2">{subtitle}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </main>
  );
}

type VendorGridProps = {
  cols?: VendorGridCols;
  children: ReactNode;
  className?: string;
};

export function VendorGrid({ cols = "cards", children, className = "" }: VendorGridProps) {
  return <div className={`${GRID_CLASSES[cols]} ${className}`.trim()}>{children}</div>;
}