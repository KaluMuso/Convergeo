"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { configApi, type CategoryNode } from "./api";

function sortSiblings(nodes: CategoryNode[]): CategoryNode[] {
  return [...nodes].sort((a, b) => a.position - b.position || a.name.localeCompare(b.name));
}

export function CategoryTreeEditor() {
  const t = useTranslations("admin.config");
  const [rows, setRows] = useState<CategoryNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [moveChildrenId, setMoveChildrenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await configApi.request<CategoryNode[]>("/admin/config/categories");
      setRows(data);
    } catch {
      setError(t("common.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const childrenByParent = useMemo(() => {
    const map = new Map<string | null, CategoryNode[]>();
    for (const row of rows) {
      const key = row.parent_id;
      const bucket = map.get(key) ?? [];
      bucket.push(row);
      map.set(key, bucket);
    }
    for (const [key, bucket] of map.entries()) {
      map.set(key, sortSiblings(bucket));
    }
    return map;
  }, [rows]);

  const reorderSibling = async (node: CategoryNode, direction: -1 | 1) => {
    const siblings = childrenByParent.get(node.parent_id) ?? [];
    const index = siblings.findIndex((item) => item.id === node.id);
    const targetIndex = index + direction;
    if (index < 0 || targetIndex < 0 || targetIndex >= siblings.length) {
      return;
    }
    const other = siblings[targetIndex];
    if (!other) {
      return;
    }
    await configApi.request("/admin/config/categories/reorder", {
      method: "POST",
      body: JSON.stringify({
        moves: [
          { id: node.id, parent_id: node.parent_id, position: other.position },
          { id: other.id, parent_id: other.parent_id, position: node.position },
        ],
      }),
    });
    await load();
  };

  const toggleProhibited = async (node: CategoryNode) => {
    await configApi.request(`/admin/config/categories/${node.id}`, {
      method: "PATCH",
      body: JSON.stringify({ prohibited: !node.prohibited }),
    });
    await load();
  };

  const moveUnderParent = async (node: CategoryNode, newParentId: string | null) => {
    const childCount = childrenByParent.get(node.id)?.length ?? 0;
    if (childCount > 0 && moveChildrenId !== node.id) {
      setMoveChildrenId(node.id);
      return;
    }

    try {
      await configApi.request(`/admin/config/categories/${node.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          parent_id: newParentId,
          move_children: moveChildrenId === node.id,
        }),
      });
      setMoveChildrenId(null);
      await load();
    } catch {
      setError(t("categories.orphanWarning"));
    }
  };

  const renderNode = (node: CategoryNode, depth: number) => {
    const siblings = childrenByParent.get(node.parent_id) ?? [];
    const index = siblings.findIndex((item) => item.id === node.id);
    const rootCandidates = childrenByParent.get(null) ?? [];

    return (
      <li key={node.id} className="space-y-2">
        <div
          className="flex flex-col gap-2 rounded-md border border-[#E8DFD0] p-3 sm:flex-row sm:items-center sm:justify-between"
          style={{ marginLeft: depth * 12 }}
        >
          <div>
            <p className="text-sm font-medium text-[#2A2118]">{node.name}</p>
            <p className="font-mono text-xs text-[#6B5E4C]">{node.path}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-3 text-sm"
              disabled={index <= 0}
              onClick={() => void reorderSibling(node, -1)}
            >
              {t("categories.moveUp")}
            </button>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-3 text-sm"
              disabled={index < 0 || index >= siblings.length - 1}
              onClick={() => void reorderSibling(node, 1)}
            >
              {t("categories.moveDown")}
            </button>
            <label className="inline-flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={node.prohibited}
                onChange={() => void toggleProhibited(node)}
              />
              {node.prohibited ? t("common.prohibited") : t("common.allowed")}
            </label>
            <select
              className="min-h-11 rounded-md border border-[#E8DFD0] px-2 text-sm"
              value={node.parent_id ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                void moveUnderParent(node, value ? value : null);
              }}
            >
              <option value="">{t("categories.rootOption")}</option>
              {rootCandidates
                .filter((candidate) => candidate.id !== node.id)
                .map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.name}
                  </option>
                ))}
            </select>
          </div>
        </div>

        {moveChildrenId === node.id ? (
          <div
            className="rounded-md border border-[#F0C987] bg-[#FFF8EB] p-3 text-sm"
            style={{ marginLeft: depth * 12 }}
          >
            <p>{t("categories.moveChildrenPrompt")}</p>
            <button
              type="button"
              className="mt-2 inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-3 text-sm font-medium text-white"
              onClick={() => void moveUnderParent(node, node.parent_id)}
            >
              {t("categories.moveChildrenConfirm")}
            </button>
          </div>
        ) : null}

        {(childrenByParent.get(node.id) ?? []).length > 0 ? (
          <ul className="space-y-2">
            {(childrenByParent.get(node.id) ?? []).map((child) => renderNode(child, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  };

  if (loading) {
    return <p className="text-sm text-[#6B5E4C]">{t("common.loading")}</p>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-[#9B2C2C]">{error}</p>
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-[#E8DFD0] px-4 text-sm"
          onClick={() => void load()}
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  const roots = childrenByParent.get(null) ?? [];

  return <ul className="space-y-3">{roots.map((node) => renderNode(node, 0))}</ul>;
}
