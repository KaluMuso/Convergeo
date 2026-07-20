import type { ReactNode, SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & {
  /** Accessible title; omit for decorative icons (parent provides aria-label). */
  title?: string;
};

function BaseIcon({ title, children, className, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      className={["h-[1.15em] w-[1.15em] shrink-0", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export function IconHome(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z" />
    </BaseIcon>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </BaseIcon>
  );
}

export function IconAsk(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
      <circle cx="12" cy="12" r="3.25" />
    </BaseIcon>
  );
}

export function IconOrders(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M7 4h10l1 4H6l1-4Z" />
      <path d="M6 8h12l-1.2 11.2a1 1 0 0 1-1 .8H8.2a1 1 0 0 1-1-.8L6 8Z" />
      <path d="M10 12h4" />
    </BaseIcon>
  );
}

export function IconAccount(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 19.5c1.6-3.2 4-4.5 7-4.5s5.4 1.3 7 4.5" />
    </BaseIcon>
  );
}

export function IconCart(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3.5 5h2l1.2 11h11.6l1.5-8H7" />
      <circle cx="10" cy="19.5" r="1.25" />
      <circle cx="16.5" cy="19.5" r="1.25" />
    </BaseIcon>
  );
}

export function IconDirectory(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H11l2 2h4.5A2.5 2.5 0 0 1 20 9.5v7A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-9Z" />
    </BaseIcon>
  );
}

export function IconCategories(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 4h7v7H4V4ZM13 4h7v7h-7V4ZM4 13h7v7H4v-7ZM13 13h7v7h-7v-7Z" />
    </BaseIcon>
  );
}

export function IconEvents(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4" y="6" width="16" height="14" rx="2" />
      <path d="M8 4v4M16 4v4M4 11h16" />
    </BaseIcon>
  );
}

export function IconServices(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M14.5 5.5 18.5 9.5 9 19H5v-4l9.5-9.5Z" />
      <path d="m12.5 7.5 4 4" />
    </BaseIcon>
  );
}

export function IconChevronDown(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m6 9 6 6 6-6" />
    </BaseIcon>
  );
}

export function IconHeart(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M12 19s-7-4.35-7-9.2A3.8 3.8 0 0 1 12 7a3.8 3.8 0 0 1 7 2.8C19 14.65 12 19 12 19Z" />
    </BaseIcon>
  );
}
