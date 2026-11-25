import type { ReactNode } from "react";

export type CustomerRouteShellProps = {
  children: ReactNode;
  className?: string;
  width?: "shop" | "content" | "full";
};

const WIDTH_CLASS: Record<NonNullable<CustomerRouteShellProps["width"]>, string> = {
  shop: "mx-auto w-full max-w-6xl",
  content: "mx-auto w-full max-w-3xl",
  full: "w-full",
};

export function CustomerRouteShell({
  children,
  className,
  width = "shop",
}: CustomerRouteShellProps) {
  return (
    <div
      className={[WIDTH_CLASS[width], "animate-page-in motion-reduce:animate-none", className]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}
