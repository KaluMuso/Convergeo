import type { ReactNode } from "react";

export type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

export function EmptyState({
  icon,
  title,
  body,
  action,
  className,
  "data-testid": dataTestId,
}: EmptyStateProps) {
  return (
    <div
      className={className}
      data-testid={dataTestId ?? "empty-state"}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        padding: "var(--sp-8) var(--sp-4)",
        gap: "var(--sp-3)",
        color: "var(--text-2)",
      }}
    >
      {icon && (
        <div
          aria-hidden="true"
          style={{ fontSize: "2.5rem", lineHeight: 1, marginBottom: "var(--sp-2)" }}
        >
          {icon}
        </div>
      )}
      <h3
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--fs-h3)",
          color: "var(--display-ink)",
        }}
      >
        {title}
      </h3>
      {body && <p style={{ margin: 0, fontSize: "var(--fs-body)", maxWidth: "20rem" }}>{body}</p>}
      {action && <div style={{ marginTop: "var(--sp-2)" }}>{action}</div>}
    </div>
  );
}
