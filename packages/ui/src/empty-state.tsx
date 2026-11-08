import type { ReactNode } from "react";

export type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

function DefaultEmptyIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3 9h18" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8" cy="14" r="1" fill="currentColor" />
      <circle cx="12" cy="14" r="1" fill="currentColor" />
      <circle cx="16" cy="14" r="1" fill="currentColor" />
    </svg>
  );
}

/**
 * Empty-state foundation — SVG default icon (no emoji). Callers inject i18n
 * title/body/action.
 */
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
        padding: "var(--sp-12) var(--sp-4)",
        gap: "var(--sp-3)",
        color: "var(--text-2)",
        border: "1px dashed var(--border)",
        borderRadius: "var(--r-lg)",
        background: "var(--surface)",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          color: "var(--primary)",
          background: "var(--primary-tint)",
          width: "4rem",
          height: "4rem",
          borderRadius: "var(--r-pill)",
          marginBottom: "var(--sp-2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {icon ?? <DefaultEmptyIcon />}
      </div>
      <h3
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "1.25rem",
          fontWeight: 700,
          color: "var(--display-ink)",
        }}
      >
        {title}
      </h3>
      {body ? (
        <p style={{ margin: 0, fontSize: "var(--fs-body)", maxWidth: "26rem", lineHeight: 1.55 }}>
          {body}
        </p>
      ) : null}
      {action ? <div style={{ marginTop: "var(--sp-2)" }}>{action}</div> : null}
    </div>
  );
}
