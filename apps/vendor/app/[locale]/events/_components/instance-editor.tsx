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
  const endsAt = instance?.ends_at ? instance.ends_at.slice(0, 16) : "";
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
    // Optional — null when left blank (backend defaults / preserves).
    ends_at: draft.endsAt ? new Date(draft.endsAt).toISOString() : null,
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
        <h2 className="text-sm font-semibold text-foreground">{t("events.instances.heading")}</h2>
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
              <p className="text-xs font-medium text-muted-foreground">
                {t("events.instances.label", { index: index + 1 })}
              </p>
              {instances.length > 1 ? (
                <button
                  type="button"
                  className="text-xs text-destructive"
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
                onChange={(event) => updateAt(index, { startsAt: event.target.value })}
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
              <p className="text-xs text-muted-foreground">
                {t("events.instances.sold", { count: instance.ticketsSold ?? 0 })}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
