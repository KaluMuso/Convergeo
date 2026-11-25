import type { ReactElement, SVGProps } from "react";

export type SpotIllustrationId =
  | "empty-cart"
  | "no-orders"
  | "no-products"
  | "verify-id"
  | "payment-success"
  | "no-results"
  | "offline"
  | "welcome-shop";

export type SpotIllustrationProps = SVGProps<SVGSVGElement> & {
  id: SpotIllustrationId;
};

function spotSvg(children: React.ReactNode, props: SVGProps<SVGSVGElement>): ReactElement {
  return (
    <svg
      viewBox="0 0 120 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-hidden
      {...props}
    >
      {children}
    </svg>
  );
}

const BODIES: Record<SpotIllustrationId, (props: SVGProps<SVGSVGElement>) => ReactElement> = {
  "empty-cart": (props) =>
    spotSvg(
      <>
        <rect x="28" y="36" width="64" height="40" rx="8" stroke="currentColor" strokeWidth="2" />
        <path d="M36 36V32a24 24 0 0 1 48 0v4" stroke="currentColor" strokeWidth="2" />
        <circle
          cx="44"
          cy="80"
          r="4"
          fill="var(--primary-tint)"
          stroke="currentColor"
          strokeWidth="2"
        />
        <circle
          cx="76"
          cy="80"
          r="4"
          fill="var(--primary-tint)"
          stroke="currentColor"
          strokeWidth="2"
        />
      </>,
      props,
    ),
  "no-orders": (props) =>
    spotSvg(
      <>
        <rect x="32" y="24" width="56" height="64" rx="6" stroke="currentColor" strokeWidth="2" />
        <path
          d="M40 40h40M40 52h32M40 64h24"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle
          cx="76"
          cy="20"
          r="8"
          fill="var(--primary-tint)"
          stroke="currentColor"
          strokeWidth="2"
        />
      </>,
      props,
    ),
  "no-products": (props) =>
    spotSvg(
      <>
        <path d="M24 68h72" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <rect x="36" y="32" width="48" height="36" rx="6" stroke="currentColor" strokeWidth="2" />
        <path
          d="M48 44h24M48 54h16"
          stroke="var(--primary)"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.7"
        />
      </>,
      props,
    ),
  "verify-id": (props) =>
    spotSvg(
      <>
        <rect x="34" y="28" width="52" height="40" rx="6" stroke="currentColor" strokeWidth="2" />
        <circle cx="48" cy="44" r="8" stroke="currentColor" strokeWidth="2" />
        <path d="M66 56H42" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path
          d="M72 36l6 6 12-14"
          stroke="var(--primary)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </>,
      props,
    ),
  "payment-success": (props) =>
    spotSvg(
      <>
        <circle cx="60" cy="48" r="28" stroke="currentColor" strokeWidth="2" />
        <path
          d="M44 48l10 10 22-24"
          stroke="var(--primary)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </>,
      props,
    ),
  "no-results": (props) =>
    spotSvg(
      <>
        <circle cx="52" cy="44" r="20" stroke="currentColor" strokeWidth="2" />
        <path d="M66 58l16 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path
          d="M44 44h16M52 36v16"
          stroke="var(--primary)"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.5"
        />
      </>,
      props,
    ),
  offline: (props) =>
    spotSvg(
      <>
        <path
          d="M24 56c12-16 28-24 36-24s24 8 36 24"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path d="M40 64h40" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle
          cx="60"
          cy="72"
          r="3"
          fill="var(--primary-tint)"
          stroke="currentColor"
          strokeWidth="2"
        />
      </>,
      props,
    ),
  "welcome-shop": (props) =>
    spotSvg(
      <>
        <path
          d="M24 68V44l36-20 36 20v24"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        <rect x="48" y="52" width="24" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M56 44v8" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" />
      </>,
      props,
    ),
};

export function SpotIllustration({ id, ...props }: SpotIllustrationProps) {
  return BODIES[id](props);
}
