"use client";

import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, FormField, Input, Spinner } from "../../../../listings/new/_lib/ui";

import type { AllocationInput, AllocationRow } from "../_lib/tickets-client";

type TicketsClient = {
  getAllocations(ticketTypeId: string): Promise<AllocationRow[]>;
  setAllocations(ticketTypeId: string, allocations: AllocationInput[]): Promise<AllocationRow[]>;
};

type AllocationEditorProps = {
  locale: string;
  ticketTypeId: string;
  ticketsClient: TicketsClient;
};

function parseAllocation(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null; // blank = no per-date cap
  }
  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return Number.NaN; // signal invalid
  }
  return parsed;
}

export function AllocationEditor({ locale, ticketTypeId, ticketsClient }: AllocationEditorProps) {
  const t = useTranslations("vendor");
  const [rows, setRows] = useState<AllocationRow[]>([]);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const dateFormat = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }),
    [locale],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await ticketsClient.getAllocations(ticketTypeId);
      setRows(data);
      setInputs(
        Object.fromEntries(
          data.map((row) => [
            row.instance_id,
            row.allocation === null ? "" : String(row.allocation),
          ]),
        ),
      );
    } catch {
      setError(t("tickets.allocation.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t, ticketTypeId, ticketsClient]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    const allocations: AllocationInput[] = [];
    for (const row of rows) {
      const parsed = parseAllocation(inputs[row.instance_id] ?? "");
      if (Number.isNaN(parsed)) {
        setError(t("tickets.allocation.errors.invalid"));
        return;
      }
      if (parsed !== null) {
        allocations.push({ instance_id: row.instance_id, allocation: parsed });
      }
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await ticketsClient.setAllocations(ticketTypeId, allocations);
      setRows(updated);
      setInputs(
        Object.fromEntries(
          updated.map((row) => [
            row.instance_id,
            row.allocation === null ? "" : String(row.allocation),
          ]),
        ),
      );
      setNotice(t("tickets.allocation.saved"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "allocation_below_sold") {
        setError(t("tickets.allocation.errors.belowSold"));
      } else {
        setError(t("tickets.allocation.errors.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2">
        <Spinner label={t("tickets.allocation.loading")} />
        <span className="sr-only">{t("tickets.allocation.loading")}</span>
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-3 rounded-md bg-bg-2/40 p-3">
      <p className="text-sm font-medium">{t("tickets.allocation.heading")}</p>
      <p className="text-xs text-muted">{t("tickets.allocation.help")}</p>

      {error ? (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary" role="status">
          {notice}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-xs text-muted">{t("tickets.allocation.noInstances")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.instance_id} className="flex items-end gap-3">
              <FormField
                label={row.starts_at ? dateFormat.format(new Date(row.starts_at)) : row.instance_id}
                helpText={t("tickets.allocation.soldLabel", { count: row.sold })}
              >
                <Input
                  inputMode="numeric"
                  value={inputs[row.instance_id] ?? ""}
                  onChange={(event) =>
                    setInputs((current) => ({
                      ...current,
                      [row.instance_id]: event.target.value,
                    }))
                  }
                  placeholder={t("tickets.allocation.placeholder")}
                />
              </FormField>
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 ? (
        <div>
          <Button
            type="button"
            size="sm"
            onClick={() => void handleSave()}
            disabled={saving}
            loading={saving}
            loadingLabel={t("tickets.allocation.saving")}
          >
            {t("tickets.allocation.save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
