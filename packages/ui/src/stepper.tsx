"use client";

import type { ComponentType, ReactNode } from "react";

export type StepperStep = {
  key: string;
  label: ReactNode;
  href?: string;
};

export type StepperState = "done" | "current" | "upcoming";

export type StepperLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
};

export type StepperProps = {
  steps: StepperStep[];
  currentStep: number;
  stepAnnouncement: (current: number, total: number) => ReactNode;
  doneIndicator: ReactNode;
  LinkComponent?: ComponentType<StepperLinkProps>;
  className?: string;
  /** When true, completed steps render as links. */
  completedStepsClickable?: boolean;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function getStepState(index: number, currentStep: number): StepperState {
  if (index < currentStep) {
    return "done";
  }
  if (index === currentStep) {
    return "current";
  }
  return "upcoming";
}

export function Stepper({
  steps,
  currentStep,
  stepAnnouncement,
  doneIndicator,
  LinkComponent = "a" as unknown as ComponentType<StepperLinkProps>,
  className,
  completedStepsClickable = false,
}: StepperProps) {
  const total = steps.length;

  if (total > 4) {
    throw new Error("Stepper supports at most 4 steps");
  }

  return (
    <div className={mergeClasses("w-full", className)} role="group">
      <p className="sr-only">{stepAnnouncement(currentStep + 1, total)}</p>
      <ol className="m-0 flex list-none items-start justify-between gap-2 p-0">
        {steps.map((step, index) => {
          const state = getStepState(index, currentStep);
          const stepNumber = index + 1;
          const isClickable = completedStepsClickable && state === "done" && step.href;

          const circleClasses = mergeClasses(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-pill text-sm font-semibold transition-colors",
            state === "done" && "bg-primary text-surface",
            state === "current" && "bg-primary-tint text-primary ring-2 ring-primary",
            state === "upcoming" && "bg-bg-2 text-text-3",
          );

          const labelClasses = mergeClasses(
            "mt-1 text-center text-micro font-medium",
            state === "current" && "text-primary",
            state === "done" && "text-text",
            state === "upcoming" && "text-text-3",
          );

          const content = (
            <>
              <span className={circleClasses} aria-hidden>
                {state === "done" ? doneIndicator : stepNumber}
              </span>
              <span className={labelClasses}>{step.label}</span>
            </>
          );

          return (
            <li
              key={step.key}
              className="flex min-w-0 flex-1 flex-col items-center"
              aria-current={state === "current" ? "step" : undefined}
            >
              {isClickable ? (
                <LinkComponent
                  href={step.href!}
                  className="flex flex-col items-center focus-visible:outline-none"
                  aria-label={typeof step.label === "string" ? step.label : undefined}
                >
                  {content}
                </LinkComponent>
              ) : (
                <div className="flex flex-col items-center">{content}</div>
              )}
              {index < steps.length - 1 ? <span className="absolute hidden" aria-hidden /> : null}
            </li>
          );
        })}
      </ol>
      <div className="relative -mt-6 flex px-4" aria-hidden>
        {steps.slice(0, -1).map((step, index) => {
          const state = getStepState(index, currentStep);
          return (
            <div
              key={`connector-${step.key}`}
              className={mergeClasses(
                "h-0.5 flex-1",
                state === "done" ? "bg-primary" : "bg-border",
              )}
              style={{ marginTop: "1rem" }}
            />
          );
        })}
      </div>
    </div>
  );
}
