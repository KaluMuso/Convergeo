import type { InvoiceLink } from "./orders-api";

export type InvoiceLinkLabels = {
  title: string;
  download: string;
  stubHelp: string;
  unavailable: string;
};

type InvoiceLinkBlockProps = {
  invoice: InvoiceLink | null;
  labels: InvoiceLinkLabels;
};

export function InvoiceLinkBlock({ invoice, labels }: InvoiceLinkBlockProps) {
  if (!invoice) {
    return (
      <section className="rounded border border-border bg-surface p-4">
        <h3 className="font-display text-h3 text-display-ink">{labels.title}</h3>
        <p className="mt-2 text-sm text-text-2">{labels.unavailable}</p>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="invoice-link-heading"
      className="space-y-2 rounded border border-border bg-surface p-4"
    >
      <h3 id="invoice-link-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>
      {invoice.download_url ? (
        <a
          href={invoice.download_url}
          className="inline-flex min-h-11 items-center rounded bg-primary px-4 text-sm font-medium text-surface hover:opacity-90"
          aria-disabled={invoice.stub}
        >
          {labels.download}
        </a>
      ) : null}
      {invoice.stub ? <p className="text-xs text-text-2">{labels.stubHelp}</p> : null}
    </section>
  );
}
