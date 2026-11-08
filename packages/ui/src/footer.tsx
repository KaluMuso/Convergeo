import type { ComponentType, CSSProperties, ReactNode } from "react";

export type FooterLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
};

export type FooterLink = {
  key: string;
  href: string;
  label: ReactNode;
};

export type FooterColumn = {
  key: string;
  heading: ReactNode;
  links: FooterLink[];
};

export type FooterProps = {
  appName: ReactNode;
  copyright: ReactNode;
  columns: FooterColumn[];
  paymentNote: ReactNode;
  LinkComponent?: ComponentType<FooterLinkProps>;
  className?: string;
  /** Optional trailing slot (e.g. quiet Display / theme link). */
  trailing?: ReactNode;
  /** Optional one-line promise under the wordmark. */
  tagline?: ReactNode;
  /** Optional escrow promise rendered with the copper-ringed seal. */
  sealLabel?: ReactNode;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/** Site footer. CSS variables keep seasonal and dark palette remaps live. */
export function Footer({
  appName,
  copyright,
  columns,
  paymentNote,
  LinkComponent = "a" as unknown as ComponentType<FooterLinkProps>,
  className,
  trailing,
  tagline,
  sealLabel,
}: FooterProps) {
  return (
    <footer className={mergeClasses("v-footer", className)}>
      <div className="v-footer__inner">
        <div className="v-footer__grid">
          <div className="v-footer__brand">
            <p className="v-footer__app-name">{appName}</p>
            {tagline ? <p className="v-footer__tagline">{tagline}</p> : null}
            {sealLabel ? (
              <p className="v-footer__seal" data-testid="footer-seal">
                <span aria-hidden className="ds-seal ds-seal--on-panel">
                  <svg
                    viewBox="0 0 24 24"
                    width="16"
                    height="16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M6 10V8a6 6 0 1 1 12 0v2M5 10h14v10H5zM12 14v2.5" />
                  </svg>
                </span>
                {sealLabel}
              </p>
            ) : null}
          </div>

          {columns.map((column) => (
            <div key={column.key} className="v-footer__column">
              <h2 className="v-footer__heading">{column.heading}</h2>
              <ul className="v-footer__links">
                {column.links.map((link) => (
                  <li key={link.key}>
                    <LinkComponent href={link.href} className="v-footer__link">
                      {link.label}
                    </LinkComponent>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div className="v-footer__payment">
            <p className="v-footer__meta">{paymentNote}</p>
            {trailing}
          </div>
        </div>

        <p className="v-footer__copyright">{copyright}</p>
      </div>
    </footer>
  );
}
