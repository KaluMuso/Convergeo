"use client";

import { RequestQuoteButton } from "../../../_components/pdp/request-quote-button";

import type { RequestQuoteLabels } from "../../../_components/pdp/request-quote-button";

type ServiceQuoteCtaProps = {
  locale: string;
  serviceId: string;
  vendorName: string;
  labels: RequestQuoteLabels;
  hint: string;
};

export function ServiceQuoteCta({
  locale,
  serviceId,
  vendorName,
  labels,
  hint,
}: ServiceQuoteCtaProps) {
  return (
    <>
      <RequestQuoteButton
        locale={locale}
        serviceId={serviceId}
        vendorName={vendorName}
        labels={labels}
        variant="primary"
        className="w-full rounded-md text-sm font-semibold"
      />
      <p className="text-center text-xs text-text-3">{hint}</p>
    </>
  );
}
