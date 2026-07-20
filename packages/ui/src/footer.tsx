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

const linkStyle: CSSProperties = {
  color: "var(--panel-muted)",
  textDecoration: "none",
  display: "inline-flex",
  minHeight: "44px",
  alignItems: "center",
  fontSize: "var(--fs-sm)",
  transition: "color var(--dur) var(--ease-out)",
};

const headingStyle: CSSProperties = {
  margin: 0,
  marginBottom: "var(--sp-3)",
  fontSize: "var(--fs-sm)",
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--panel-text)",
};

/**
 * Site footer — uses CSS variables for panel chrome so theme remaps apply
 * (no frozen JS hex from tokens.ts).
 */
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
    <footer
      className={mergeClasses("w-full", className)}
      style={{
        backgroundColor: "var(--panel)",
        color: "var(--panel-text)",
        borderTop: "1px solid var(--panel-border)",
      }}
    >
      <div
        style={{
          maxWidth: "var(--container-max)",
          margin: "0 auto",
          padding: "var(--sp-8) var(--container-gutter)",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "var(--sp-6)",
            marginBottom: "var(--sp-8)",
          }}
        >
          {columns.map((column) => (
            <div key={column.key}>
              <h2 style={headingStyle}>{column.heading}</h2>
              <ul
                style={{
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--sp-1)",
                }}
              >
                {column.links.map((link) => (
                  <li key={link.key}>
                    <LinkComponent href={link.href} style={linkStyle}>
                      {link.label}
                    </LinkComponent>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div
          style={{
            borderTop: "1px solid var(--panel-border)",
            paddingTop: "var(--sp-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-3)",
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: "var(--fs-sm)",
              color: "var(--panel-muted)",
            }}
          >
            {paymentNote}
          </p>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
            }}
          >
            <p
              style={{
                margin: 0,
                fontFamily: "var(--font-display)",
                fontSize: "var(--fs-h3)",
                color: "var(--panel-text)",
              }}
            >
              {appName}
            </p>
            <p
              style={{
                margin: 0,
                fontSize: "var(--fs-micro)",
                color: "var(--panel-muted)",
              }}
            >
              {copyright}
            </p>
            {trailing}
          </div>
        </div>
      </div>
    </footer>
  );
}
