export type ServiceHowItWorksLabels = {
  heading: string;
  step1: string;
  step2: string;
  step3: string;
  escrow?: string;
};

type ServiceHowItWorksProps = {
  labels: ServiceHowItWorksLabels;
  showEscrow: boolean;
};

const STEPS: Array<keyof Pick<ServiceHowItWorksLabels, "step1" | "step2" | "step3">> = [
  "step1",
  "step2",
  "step3",
];

export function ServiceHowItWorks({ labels, showEscrow }: ServiceHowItWorksProps) {
  return (
    <section
      className="rounded-lg border border-border bg-bg-2 p-5"
      aria-labelledby="service-how-heading"
    >
      <h2 id="service-how-heading" className="font-display text-h3 text-display-ink">
        {labels.heading}
      </h2>
      <ol className="mt-3 flex list-none flex-col gap-3 p-0">
        {STEPS.map((key, index) => (
          <li key={key} className="flex items-start gap-3 text-sm text-text-2">
            <span
              aria-hidden
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 font-semibold text-primary"
            >
              {index + 1}
            </span>
            <span>{labels[key]}</span>
          </li>
        ))}
      </ol>
      {showEscrow && labels.escrow ? (
        <p className="mt-4 text-sm text-text-2">{labels.escrow}</p>
      ) : null}
    </section>
  );
}
