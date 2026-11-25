"use client";

import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { useCallback, useEffect, useState } from "react";

export type PdpSectionNavItem = {
  id: string;
  label: string;
};

export type PdpSectionNavProps = {
  items: PdpSectionNavItem[];
  productTitle: string;
  thumbnailPublicId?: string;
  thumbnailAlt: string;
  cloudName?: string;
};

export function PdpSectionNav({
  items,
  productTitle,
  thumbnailPublicId,
  thumbnailAlt,
  cloudName,
}: PdpSectionNavProps) {
  const [active, setActive] = useState(items[0]?.id ?? "");
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const sentinel = document.getElementById("pdp-section-nav-sentinel");
    if (!sentinel) {
      return;
    }
    const observer = new IntersectionObserver(([entry]) => setStuck(!entry?.isIntersecting), {
      rootMargin: "-1px 0px 0px 0px",
      threshold: 0,
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const sections = items
      .map((item) => document.getElementById(item.id))
      .filter((node): node is HTMLElement => node !== null);
    if (sections.length === 0) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) {
          setActive(visible.target.id);
        }
      },
      { rootMargin: "-40% 0px -45% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [items]);

  const scrollTo = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActive(id);
  }, []);

  if (items.length === 0) {
    return null;
  }

  return (
    <>
      <div id="pdp-section-nav-sentinel" className="h-px w-full" aria-hidden />
      <nav
        data-testid="pdp-section-nav"
        aria-label={productTitle}
        className={[
          "z-30 border-b border-border bg-surface/95 backdrop-blur",
          stuck ? "sticky top-0 shadow-sm" : "relative",
        ].join(" ")}
      >
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-1 py-2">
          {thumbnailPublicId ? (
            <div className="hidden h-10 w-10 shrink-0 overflow-hidden rounded border border-border lg:block">
              <CloudinaryImage
                publicId={thumbnailPublicId}
                alt={thumbnailAlt}
                width={80}
                ratio="1/1"
                cloudName={cloudName}
                className="h-full w-full object-contain"
              />
            </div>
          ) : null}
          <p className="m-0 hidden max-w-[12rem] truncate text-sm font-medium text-text lg:block">
            {productTitle}
          </p>
          <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                data-testid={`pdp-section-nav-${item.id}`}
                onClick={() => scrollTo(item.id)}
                className={[
                  "shrink-0 rounded-full px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:shadow-focusRing",
                  active === item.id
                    ? "bg-primary text-primary-fg"
                    : "bg-bg-2 text-text-2 hover:bg-bg",
                ].join(" ")}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </nav>
    </>
  );
}
