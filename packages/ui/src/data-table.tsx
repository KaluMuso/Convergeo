"use client";

import { type ReactNode, type TableHTMLAttributes, useMemo, useState } from "react";

import { EmptyState, type EmptyStateProps } from "./empty-state";
import { NumberedPagination } from "./pagination";
import type { SpotIllustrationId } from "./spot-illustrations";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export type DataTableSortDirection = "asc" | "desc";

export type DataTableColumn<T> = {
  id: string;
  header: ReactNode;
  /** Plain-text column name for sort button labels (required when sortable). */
  sortLabel?: string;
  sortable?: boolean;
  /** Custom comparator; when omitted, `getSortValue` + localeCompare is used. */
  compare?: (a: T, b: T) => number;
  getSortValue?: (row: T) => string | number | null | undefined;
  cell: (row: T) => ReactNode;
  headerClassName?: string;
  cellClassName?: string;
};

export type DataTableLabels = {
  sortAscending: (column: string) => string;
  sortDescending: (column: string) => string;
  sortable: (column: string) => string;
  paginationAriaLabel: string;
  paginationPrevious: ReactNode;
  paginationNext: ReactNode;
  paginationPage: (page: number) => ReactNode;
};

export type DataTableProps = TableHTMLAttributes<HTMLTableElement> & {
  children: ReactNode;
};

/**
 * Semantic table shell. Density and borders stay in the host app via `className`.
 */
export function DataTable({ className, children, ...rest }: DataTableProps) {
  return (
    <table className={cx(className)} {...rest}>
      {children}
    </table>
  );
}

export type DataTableViewProps<T> = {
  rows: readonly T[];
  columns: readonly DataTableColumn<T>[];
  rowKey: (row: T) => string;
  labels: DataTableLabels;
  pageSize?: number;
  empty: Pick<EmptyStateProps, "title" | "body" | "illustration" | "action">;
  tableClassName?: string;
  className?: string;
  caption?: string;
  "data-testid"?: string;
};

const DEFAULT_PAGE_SIZE = 10;

function defaultCompare(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
  direction: DataTableSortDirection,
): number {
  const mult = direction === "asc" ? 1 : -1;
  if (a == null && b == null) {
    return 0;
  }
  if (a == null) {
    return 1;
  }
  if (b == null) {
    return -1;
  }
  if (typeof a === "number" && typeof b === "number") {
    return (a - b) * mult;
  }
  return (
    String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }) * mult
  );
}

function sortRows<T>(
  rows: readonly T[],
  column: DataTableColumn<T>,
  direction: DataTableSortDirection,
): T[] {
  const copy = [...rows];
  if (column.compare) {
    copy.sort((left, right) => {
      const base = column.compare!(left, right);
      return direction === "asc" ? base : -base;
    });
    return copy;
  }
  const getValue = column.getSortValue ?? (() => undefined);
  copy.sort((left, right) => defaultCompare(getValue(left), getValue(right), direction));
  return copy;
}

function ariaSortValue(
  active: boolean,
  direction: DataTableSortDirection | null,
): "ascending" | "descending" | "none" {
  if (!active || !direction) {
    return "none";
  }
  return direction === "asc" ? "ascending" : "descending";
}

/**
 * Client-side sort + numbered pagination + empty state for lean admin tables.
 */
export function DataTableView<T>({
  rows,
  columns,
  rowKey,
  labels,
  pageSize = DEFAULT_PAGE_SIZE,
  empty,
  tableClassName,
  className,
  caption,
  "data-testid": dataTestId,
}: DataTableViewProps<T>) {
  const [sortColumnId, setSortColumnId] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<DataTableSortDirection>("asc");
  const [page, setPage] = useState(1);

  const sortColumn = useMemo(
    () => columns.find((col) => col.id === sortColumnId && col.sortable),
    [columns, sortColumnId],
  );

  const sortedRows = useMemo(() => {
    if (!sortColumn) {
      return [...rows];
    }
    return sortRows(rows, sortColumn, sortDirection);
  }, [rows, sortColumn, sortDirection]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const safePage = Math.min(page, totalPages);

  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return sortedRows.slice(start, start + pageSize);
  }, [sortedRows, safePage, pageSize]);

  if (rows.length === 0) {
    return (
      <EmptyState
        title={empty.title}
        body={empty.body}
        illustration={empty.illustration as SpotIllustrationId | undefined}
        action={empty.action}
        data-testid="data-table-empty"
      />
    );
  }

  const handleSort = (column: DataTableColumn<T>) => {
    if (!column.sortable || !column.sortLabel) {
      return;
    }
    if (sortColumnId !== column.id) {
      setSortColumnId(column.id);
      setSortDirection("asc");
      setPage(1);
      return;
    }
    setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    setPage(1);
  };

  return (
    <div className={cx("flex flex-col gap-4", className)}>
      <div className="overflow-x-auto">
        <DataTable className={cx(tableClassName)} data-testid={dataTestId ?? "data-table"}>
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
              {columns.map((column) => {
                const isActive = sortColumnId === column.id;
                const direction = isActive ? sortDirection : null;
                const sortLabel = column.sortLabel ?? "";
                const canSort = column.sortable && column.sortLabel;

                if (!canSort) {
                  return (
                    <th
                      key={column.id}
                      scope="col"
                      className={cx("px-2 py-3 font-medium text-left", column.headerClassName)}
                    >
                      {column.header}
                    </th>
                  );
                }

                const ariaLabel = isActive
                  ? direction === "asc"
                    ? labels.sortAscending(sortLabel)
                    : labels.sortDescending(sortLabel)
                  : labels.sortable(sortLabel);

                return (
                  <th
                    key={column.id}
                    scope="col"
                    aria-sort={ariaSortValue(isActive, direction)}
                    className={cx("px-2 py-3 font-medium text-left", column.headerClassName)}
                  >
                    <button
                      type="button"
                      className={cx(
                        "inline-flex min-h-11 items-center gap-1 rounded-md text-left text-xs font-medium uppercase tracking-wide text-muted",
                        "hover:text-text focus-visible:outline-none focus-visible:shadow-focusRing",
                        isActive && "text-text",
                      )}
                      onClick={() => handleSort(column)}
                      aria-label={ariaLabel}
                    >
                      <span>{column.header}</span>
                      <span aria-hidden className="text-[0.65rem] leading-none">
                        {isActive ? (direction === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-border">
                {columns.map((column) => (
                  <td
                    key={column.id}
                    className={cx("px-2 py-3 align-middle", column.cellClassName)}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </DataTable>
      </div>
      {totalPages > 1 ? (
        <NumberedPagination
          page={safePage}
          totalPages={totalPages}
          onPageChange={setPage}
          previousLabel={labels.paginationPrevious}
          nextLabel={labels.paginationNext}
          pageLabel={labels.paginationPage}
          ariaLabel={labels.paginationAriaLabel}
        />
      ) : null}
    </div>
  );
}
