import { tokens } from "./tokens";
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
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

const linkStyle: CSSProperties = {
  color: tokens.colors.panelMuted,
  textDecoration: "none",
  display: "inline-flex",
  minHeight: "44px",
  alignItems: "center",
  fontSize: tokens.fontSize.sm,
  transition: `color ${tokens.transitionDuration.DEFAULT} ${tokens.transitionTimingFunction.out}`,
};

const headingStyle: CSSProperties = {
  margin: 0,
  marginBottom: tokens.spacing[3],
  fontSize: tokens.fontSize.sm,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: tokens.colors.panelText,
};

export function Footer({
  appName,
  copyright,
  columns,
  paymentNote,
  LinkComponent = "a" as unknown as ComponentType<FooterLinkProps>,
  className,
}: FooterProps) {
  return (
    <footer
      className={mergeClasses("w-full", className)}
      style={{
        backgroundColor: tokens.colors.panel,
        color: tokens.colors.panelText,
        borderTop: `1px solid ${tokens.colors.panelBorder}`,
      }}
    >
      <div
        style={{
          maxWidth: "80rem",
          margin: "0 auto",
          padding: `${tokens.spacing[8]} ${tokens.spacing[4]}`,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: tokens.spacing[6],
            marginBottom: tokens.spacing[8],
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
                  gap: tokens.spacing[1],
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
            borderTop: `1px solid ${tokens.colors.panelBorder}`,
            paddingTop: tokens.spacing[6],
            display: "flex",
            flexDirection: "column",
            gap: tokens.spacing[3],
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: tokens.fontSize.sm,
              color: tokens.colors.panelMuted,
            }}
          >
            {paymentNote}
          </p>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: tokens.spacing[2],
            }}
          >
            <p
              style={{
                margin: 0,
                fontFamily: tokens.fonts.display,
                fontSize: tokens.fontSize.h3,
                color: tokens.colors.panelText,
              }}
            >
              {appName}
            </p>
            <p
              style={{
                margin: 0,
                fontSize: tokens.fontSize.micro,
                color: tokens.colors.panelMuted,
              }}
            >
              {copyright}
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
