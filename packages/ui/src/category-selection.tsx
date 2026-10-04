"use client";

import { categoryPath, type CategoryNode, type CategoryLabels } from "./category-selection-data";
import { Select } from "./select";

export { categoryPath, eventCategoryNodes, type CategoryNode } from "./category-selection-data";

export function CategorySelection({
  nodes,
  value,
  onChange,
  labels,
  disabled = false,
}: {
  nodes: CategoryNode[];
  value: string;
  onChange: (id: string) => void;
  labels: CategoryLabels;
  disabled?: boolean;
}) {
  const path = categoryPath(nodes, value);
  const parents: (string | null)[] = [null, ...path.map((node) => node.id)];
  const roots = nodes.filter((node) => node.parentId === null);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {parents.map((parentId, depth) => {
        const options = nodes.filter(
          (node) =>
            node.parentId === parentId &&
            !path.slice(0, depth).some((ancestor) => ancestor.id === node.id),
        );
        if (depth > 0 && options.length === 0) return null;
        return (
          <label key={parentId ?? "root"} className="flex min-w-0 flex-col gap-1 text-sm">
            <span>{depth === 0 ? labels.category : labels.subcategory}</span>
            <Select
              value={path[depth]?.id ?? ""}
              disabled={disabled || options.length === 0}
              onChange={(event) => {
                const next = event.target.value;
                if (!next || options.some((node) => node.id === next))
                  onChange(next || parentId || "");
              }}
            >
              <option value="">{labels.placeholder}</option>
              {options.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label}
                </option>
              ))}
            </Select>
          </label>
        );
      })}
      {!disabled && roots.length === 0 ? <p role="status">{labels.empty}</p> : null}
      {value && path.length === 0 ? <p role="alert">{labels.unavailable}</p> : null}
    </div>
  );
}
