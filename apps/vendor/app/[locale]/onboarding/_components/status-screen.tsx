import { hasAuditableKycRecord, type KycIntegrityInput } from "../../_lib/kyc-integrity";

import type { KycStatus } from "../_lib/types";

export type StatusVariant = "pending" | "approved" | "rejected" | "resubmit";

export function resolveStatusVariant(kycStatus: KycStatus): StatusVariant {
  switch (kycStatus) {
    case "submitted":
      return "pending";
    case "approved":
      return "approved";
    case "rejected":
      return "rejected";
    case "resubmit":
      return "resubmit";
    default:
      return "pending";
  }
}

/**
 * Never surface "approved" without an auditable KYC record (VEND-01 / MR-D02).
 * Orphaned tier badges fall back to pending so the UI cannot claim verification.
 */
export function resolveHonestStatusVariant(
  input: Pick<KycIntegrityInput, "kyc_status" | "kyc_record_id"> & {
    kyc_status: KycStatus;
  },
): StatusVariant {
  const base = resolveStatusVariant(input.kyc_status);
  if (
    base === "approved" &&
    !hasAuditableKycRecord({ ...input, kyc_tier: null, kyc_record_status: null })
  ) {
    return "pending";
  }
  return base;
}

type StatusScreenProps = {
  variant: StatusVariant;
  rejectionReason?: string | null;
  labels: {
    heading: string;
    pending: { title: string; body: string; cta: string };
    approved: { title: string; body: string; cta: string; t2Link: string };
    rejected: {
      title: string;
      body: string;
      reasonLabel: string;
      resubmitCta: string;
      gateNotice: string;
    };
    resubmit: { title: string; body: string; submit: string };
    t2: { stubLabel: string; stubBody: string };
  };
  dashboardHref: string;
  listingsHref: string;
  resubmitHref: string;
};

export function StatusScreen({
  variant,
  rejectionReason,
  labels,
  dashboardHref,
  listingsHref,
  resubmitHref,
}: StatusScreenProps) {
  const copy =
    variant === "approved"
      ? labels.approved
      : variant === "rejected"
        ? labels.rejected
        : variant === "resubmit"
          ? labels.resubmit
          : labels.pending;

  const primaryHref =
    variant === "approved" ? listingsHref : variant === "rejected" ? resubmitHref : dashboardHref;

  const primaryCta =
    variant === "approved"
      ? labels.approved.cta
      : variant === "rejected"
        ? labels.rejected.resubmitCta
        : labels.pending.cta;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[360px] flex-col gap-4 p-4">
      <header>
        <h1 className="font-display text-h3 text-display-ink">{labels.heading}</h1>
      </header>

      <section className="flex flex-1 flex-col gap-3 rounded border border-border p-4">
        <h2 className="text-lg font-semibold text-text">{copy.title}</h2>
        <p className="text-sm text-text-2">{copy.body}</p>

        {variant === "rejected" && rejectionReason ? (
          <div className="rounded bg-bg-2 p-3 text-sm">
            <p className="mb-1 font-medium text-text">{labels.rejected.reasonLabel}</p>
            <p className="m-0 text-text-2">{rejectionReason}</p>
          </div>
        ) : null}

        {variant === "rejected" ? (
          <p className="text-sm text-text-2">{labels.rejected.gateNotice}</p>
        ) : null}

        <a
          href={primaryHref}
          className="mt-auto inline-flex h-11 min-h-11 w-full items-center justify-center rounded bg-primary px-4 text-body font-medium text-surface transition-colors hover:bg-primary-deep focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {primaryCta}
        </a>

        {variant === "approved" ? (
          <div className="rounded border border-dashed border-border p-3 text-sm">
            <p className="mb-1 font-medium text-text">{labels.t2.stubLabel}</p>
            <p className="m-0 text-text-2">{labels.t2.stubBody}</p>
          </div>
        ) : null}
      </section>
    </main>
  );
}
