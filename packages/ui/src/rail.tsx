import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

type RailElement = "div" | "ul";

export type RailProps<T extends RailElement = "div"> = {
  as?: T;
  snap?: boolean;
  className?: string;
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<T>, "as" | "className" | "children">;

const SCROLL_CLASSES =
  "overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";

/**
 * Horizontal scroll container with hidden scrollbar. Gap, padding, and layout
 * classes are caller-supplied. Optional snap for touch carousels.
 */
export function Rail<T extends RailElement = "div">({
  as,
  snap = false,
  className,
  children,
  ...rest
}: RailProps<T>) {
  const Component = (as ?? "div") as ElementType;
  const classes = [SCROLL_CLASSES, snap ? "snap-x snap-mandatory" : undefined, className]
    .filter(Boolean)
    .join(" ");

  return (
    <Component className={classes} {...rest}>
      {children}
    </Component>
  );
}
