import { PageHeader } from "@vergeo/ui/src/page-header";

import type { ReactNode } from "react";

const WIDTH_CLASSES = {
  full: "max-w-[1400px]",
  /** Single column on 360px; two-column shell at xl (≥1280px). */
  form: "max-w-[1400px]",
} as const;

const GRID_CLASSES = {
  cards: "grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4",
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
      className={`animate-page-in flex w-full flex-col space-y-4 px-4 py-4 sm:px-6 sm:py-6 lg:px-8 ${WIDTH_CLASSES[width]} ${className}`.trim()}
    >
      {title ? (
        <PageHeader title={title} subtitle={subtitle} actions={actions} className="!pb-4" />
      ) : null}
      {children}
    </main>
  );
}

type VendorGridProps = {
  cols?: VendorGridCols;
  /** Use `ul` when the children are `<li>` cards. */
  as?: "div" | "ul";
  children: ReactNode;
  className?: string;
};

type VendorFormLayoutProps = {
  main: ReactNode;
  aside: ReactNode;
  className?: string;
};

/** Form column + sticky preview / tips from xl (1280px) up; single column at 360px. */
export function VendorFormLayout({ main, aside, className = "" }: VendorFormLayoutProps) {
  return (
    <div
      className={`grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(280px,22rem)] xl:items-start ${className}`.trim()}
    >
      <div className="min-w-0 flex flex-col gap-4">{main}</div>
      <aside className="flex flex-col gap-3 xl:sticky xl:top-4">{aside}</aside>
    </div>
  );
}

export function VendorGrid({
  cols = "cards",
  as: Tag = "div",
  children,
  className = "",
}: VendorGridProps) {
  const listReset = Tag === "ul" ? "m-0 list-none p-0" : "";
  return (
    <Tag className={`${GRID_CLASSES[cols]} ${listReset} ${className}`.replace(/\s+/g, " ").trim()}>
      {children}
    </Tag>
  );
}
