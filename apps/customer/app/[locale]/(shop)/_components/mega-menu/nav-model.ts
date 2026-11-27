import { EVENT_CATEGORY_SLUGS, SERVICE_VERTICAL_SLUGS, type MegaMenuLabels } from "./labels";

import type { NavCategory } from "../category-tree";

export type MenuGroup = "products" | "services" | "events";

export type MenuLink = {
  id: string;
  slug: string;
  label: string;
  href: string;
};

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
    children: root.children.map((child) => ({
      id: child.id,
      slug: child.slug,
      label: child.name,
      href: `/${locale}/c/${child.slug}`,
    })),
  }));
}

export function serviceDept(labels: MegaMenuLabels, locale: string): MenuDept {
  return {
    id: "group:services",
    slug: "services",
    label: labels.services,
    href: `/${locale}/services`,
    group: "services",
    children: SERVICE_VERTICAL_SLUGS.map((slug) => ({
      id: `service:${slug}`,
      slug,
      label: labels.serviceVerticals[slug] ?? slug,
      href: `/${locale}/services?category=${encodeURIComponent(slug)}`,
    })),
  };
}

export function eventDept(labels: MegaMenuLabels, locale: string): MenuDept {
  return {
    id: "group:events",
    slug: "events",
    label: labels.events,
    href: `/${locale}/events`,
    group: "events",
    children: EVENT_CATEGORY_SLUGS.map((slug) => ({
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
): MenuModel {
  return {
    products: productDepts(tree, locale),
    services: serviceDept(labels, locale),
    events: eventDept(labels, locale),
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
