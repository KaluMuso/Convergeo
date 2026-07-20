/**
 * Thin service-information strip above shop chrome (audit §5 / E05 trust relocation).
 * Factual fulfillment copy only — no active MoMo/card claims.
 */

export type ServiceInfoBarLabels = {
  ariaLabel: string;
  message: string;
};

type ServiceInfoBarProps = {
  labels: ServiceInfoBarLabels;
};

export function ServiceInfoBar({ labels }: ServiceInfoBarProps) {
  return (
    <div
      data-testid="service-info-bar"
      role="region"
      aria-label={labels.ariaLabel}
      className="border-b border-border bg-bg-2 text-text-2"
    >
      <p className="mx-auto m-0 flex min-h-9 max-w-7xl items-center justify-center px-4 py-1.5 text-center text-micro font-medium tracking-wide lg:px-6">
        {labels.message}
      </p>
    </div>
  );
}
