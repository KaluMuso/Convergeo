"use client";

import type { ComponentType, CSSProperties, ReactNode } from "react";

export type BottomNavItem = {
  key: string;
  icon: ReactNode;
  label: ReactNode;
  href: string;
  active: boolean;
  badge?: number;
};

export type BottomNavLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  "aria-current"?: "page" | boolean;
};

export type BottomNavProps = {
  items: BottomNavItem[];
  ariaLabel: string;
  LinkComponent?: ComponentType<BottomNavLinkProps>;
  className?: string;
  /** Class hook for hiding at ≥768px — apps may override. */
  desktopHiddenClassName?: string;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function formatBadgeCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

export function BottomNav({
  items,
  ariaLabel,
  LinkComponent = "a" as unknown as ComponentType<BottomNavLinkProps>,
  className,
  desktopHiddenClassName = "md:hidden",
}: BottomNavProps) {
  return (
    <nav
      aria-label={ariaLabel}
      className={mergeClasses(
        "fixed inset-x-0 bottom-0 z-50 border-t border-border bg-surface",
        desktopHiddenClassName,
        className,
      )}
      style={{
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        transition: "box-shadow var(--dur) var(--ease-std)",
      }}
    >
      <ul className="mx-auto flex h-14 max-w-lg list-none items-stretch justify-around p-0">
        {items.map((item) => (
          <li key={item.key} className="flex min-w-0 flex-1">
            <LinkComponent
              href={item.href}
              aria-current={item.active ? "page" : undefined}
              className={mergeClasses(
                "relative flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-0.5 px-1 py-1 text-micro font-medium transition-colors",
                item.active ? "text-primary" : "text-text-3",
              )}
              style={{ transitionTimingFunction: "var(--ease-std)" }}
            >
              <span className="relative flex h-6 w-6 items-center justify-center" aria-hidden>
                {item.icon}
                {item.badge != null && item.badge > 0 ? (
                  <span
                    className="absolute -right-1.5 -top-1 flex min-h-4 min-w-4 items-center justify-center rounded-pill bg-accent px-1 text-[0.625rem] font-semibold leading-none text-surface"
                    aria-hidden
                  >
                    {formatBadgeCount(item.badge)}
                  </span>
                ) : null}
              </span>
              <span className="truncate">{item.label}</span>
              {item.active ? (
                <span className="absolute bottom-1 h-1 w-1 rounded-pill bg-primary" aria-hidden />
              ) : null}
            </LinkComponent>
          </li>
        ))}
      </ul>
    </nav>
  );
}
