"use client";

import { ApiError } from "@vergeo/config";
import { Button } from "@vergeo/ui/src/button";
import { Checkbox } from "@vergeo/ui/src/checkbox";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Select } from "@vergeo/ui/src/select";
import { useState, type FormEvent } from "react";

import { createAccountApiClient, type Birthday } from "./account-api";

/**
 * Optional birthday (day + month, year optional) for a yearly treat. Both boxes
 * start UNTICKED: marketing consent and an 18+ confirmation. Removing the
 * birthday withdraws consent and erases it.
 */
export type BirthdayLabels = {
  title: string;
  intro: string;
  day: string;
  month: string;
  year: string;
  yearHelp: string;
  months: string[];
  consent: string;
  adult: string;
  save: string;
  saving: string;
  saved: string;
  /** "Your birthday: {date}" */
  current: string;
  /** "You can change the date again from {date}." */
  changeFrom: string;
  remove: string;
  removed: string;
  privacy: string;
  errors: Record<string, string>;
};

type Props = {
  accessToken: string;
  labels: BirthdayLabels;
  initial: Birthday | null;
};

function errorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const key = error.details.message_key;
    if (typeof key === "string") return key.split(".").pop() ?? "generic";
  }
  return "generic";
}

export function BirthdayForm({ accessToken, labels, initial }: Props) {
  const api = createAccountApiClient(() => accessToken);
  const [current, setCurrent] = useState<Birthday | null>(initial?.consented ? initial : null);
  const [day, setDay] = useState(String(initial?.day ?? ""));
  const [month, setMonth] = useState(String(initial?.month ?? ""));
  const [year, setYear] = useState(initial?.year ? String(initial.year) : "");
  const [consent, setConsent] = useState(false);
  const [adult, setAdult] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (!consent) return setStatus({ tone: "error", text: labels.errors.consent ?? "" });
    if (!adult) return setStatus({ tone: "error", text: labels.errors.adult ?? "" });
    const dayNumber = Number.parseInt(day, 10);
    const monthNumber = Number.parseInt(month, 10);
    if (!dayNumber || !monthNumber) {
      return setStatus({ tone: "error", text: labels.errors.invalid ?? "" });
    }
    setBusy(true);
    setStatus(null);
    try {
      const saved = await api.putBirthday({
        day: dayNumber,
        month: monthNumber,
        year: year ? Number.parseInt(year, 10) : null,
        consent,
        adult_confirmed: adult,
      });
      setCurrent(saved);
      setConsent(false);
      setAdult(false);
      setStatus({ tone: "ok", text: labels.saved });
    } catch (error) {
      setStatus({
        tone: "error",
        text: labels.errors[errorKey(error)] ?? labels.errors.generic ?? "",
      });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.deleteBirthday();
      setCurrent(null);
      setDay("");
      setMonth("");
      setYear("");
      setStatus({ tone: "ok", text: labels.removed });
    } catch (error) {
      setStatus({
        tone: "error",
        text: labels.errors[errorKey(error)] ?? labels.errors.generic ?? "",
      });
    } finally {
      setBusy(false);
    }
  };

  const currentDate =
    current?.day && current.month
      ? `${current.day} ${labels.months[current.month - 1] ?? ""}`
      : null;

  return (
    <section
      aria-labelledby="birthday-heading"
      className="space-y-3 rounded-card border border-border bg-surface p-4"
    >
      <h3 id="birthday-heading" className="font-display text-h3 text-display-ink">
        {labels.title}
      </h3>
      <p className="text-sm text-text-2">{labels.intro}</p>

      {currentDate ? (
        <div className="space-y-1">
          <p className="text-sm font-medium text-display-ink">
            {labels.current.replace("{date}", currentDate)}
          </p>
          {current?.can_change_from ? (
            <p className="text-xs text-text-3">
              {labels.changeFrom.replace("{date}", current.can_change_from)}
            </p>
          ) : null}
        </div>
      ) : null}

      <form className="space-y-3" onSubmit={(event) => void save(event)}>
        <div className="grid grid-cols-3 gap-2">
          <FormField label={labels.day}>
            <Select value={day} onChange={(event) => setDay(event.target.value)}>
              <option value="">—</option>
              {Array.from({ length: 31 }, (_, index) => (
                <option key={index + 1} value={index + 1}>
                  {index + 1}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label={labels.month} className="col-span-2">
            <Select value={month} onChange={(event) => setMonth(event.target.value)}>
              <option value="">—</option>
              {labels.months.map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </Select>
          </FormField>
        </div>
        <FormField label={labels.year} helpText={labels.yearHelp}>
          <Input
            value={year}
            onChange={(event) => setYear(event.target.value.replace(/\D/g, "").slice(0, 4))}
            inputMode="numeric"
          />
        </FormField>
        <Checkbox
          label={labels.consent}
          checked={consent}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <Checkbox
          label={labels.adult}
          checked={adult}
          onChange={(event) => setAdult(event.target.checked)}
        />
        <p className="text-xs text-text-3">{labels.privacy}</p>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={busy} loadingLabel={labels.saving}>
            {labels.save}
          </Button>
          {current ? (
            <Button
              variant="ghost"
              loading={busy}
              loadingLabel={labels.saving}
              onClick={() => void remove()}
            >
              {labels.remove}
            </Button>
          ) : null}
        </div>
      </form>
      {status ? (
        <p
          role={status.tone === "error" ? "alert" : "status"}
          className={`text-sm ${status.tone === "error" ? "text-danger" : "text-success"}`}
        >
          {status.text}
        </p>
      ) : null}
    </section>
  );
}
