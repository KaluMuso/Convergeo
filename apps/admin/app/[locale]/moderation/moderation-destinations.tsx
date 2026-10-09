"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { loadAdminPermissions } from "../../../lib/roles-api";

type Destination = { key: string; href: string; title: string; body: string };

export function ModerationDestinations({ destinations }: { destinations: readonly Destination[] }) {
  const [unrestricted, setUnrestricted] = useState(false);
  useEffect(() => {
    let active = true;
    void loadAdminPermissions().then(
      (grants) => {
        if (active) setUnrestricted(grants.unrestricted);
      },
      () => {
        if (active) setUnrestricted(false);
      },
    );
    return () => {
      active = false;
    };
  }, []);
  return (
    <ul className="grid list-none gap-3 p-0 sm:grid-cols-2">
      {destinations
        .filter((item) => item.key !== "flags" || unrestricted)
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
