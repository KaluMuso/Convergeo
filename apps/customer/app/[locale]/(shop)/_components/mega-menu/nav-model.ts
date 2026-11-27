import { EVENT_CATEGORY_SLUGS, SERVICE_VERTICAL_SLUGS, type MegaMenuLabels } from "./labels";

import type { NavCategory } from "../category-tree";

export type MenuGroup = "products" | "services" | "events";

export type MenuLink = {
  id: string;
  slug: string;
  label: string;
  href: string;
  /** Admin-managed tile image; the tile falls back to the tinted initial when absent. */
  imageUrl?: string | null;
  imageAlt?: string | null;
};

/** Top-level services / event categories from the admin-managed taxonomy. */
export type GroupItem = {
  slug: string;
  name: string;
  parentSlug: string | null;
  imageUrl: string | null;
  imageAlt: string | null;
};

export type MenuGroups = { services: GroupItem[] | null; events: GroupItem[] | null };

export type MenuDept = MenuLink & {
  group: MenuGroup;
  children: MenuLink[];
};

/** Product departments from the `/categories` tree (one child level). */
export function productDepts(tree: readonly NavCategory[], locale: string): MenuDept[] {
  return tree.map((root) => ({
    id: root.id,
    slug: root.slug,
    label: root.name,
    href: `/${locale}/c/${root.slug}`,
    group: "products" as const,
    imageUrl: root.imageUrl ?? null,
    imageAlt: root.imageAlt ?? null,
    children: root.children.map((child) => ({
      id: child.id,
      slug: child.slug,
      label: child.name,
      href: `/${locale}/c/${child.slug}`,
      imageUrl: child.imageUrl ?? null,
      imageAlt: child.imageAlt ?? null,
    })),
  }));
}

/** Top-level published items; empty/absent means "use the built-in launch list". */
function topLevel(items: readonly GroupItem[] | null | undefined): GroupItem[] {
  return (items ?? []).filter((item) => item.parentSlug === null);
}

export function serviceDept(
  labels: MegaMenuLabels,
  locale: string,
  items?: readonly GroupItem[] | null,
): MenuDept {
  const live = topLevel(items);
  return {
    id: "group:services",
    slug: "services",
    label: labels.services,
    href: `/${locale}/services`,
    group: "services",
    children:
      live.length > 0
        ? live.map((item) => ({
            id: `service:${item.slug}`,
            slug: item.slug,
            label: labels.serviceVerticals[item.slug] ?? item.name,
            href: `/${locale}/services?category=${encodeURIComponent(item.slug)}`,
            imageUrl: item.imageUrl,
            imageAlt: item.imageAlt,
          }))
        : SERVICE_VERTICAL_SLUGS.map((slug) => ({
            id: `service:${slug}`,
            slug,
            label: labels.serviceVerticals[slug] ?? slug,
            href: `/${locale}/services?category=${encodeURIComponent(slug)}`,
          })),
  };
}

export function eventDept(
  labels: MegaMenuLabels,
  locale: string,
  items?: readonly GroupItem[] | null,
): MenuDept {
  const live = topLevel(items);
  return {
    id: "group:events",
    slug: "events",
    label: labels.events,
    href: `/${locale}/events`,
    group: "events",
    children:
      live.length > 0
        ? live.map((item) => ({
            id: `event:${item.slug}`,
            slug: item.slug,
            label: labels.eventCategories[item.slug] ?? item.name,
            href: `/${locale}/events?category=${encodeURIComponent(item.slug)}`,
            imageUrl: item.imageUrl,
            imageAlt: item.imageAlt,
          }))
        : EVENT_CATEGORY_SLUGS.map((slug) => ({
            id: `event:${slug}`,
            slug,
            label: labels.eventCategories[slug] ?? slug,
            href: `/${locale}/events?category=${encodeURIComponent(slug)}`,
          })),
  };
}

export type MenuModel = {
  products: MenuDept[];
  services: MenuDept;
  events: MenuDept;
};

export function buildMenuModel(
  tree: readonly NavCategory[],
  labels: MegaMenuLabels,
  locale: string,
  groups?: MenuGroups | null,
): MenuModel {
  return {
    products: productDepts(tree, locale),
    services: serviceDept(labels, locale, groups?.services),
    events: eventDept(labels, locale, groups?.events),
  };
}

/** Initial for the placeholder tile (first letter or digit of the label). */
export function tileInitial(label: string): string {
  const first = Array.from(label.trim())[0];
  return first ? first.toLocaleUpperCase() : "•";
}

const PASTELS = [
  "var(--cat-beauty)",
  "var(--cat-health)",
  "var(--cat-food)",
  "var(--cat-fitness)",
  "var(--cat-home)",
  "var(--cat-auto)",
] as const;

/** Deterministic design-token tint for a placeholder tile. */
export function tileTint(seed: string): string {
  let hash = 0;
  for (const ch of seed) {
    hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  }
  return PASTELS[hash % PASTELS.length] ?? "var(--cat-beauty)";
}
