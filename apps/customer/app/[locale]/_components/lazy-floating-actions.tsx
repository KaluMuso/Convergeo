"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";

import type { FloatingActionsLabels } from "./floating-actions";

type Props = { locale: string; labels: FloatingActionsLabels; footer: ReactNode };

function isHome(pathname: string, locale: string): boolean {
  return pathname === `/${locale}` || pathname === `/${locale}/`;
}

/**
 * Loads the floating Ask Vergeo / footer-toggle stack after the browser is
 * idle so it never competes with LCP or counts toward first-load JS.
 * Until then the footer renders inline (off home) exactly as before.
 */
export function LazyFloatingActions({ locale, labels, footer }: Props) {
  const pathname = usePathname() ?? `/${locale}`;
  const [Loaded, setLoaded] = useState<ComponentType<Props> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void import("./floating-actions").then((mod) => {
        if (!cancelled) setLoaded(() => mod.FloatingActions);
      });
    };
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    let idle: number | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (typeof w.requestIdleCallback === "function") {
      idle = w.requestIdleCallback(load, { timeout: 2500 });
    } else {
      timer = setTimeout(load, 1200);
    }
    return () => {
      cancelled = true;
      if (idle !== undefined) w.cancelIdleCallback?.(idle);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  if (Loaded) {
    return <Loaded locale={locale} labels={labels} footer={footer} />;
  }
  return isHome(pathname, locale) ? null : <>{footer}</>;
}
