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
}: FooterProps) {
  return (
    <footer className={mergeClasses("v-footer", className)}>
      <div className="v-footer__inner">
        <div className="v-footer__grid">
          <div className="v-footer__brand">
            <p className="v-footer__app-name">{appName}</p>
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
