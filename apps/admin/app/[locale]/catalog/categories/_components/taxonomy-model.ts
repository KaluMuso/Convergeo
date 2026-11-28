export const UMBRELLAS = ["product", "service", "event", "wholesale"] as const;
export type Umbrella = (typeof UMBRELLAS)[number];
export type TaxonomyStatus = "draft" | "published" | "blocked";

export type TaxonomyNode = {
  id: string;
  slug: string;
  parent_id: string | null;
  name: string;
  umbrella: Umbrella;
  status: TaxonomyStatus;
  sort_order: number;
  image_public_id: string | null;
  image_alt: string | null;
  image_url: string | null;
  icon: string | null;
  show_in_customer: boolean;
  show_in_vendor: boolean;
  path: string | null;
  commission_key: string | null;
  child_count: number;
};

export type TreeRow = {
  node: TaxonomyNode;
  depth: number;
  siblings: TaxonomyNode[];
};

/** Permission needed per umbrella (mirrors admin_taxonomy._require_umbrella). */
export function canManageUmbrella(
  umbrella: Umbrella,
  grants: { permissions: string[]; unrestricted: boolean } | null,
): boolean {
  if (!grants) return false;
  if (grants.unrestricted) return true;
  if (umbrella === "service") return false;
  const needed = umbrella === "event" ? "events.manage" : "products.manage";
  return grants.permissions.includes(needed);
}

function bySort(a: TaxonomyNode, b: TaxonomyNode): number {
  return a.sort_order - b.sort_order || a.name.localeCompare(b.name);
}

/** Flatten to depth-first rows; orphans (missing parent, e.g. filtered by search) become roots. */
export function flattenTree(nodes: readonly TaxonomyNode[]): TreeRow[] {
  const ids = new Set(nodes.map((n) => n.id));
  const children = new Map<string | null, TaxonomyNode[]>();
  for (const node of nodes) {
    const key = node.parent_id && ids.has(node.parent_id) ? node.parent_id : null;
    const list = children.get(key) ?? [];
    list.push(node);
    children.set(key, list);
  }
  const rows: TreeRow[] = [];
  const walk = (parent: string | null, depth: number) => {
    const siblings = [...(children.get(parent) ?? [])].sort(bySort);
    for (const node of siblings) {
      rows.push({ node, depth, siblings });
      walk(node.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

/** Ordered sibling ids after moving `id` one step; null when it cannot move. */
export function reorderedIds(
  siblings: readonly TaxonomyNode[],
  id: string,
  direction: -1 | 1,
): string[] | null {
  const ids = siblings.map((s) => s.id);
  const index = ids.indexOf(id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= ids.length) return null;
  [ids[index], ids[target]] = [ids[target]!, ids[index]!];
  return ids;
}

/** Parents a node may move under: same umbrella, not itself or a descendant. */
export function movableParents(nodes: readonly TaxonomyNode[], id: string): TaxonomyNode[] {
  const banned = new Set<string>([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const node of nodes) {
      if (node.parent_id && banned.has(node.parent_id) && !banned.has(node.id)) {
        banned.add(node.id);
        grew = true;
      }
    }
  }
  return nodes.filter((n) => !banned.has(n.id));
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
