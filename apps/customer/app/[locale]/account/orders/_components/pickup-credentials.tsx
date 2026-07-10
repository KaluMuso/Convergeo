import type { PickupCredentials } from "./orders-api";

export type PickupCredentialsLabels = {
  title: string;
  qrLabel: string;
  pinLabel: string;
  stubBody: string;
  pinAria: string;
};

type PickupCredentialsBlockProps = {
  pickup: PickupCredentials;
  labels: PickupCredentialsLabels;
};

export function PickupCredentialsBlock({ pickup, labels }: PickupCredentialsBlockProps) {
  return (
    <section
      aria-labelledby="pickup-credentials-heading"
      className="space-y-3 rounded border border-border bg-surface p-4"
    >
      <h3 id="pickup-credentials-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>

      {pickup.stub ? (
        <p className="text-sm text-text-2">{labels.stubBody}</p>
      ) : (
        <div className="space-y-4">
          {pickup.qr_token ? (
            <div className="space-y-1">
              <p className="text-sm font-medium text-display-ink">{labels.qrLabel}</p>
              <p
                aria-label={labels.qrLabel}
                className="break-all rounded bg-bg-2 p-3 font-mono text-xs text-display-ink"
              >
                {pickup.qr_token}
              </p>
            </div>
          ) : null}
          {pickup.pin ? (
            <div className="space-y-1">
              <p className="text-sm font-medium text-display-ink">{labels.pinLabel}</p>
              <p
                aria-label={labels.pinAria.replace("{pin}", pickup.pin)}
                className="rounded bg-bg-2 p-3 font-mono text-lg tracking-widest text-display-ink"
              >
                {pickup.pin}
              </p>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
