"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";

export type BreadcrumbItem = {
  key: string;
  label: ReactNode;
  href?: string;
};

export type BreadcrumbLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
};

export type BreadcrumbsProps = {
  items: BreadcrumbItem[];
  ariaLabel: string;
  ellipsisLabel: ReactNode;
  LinkComponent?: ComponentType<BreadcrumbLinkProps>;
  className?: string;
  /** Viewport width (px) at which middle items collapse when depth > 3. */
  collapseAtWidth?: number;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function useNarrowViewport(maxWidth: number): boolean {
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [maxWidth]);

  return narrow;
}

function getVisibleItems(
  items: BreadcrumbItem[],
  collapsed: boolean,
): Array<BreadcrumbItem | "ellipsis"> {
  if (!collapsed || items.length <= 3) {
    return items;
  }

  const first = items[0];
  const last = items[items.length - 1];
  if (!first || !last) {
    return items;
  }

  return [first, "ellipsis", last];
}

export function Breadcrumbs({
  items,
  ariaLabel,
  ellipsisLabel,
  LinkComponent = "a" as unknown as ComponentType<BreadcrumbLinkProps>,
  className,
  collapseAtWidth = 360,
}: BreadcrumbsProps) {
  const narrow = useNarrowViewport(collapseAtWidth);
  const shouldCollapse = narrow && items.length > 3;
  const visible = getVisibleItems(items, shouldCollapse);

  return (
    <nav aria-label={ariaLabel} className={mergeClasses("text-sm text-text-2", className)}>
      <ol className="m-0 flex list-none flex-wrap items-center gap-1 p-0">
        {visible.map((entry, index) => {
          if (entry === "ellipsis") {
            return (
              <li key="ellipsis" className="flex items-center gap-1" aria-hidden>
                <span className="px-1 text-text-3">{ellipsisLabel}</span>
                <span className="text-text-3" aria-hidden>
                  /
                </span>
              </li>
            );
          }

          const isLast = index === visible.length - 1;
          const isCurrent = isLast || entry.href == null;

          return (
            <li key={entry.key} className="flex min-w-0 items-center gap-1">
              {isCurrent ? (
                <span className="truncate font-medium text-text" aria-current="page">
                  {entry.label}
                </span>
              ) : (
                <LinkComponent
                  href={entry.href!}
                  className="truncate text-primary hover:underline focus-visible:outline-none"
                >
                  {entry.label}
                </LinkComponent>
              )}
              {!isLast ? (
                <span className="shrink-0 text-text-3" aria-hidden>
                  /
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
