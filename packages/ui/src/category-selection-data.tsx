export type CategoryNode = { id: string; parentId: string | null; label: string };
export type CategoryLabels = {
  category: string;
  subcategory: string;
  placeholder: string;
  empty: string;
  unavailable: string;
};

/** Only rooted, acyclic paths can be selected. No synthetic taxonomy nodes. */
export function categoryPath(nodes: CategoryNode[], value: string): CategoryNode[] {
  const path: CategoryNode[] = [];
  const seen = new Set<string>();
  let id: string | null = value || null;
  while (id) {
    if (seen.has(id)) return [];
    seen.add(id);
    const node = nodes.find((item) => item.id === id);
    if (!node) return [];
    path.unshift(node);
    id = node.parentId;
  }
  return path;
}

export function eventCategoryNodes(
  rows: { slug: string; parent_slug: string | null; label_key: string }[],
  translate: ((key: string) => string) & { has: (key: string) => boolean },
): CategoryNode[] {
  return rows.map((row) => {
    const key = row.label_key.replace(/^events\./, "");
    const fallback = `categories.${row.slug}`;
    return {
      id: row.slug,
      parentId: row.parent_slug,
      label: translate.has(key)
        ? translate(key)
        : translate.has(fallback)
          ? translate(fallback)
          : row.slug,
    };
  });
}
