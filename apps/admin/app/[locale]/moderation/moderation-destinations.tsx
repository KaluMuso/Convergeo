"use client";

import { useAdminPermissions } from "../../../lib/roles-api";
import { AdminHubCard } from "../_components/admin-hub-card";

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
            <AdminHubCard
              href={item.href}
              title={item.title}
              body={item.body}
              hue={item.key === "flags" ? "red" : "orange"}
            />
          </li>
        ))}
    </ul>
  );
}
