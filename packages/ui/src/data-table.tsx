import type { ReactNode, TableHTMLAttributes } from "react";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export type DataTableProps = TableHTMLAttributes<HTMLTableElement> & {
  children: ReactNode;
};

/**
 * Lean semantic table shell. Visual layout (density, borders) stays in the host app via `className`.
 */
export function DataTable({ className, children, ...rest }: DataTableProps) {
  return (
    <table className={cx(className)} {...rest}>
      {children}
    </table>
  );
}
