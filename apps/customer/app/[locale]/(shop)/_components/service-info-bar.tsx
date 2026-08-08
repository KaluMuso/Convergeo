/**
 * Compact fulfillment trust line — sits under the main shop header (not the top utility strip).
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
      className="border-b border-border bg-primary-tint/40 text-text-2"
    >
      <p className="mx-auto m-0 flex min-h-8 max-w-7xl items-center justify-center px-4 py-1 text-center text-micro font-medium tracking-wide lg:px-6">
        {labels.message}
      </p>
    </div>
  );
}
