import { ONBOARDING_STEPS, type OnboardingStepKey } from "../_lib/types";
import { Stepper } from "../_lib/ui";

type StepProgressProps = {
  currentStep: number;
  labels: Record<OnboardingStepKey, string>;
  stepAnnouncement: (current: number, total: number) => string;
  doneIndicator: string;
};

export function StepProgress({
  currentStep,
  labels,
  stepAnnouncement,
  doneIndicator,
}: StepProgressProps) {
  const steps = ONBOARDING_STEPS.map((key) => ({
    key,
    label: labels[key],
  }));

  return (
    <Stepper
      steps={steps}
      currentStep={currentStep}
      stepAnnouncement={(current: number, total: number) => stepAnnouncement(current, total)}
      doneIndicator={doneIndicator}
      className="mb-6"
    />
  );
}
