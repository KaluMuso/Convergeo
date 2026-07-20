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

function DefaultErrorIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 7v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="16.5" r="1" fill="currentColor" />
    </svg>
  );
}

/**
 * Error-state foundation with optional retry. Uses `--primary-btn-fg` so the
 * retry CTA stays AA in dark mode.
 */
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
      <div
        aria-hidden="true"
        style={{
          color: "var(--danger)",
          marginBottom: "var(--sp-2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {icon ?? <DefaultErrorIcon />}
      </div>
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
      {body ? (
        <p style={{ margin: 0, fontSize: "var(--fs-body)", maxWidth: "20rem" }}>{body}</p>
      ) : null}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--sp-3)",
          justifyContent: "center",
          marginTop: "var(--sp-2)",
        }}
      >
        {onRetry && retryLabel ? (
          <button
            type="button"
            onClick={onRetry}
            data-testid={dataTestId ? `${dataTestId}-retry` : "error-state-retry"}
            style={{
              minHeight: "2.75rem",
              minWidth: "2.75rem",
              padding: "var(--sp-2) var(--sp-5)",
              background: "var(--primary)",
              color: "var(--primary-btn-fg)",
              border: "none",
              borderRadius: "var(--r)",
              fontSize: "var(--fs-body)",
              fontWeight: 600,
              cursor: "pointer",
              transition: `opacity var(--dur-fast) var(--ease-std), transform var(--dur-fast) var(--ease-std)`,
            }}
          >
            {retryLabel}
          </button>
        ) : null}
        {action}
      </div>
    </div>
  );
}
