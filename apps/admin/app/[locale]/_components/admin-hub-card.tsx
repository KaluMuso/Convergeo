"use client";

import { IconTile } from "@vergeo/ui/src/icon-tile";
import { LcArrowRight } from "@vergeo/ui/src/lucide-icons";
import Link from "next/link";

import type { IconHue } from "@vergeo/ui/src/icon-hues";
import type { ReactNode } from "react";

export type AdminHubCardProps = {
  href: string;
  title: string;
  body: string;
  hue?: IconHue;
  icon?: ReactNode;
};

/** Hub destination tile with coloured icon and hover lift. */
export function AdminHubCard({ href, title, body, hue = "slate", icon }: AdminHubCardProps) {
  return (
    <Link
      href={href}
      className="card-lift group flex min-h-[5.5rem] gap-3 rounded-xl border border-border bg-surface p-4 no-underline transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
    >
      <IconTile hue={hue} size={40}>
        {icon ?? <LcArrowRight className="size-5" duotone aria-hidden />}
      </IconTile>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 font-semibold text-text">
          <span className="line-clamp-1">{title}</span>
          <LcArrowRight
            className="size-4 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100"
            aria-hidden
          />
        </span>
        <span className="mt-1 line-clamp-2 block text-sm text-muted">{body}</span>
      </span>
    </Link>
  );
}
