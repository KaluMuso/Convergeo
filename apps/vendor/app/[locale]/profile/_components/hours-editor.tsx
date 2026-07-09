"use client";

import { useTranslations } from "next-intl";

import { FormField, Input } from "../../listings/new/_lib/ui";

import type { VendorProfile } from "../_lib/profile-client";

const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

type DayKey = (typeof DAY_KEYS)[number];

type HoursEditorProps = {
  hours: VendorProfile["hours"];
  disabled: boolean;
  onChange: (hours: VendorProfile["hours"]) => void;
};

function defaultDay(): { open: string; close: string; closed: boolean } {
  return { open: "08:00", close: "17:00", closed: false };
}

export function HoursEditor({ hours, disabled, onChange }: HoursEditorProps) {
  const t = useTranslations("vendor");

  const updateDay = (
    day: DayKey,
    patch: Partial<{ open: string; close: string; closed: boolean }>,
  ) => {
    const current = hours[day] ?? defaultDay();
    onChange({
      ...hours,
      [day]: {
        ...current,
        ...patch,
      },
    });
  };

  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="text-sm font-medium text-neutral-900">
        {t("profile.fields.hoursLabel")}
      </legend>
      <p className="text-sm text-neutral-600">{t("profile.fields.hoursHelp")}</p>
      <div className="space-y-3">
        {DAY_KEYS.map((day) => {
          const dayHours = hours[day] ?? defaultDay();
          const isClosed = dayHours.closed === true;
          return (
            <div key={day} className="rounded-lg border border-neutral-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-neutral-800">
                  {t(`profile.hours.days.${day}`)}
                </span>
                <label className="flex items-center gap-2 text-sm text-neutral-600">
                  <input
                    type="checkbox"
                    checked={isClosed}
                    onChange={(event) => updateDay(day, { closed: event.target.checked })}
                  />
                  {t("profile.hours.closed")}
                </label>
              </div>
              {!isClosed ? (
                <div className="grid grid-cols-2 gap-3">
                  <FormField label={t("profile.hours.open")}>
                    <Input
                      type="time"
                      value={dayHours.open ?? "08:00"}
                      onChange={(event) => updateDay(day, { open: event.target.value })}
                    />
                  </FormField>
                  <FormField label={t("profile.hours.close")}>
                    <Input
                      type="time"
                      value={dayHours.close ?? "17:00"}
                      onChange={(event) => updateDay(day, { close: event.target.value })}
                    />
                  </FormField>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
