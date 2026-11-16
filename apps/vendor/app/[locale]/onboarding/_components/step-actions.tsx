"use client";

import { Button } from "../_lib/ui";

type StepActionsProps = {
  /** Hidden on the first step and in resubmit mode, where there is nothing to go back to. */
  showBack: boolean;
  onBack: () => void;
  onSaveLater: () => void;
  saving: boolean;
  /** Result of the last "Save and continue later" press. */
  notice: { kind: "saved" | "savedLocal"; text: string } | null;
  labels: {
    back: string;
    saveLater: string;
    saving: string;
  };
};

/** Back + "Save and continue later" row shown under every onboarding step. */
export function StepActions({
  showBack,
  onBack,
  onSaveLater,
  saving,
  notice,
  labels,
}: StepActionsProps) {
  return (
    <div className="flex flex-col gap-2" data-testid="onboarding-step-actions">
      <div className="flex flex-wrap items-center gap-2">
        {showBack ? (
          <Button
            type="button"
            variant="ghost"
            loadingLabel={labels.back}
            onClick={onBack}
            data-testid="onboarding-back"
          >
            {labels.back}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="secondary"
          loading={saving}
          loadingLabel={labels.saving}
          onClick={onSaveLater}
          data-testid="onboarding-save-later"
        >
          {labels.saveLater}
        </Button>
      </div>
      {notice ? (
        <p
          role="status"
          data-testid="onboarding-save-notice"
          className={notice.kind === "saved" ? "text-sm text-success" : "text-sm text-text-2"}
        >
          {notice.text}
        </p>
      ) : null}
    </div>
  );
}
