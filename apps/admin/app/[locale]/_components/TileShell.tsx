"use client";

import type { ReactNode } from "react";

type TileShellProps = {
  title: string;
  subtitle?: string;
  status?: "success" | "danger" | "warning";
  className?: string;
  children: ReactNode;
};

const STATUS_BORDER: Record<NonNullable<TileShellProps["status"]>, string> = {
  success: "border-success/30",
  danger: "border-danger/30",
  warning: "border-warning/40",
};

export function TileShell({ title, subtitle, status, className = "", children }: TileShellProps) {
  const borderClass = status ? STATUS_BORDER[status] : "border-border";

  return (
    <section
      className={`rounded-lg border ${borderClass} bg-surface p-4 shadow-sm ${className}`.trim()}
    >
      <header className="mb-3 space-y-1">
        <h2 className="font-serif text-base text-text">{title}</h2>
        {subtitle ? <p className="text-xs text-muted">{subtitle}</p> : null}
      </header>
      {children}
    </section>
  );
}
