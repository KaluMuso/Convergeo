"use client";

import { Button } from "../_lib/ui";

type ReviewStepProps = {
  businessName: string;
  businessCategory: string;
  businessCategoryLabel: string;
  momoPhone: string;
  nrcUploaded: boolean;
  selfieUploaded: boolean;
  onEditBusiness: () => void;
  onEditDocs: () => void;
  onSubmit: () => void;
  labels: {
    heading: string;
    intro: string;
    businessSection: string;
    docsSection: string;
    momoSection: string;
    nrcUploaded: string;
    selfieUploaded: string;
    notUploaded: string;
    submit: string;
    submitting: string;
    editBusiness: string;
    editDocs: string;
    gateNotice: string;
  };
  submitting?: boolean;
};

export function ReviewStep({
  businessName,
  businessCategory,
  businessCategoryLabel,
  momoPhone,
  nrcUploaded,
  selfieUploaded,
  onEditBusiness,
  onEditDocs,
  onSubmit,
  labels,
  submitting = false,
}: ReviewStepProps) {
  return (
    <div className="flex flex-col gap-4">
      <header className="space-y-1">
        <h1 className="font-display text-h3 text-display-ink">{labels.heading}</h1>
        <p className="text-sm text-text-2">{labels.intro}</p>
      </header>

      <section className="rounded border border-border p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-text">{labels.businessSection}</h2>
          <button
            type="button"
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
            onClick={onEditBusiness}
          >
            {labels.editBusiness}
          </button>
        </div>
        <dl className="m-0 space-y-1 text-sm">
          <div>
            <dt className="text-text-3">{labels.businessSection}</dt>
            <dd className="font-medium text-text">{businessName}</dd>
          </div>
          <div>
            <dt className="text-text-3">{labels.businessSection}</dt>
            <dd className="text-text">{businessCategoryLabel || businessCategory}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded border border-border p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-text">{labels.docsSection}</h2>
          <button
            type="button"
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
            onClick={onEditDocs}
          >
            {labels.editDocs}
          </button>
        </div>
        <ul className="m-0 list-none space-y-1 p-0 text-sm">
          <li className={nrcUploaded ? "text-success" : "text-danger"}>
            {nrcUploaded ? labels.nrcUploaded : labels.notUploaded}
          </li>
          <li className={selfieUploaded ? "text-success" : "text-danger"}>
            {selfieUploaded ? labels.selfieUploaded : labels.notUploaded}
          </li>
        </ul>
      </section>

      <section className="rounded border border-border p-4">
        <h2 className="mb-1 text-sm font-semibold text-text">{labels.momoSection}</h2>
        <p className="m-0 text-sm text-text">{momoPhone}</p>
      </section>

      <p className="rounded bg-primary-tint px-3 py-2 text-sm text-primary">{labels.gateNotice}</p>

      <Button
        type="button"
        className="w-full"
        loading={submitting}
        loadingLabel={labels.submitting}
        onClick={onSubmit}
      >
        {labels.submit}
      </Button>
    </div>
  );
}
