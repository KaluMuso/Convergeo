"use client";

import Link from "next/link";

import { useAdminPermissions } from "../../../lib/roles-api";

type Destination = { key: string; href: string; title: string; body: string };

export function ModerationDestinations({ destinations }: { destinations: readonly Destination[] }) {
  const grants = useAdminPermissions();
  const canModerate = grants?.unrestricted || grants?.permissions.includes("products.manage");
  return (
    <ul className="grid list-none gap-3 p-0 sm:grid-cols-2">
      {destinations
        .filter((item) => canModerate && (item.key !== "flags" || grants?.unrestricted))
        .map((item) => (
          <li key={item.key}>
            <Link
              href={item.href}
              className="block rounded border border-border bg-surface p-4 no-underline transition-colors hover:border-primary focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              <p className="font-semibold text-text">{item.title}</p>
              <p className="mt-1 text-sm text-muted">{item.body}</p>
            </Link>
          </li>
        ))}
    </ul>
  );
}
