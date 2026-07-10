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
  success: "border-[#B7DFC5]",
  danger: "border-[#E8B4B4]",
  warning: "border-[#F0D49A]",
};

export function TileShell({ title, subtitle, status, className = "", children }: TileShellProps) {
  const borderClass = status ? STATUS_BORDER[status] : "border-[#F0E9DE]";

  return (
    <section
      className={`rounded-lg border ${borderClass} bg-white p-4 shadow-sm ${className}`.trim()}
    >
      <header className="mb-3 space-y-1">
        <h2 className="font-serif text-base text-[#2A2118]">{title}</h2>
        {subtitle ? <p className="text-xs text-[#6B5E4C]">{subtitle}</p> : null}
      </header>
      {children}
    </section>
  );
}
