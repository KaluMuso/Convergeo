import type { ReactNode } from "react";

export type ErrorStateProps = {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  /** Retry button label (caller-provided i18n key resolution). */
  retryLabel?: string;
  onRetry?: () => void;
  className?: string;
  "data-testid"?: string;
};

export function ErrorState({
  icon,
  title,
  body,
  action,
  retryLabel,
  onRetry,
  className,
  "data-testid": dataTestId,
}: ErrorStateProps) {
  return (
    <div
      className={className}
      data-testid={dataTestId ?? "error-state"}
      role="alert"
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
          color: "var(--danger)",
        }}
      >
        {title}
      </h3>
      {body && <p style={{ margin: 0, fontSize: "var(--fs-body)", maxWidth: "20rem" }}>{body}</p>}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--sp-3)",
          justifyContent: "center",
          marginTop: "var(--sp-2)",
        }}
      >
        {onRetry && retryLabel && (
          <button
            type="button"
            onClick={onRetry}
            data-testid={dataTestId ? `${dataTestId}-retry` : "error-state-retry"}
            style={{
              minHeight: "2.75rem",
              minWidth: "2.75rem",
              padding: "var(--sp-2) var(--sp-5)",
              background: "var(--primary)",
              color: "var(--surface)",
              border: "none",
              borderRadius: "var(--r)",
              fontSize: "var(--fs-body)",
              fontWeight: 600,
              cursor: "pointer",
              transition: `opacity var(--dur-fast) var(--ease-std)`,
            }}
          >
            {retryLabel}
          </button>
        )}
        {action}
      </div>
    </div>
  );
}
