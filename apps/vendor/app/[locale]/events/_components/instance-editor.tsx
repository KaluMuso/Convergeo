"use client";

import { useTranslations } from "next-intl";

import { Button, FormField, Input } from "../_lib/ui";

import type { EventInstanceInput } from "../_lib/events-client";

export type InstanceDraft = {
  key: string;
  id?: string;
  startsAt: string;
  endsAt: string;
  capacity: string;
  ticketsSold?: number;
};

const DEFAULT_INSTANCE_DURATION_MS = 2 * 60 * 60 * 1000;

function localDateTimeMs(value: string): number {
  if (!value) {
    return Number.NaN;
  }
  return new Date(`${value}Z`).getTime();
}

export function defaultEndsAtForStart(startsAt: string): string {
  const startsAtMs = localDateTimeMs(startsAt);
  if (!Number.isFinite(startsAtMs)) {
    return "";
  }
  return new Date(startsAtMs + DEFAULT_INSTANCE_DURATION_MS).toISOString().slice(0, 16);
}

export function endsAtAfterStartChange(
  previousStartsAt: string,
  previousEndsAt: string,
  nextStartsAt: string,
): string {
  if (!nextStartsAt) {
    return "";
  }

  const previousDefault = defaultEndsAtForStart(previousStartsAt);
  const nextStartsAtMs = localDateTimeMs(nextStartsAt);
  const previousEndsAtMs = localDateTimeMs(previousEndsAt);
  const shouldUseDefault =
    !previousEndsAt ||
    previousEndsAt === previousDefault ||
    !Number.isFinite(previousEndsAtMs) ||
    previousEndsAtMs <= nextStartsAtMs;

  return shouldUseDefault ? defaultEndsAtForStart(nextStartsAt) : previousEndsAt;
}

export type InstanceDraftValidationError = "required" | "ends_before_starts";

export function validateInstanceDrafts(
  drafts: InstanceDraft[],
): InstanceDraftValidationError | null {
  for (const draft of drafts) {
    if (!draft.startsAt || !draft.endsAt) {
      return "required";
    }

    const startsAtMs = localDateTimeMs(draft.startsAt);
    const endsAtMs = localDateTimeMs(draft.endsAt);
    if (!Number.isFinite(startsAtMs) || !Number.isFinite(endsAtMs)) {
      return "required";
    }
    if (endsAtMs <= startsAtMs) {
      return "ends_before_starts";
    }
  }
  return null;
}

export function toInstanceDraft(
  instance?: {
    id: string;
    starts_at: string;
    ends_at?: string | null;
    capacity: number;
    tickets_sold?: number;
  },
  key?: string,
): InstanceDraft {
  const startsAt = instance?.starts_at ? instance.starts_at.slice(0, 16) : "";
  const endsAt = instance?.ends_at
    ? instance.ends_at.slice(0, 16)
    : defaultEndsAtForStart(startsAt);
  return {
    key: key ?? instance?.id ?? `new-${Math.random().toString(36).slice(2)}`,
    id: instance?.id,
    startsAt,
    endsAt,
    capacity: instance ? String(instance.capacity) : "50",
    ticketsSold: instance?.tickets_sold ?? 0,
  };
}

export function draftToPayload(drafts: InstanceDraft[]): EventInstanceInput[] {
  return drafts.map((draft) => ({
    id: draft.id,
    starts_at: new Date(draft.startsAt).toISOString(),
    // The editor validates this before serializing, so the API always receives an end.
    ends_at: new Date(draft.endsAt).toISOString(),
    capacity: Number.parseInt(draft.capacity, 10) || 0,
  }));
}

type InstanceEditorProps = {
  instances: InstanceDraft[];
  onChange: (instances: InstanceDraft[]) => void;
  disabled?: boolean;
};

export function InstanceEditor({ instances, onChange, disabled = false }: InstanceEditorProps) {
  const t = useTranslations("vendor");

  const updateAt = (index: number, patch: Partial<InstanceDraft>) => {
    onChange(instances.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  };

  const addInstance = () => {
    onChange([...instances, toInstanceDraft()]);
  };

  const removeAt = (index: number) => {
    if (instances.length <= 1) {
      return;
    }
    onChange(instances.filter((_, position) => position !== index));
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-text">{t("events.instances.heading")}</h2>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={addInstance}
          disabled={disabled}
          loadingLabel={t("events.instances.add")}
        >
          {t("events.instances.add")}
        </Button>
      </div>

      <ul className="space-y-3">
        {instances.map((instance, index) => (
          <li key={instance.key} className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-muted">
                {t("events.instances.label", { index: index + 1 })}
              </p>
              {instances.length > 1 ? (
                <button
                  type="button"
                  className="text-xs text-danger"
                  onClick={() => removeAt(index)}
                  disabled={disabled || (instance.ticketsSold ?? 0) > 0}
                >
                  {t("events.instances.remove")}
                </button>
              ) : null}
            </div>

            <FormField label={t("events.instances.startsAt")}>
              <Input
                type="datetime-local"
                value={instance.startsAt}
                onChange={(event) => {
                  const startsAt = event.target.value;
                  updateAt(index, {
                    startsAt,
                    endsAt: endsAtAfterStartChange(instance.startsAt, instance.endsAt, startsAt),
                  });
                }}
                disabled={disabled}
                required
              />
            </FormField>

            <FormField label={t("events.instances.endsAt")}>
              <Input
                type="datetime-local"
                value={instance.endsAt}
                min={instance.startsAt || undefined}
                onChange={(event) => updateAt(index, { endsAt: event.target.value })}
                disabled={disabled}
                required
              />
            </FormField>

            <FormField label={t("events.instances.capacity")}>
              <Input
                type="number"
                min={instance.ticketsSold ?? 0}
                inputMode="numeric"
                value={instance.capacity}
                onChange={(event) => updateAt(index, { capacity: event.target.value })}
                disabled={disabled}
                required
              />
            </FormField>

            {(instance.ticketsSold ?? 0) > 0 ? (
              <p className="text-xs text-muted">
                {t("events.instances.sold", { count: instance.ticketsSold ?? 0 })}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
