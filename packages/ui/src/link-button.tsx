import type { AnchorHTMLAttributes, ComponentType, ReactNode } from "react";

import {
  buttonBaseClasses,
  buttonSizeClasses,
  buttonVariantClasses,
  type ButtonSize,
  type ButtonVariant,
} from "./button";

export type LinkButtonLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
};

export type LinkButtonProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
  /** Inject Next.js `Link` (or equivalent) without coupling this package to next/link. */
  LinkComponent?: ComponentType<LinkButtonLinkProps>;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Anchor styled as a Button variant. RSC-safe; pass `LinkComponent={Link}` from
 * the app for client-side navigation.
 */
export function LinkButton({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
  LinkComponent,
  ...rest
}: LinkButtonProps) {
  const classes = cx(
    buttonBaseClasses,
    buttonVariantClasses[variant],
    buttonSizeClasses[size],
    className,
  );

  if (LinkComponent) {
    return (
      <LinkComponent href={href} className={classes} {...rest}>
        {children}
      </LinkComponent>
    );
  }

  return (
    <a href={href} className={classes} {...rest}>
      {children}
    </a>
  );
}
