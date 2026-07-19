type AdminLoadFailureProps = {
  permissionDenied: boolean;
  message: string;
  hint?: string;
  retryLabel: string;
  onRetry: () => void;
};

/** Shared load-failure panel: permission-denied (warning) vs retryable error. */
export function AdminLoadFailure({
  permissionDenied,
  message,
  hint,
  retryLabel,
  onRetry,
}: AdminLoadFailureProps) {
  if (permissionDenied) {
    return (
      <div
        className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-4"
        data-testid="admin-permission-denied"
      >
        <p className="text-sm font-medium text-warning">{message}</p>
        {hint ? <p className="text-xs text-muted">{hint}</p> : null}
        <button
          type="button"
          className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
          onClick={onRetry}
        >
          {retryLabel}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="admin-load-error">
      <p className="text-sm text-danger">{message}</p>
      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm"
        onClick={onRetry}
      >
        {retryLabel}
      </button>
    </div>
  );
}
