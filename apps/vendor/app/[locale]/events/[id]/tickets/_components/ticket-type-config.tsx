"use client";

import { useSession } from "@vergeo/auth/use-session";
import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, FormField, Input, Select, Spinner } from "../../../../listings/new/_lib/ui";
import {
  isValidFreePrice,
  isValidPaidPrice,
  ngweeToZmwInput,
  zmwDecimalToNgwee,
} from "../_lib/money";
import {
  createTicketsClient,
  type TicketKind,
  type TicketTypeSummary,
} from "../_lib/tickets-client";

type TicketTypeConfigProps = {
  locale: string;
  eventId: string;
};

type TypeDraft = {
  kind: TicketKind;
  name: string;
  priceZmw: string;
  qtyCap: string;
  perCustomerCap: string;
};

const EMPTY_DRAFT: TypeDraft = {
  kind: "fixed",
  name: "",
  priceZmw: "",
  qtyCap: "",
  perCustomerCap: "",
};

function draftFromType(type: TicketTypeSummary): TypeDraft {
  return {
    kind: type.kind,
    name: type.name,
    priceZmw: type.kind === "free_rsvp" ? "0.00" : ngweeToZmwInput(type.price_ngwee),
    qtyCap: type.qty_cap === null ? "" : String(type.qty_cap),
    perCustomerCap: type.per_customer_cap === null ? "" : String(type.per_customer_cap),
  };
}

function parseOptionalPositiveInt(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

export function TicketTypeConfig({ locale, eventId }: TicketTypeConfigProps) {
  const t = useTranslations("vendor");
  const { session, loading: sessionLoading } = useSession();
  const [types, setTypes] = useState<TicketTypeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState<TypeDraft>(EMPTY_DRAFT);

  const getToken = useCallback(() => session?.access_token ?? null, [session?.access_token]);
  const ticketsClient = useMemo(() => createTicketsClient(getToken), [getToken]);

  const loadTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await ticketsClient.listTicketTypes(eventId);
      setTypes(rows);
    } catch {
      setError(t("tickets.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [eventId, t, ticketsClient]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    if (!session) {
      setLoading(false);
      return;
    }
    void loadTypes();
  }, [loadTypes, session, sessionLoading]);

  const resetForm = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
    setShowForm(false);
  };

  const startCreate = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
    setShowForm(true);
    setNotice(null);
    setError(null);
  };

  const startEdit = (type: TicketTypeSummary) => {
    setDraft(draftFromType(type));
    setEditingId(type.id);
    setShowForm(true);
    setNotice(null);
    setError(null);
  };

  const handleKindChange = (kind: TicketKind) => {
    setDraft((current) => ({
      ...current,
      kind,
      priceZmw: kind === "free_rsvp" ? "0.00" : current.priceZmw,
    }));
  };

  const validateDraft = (): string | null => {
    if (!draft.name.trim()) {
      return t("tickets.errors.required");
    }
    if (draft.kind === "free_rsvp") {
      if (!isValidFreePrice(draft.priceZmw)) {
        return t("tickets.errors.freeMustBeZero");
      }
    } else if (!isValidPaidPrice(draft.priceZmw)) {
      return t("tickets.errors.priceInvalid");
    }
    return null;
  };

  const handleSave = async () => {
    const validationError = validateDraft();
    if (validationError) {
      setError(validationError);
      return;
    }

    const priceNgwee =
      draft.kind === "free_rsvp" ? 0 : zmwDecimalToNgwee(draft.priceZmw.replace(/,/g, ""));
    const payload = {
      kind: draft.kind,
      name: draft.name.trim(),
      price_ngwee: priceNgwee,
      qty_cap: parseOptionalPositiveInt(draft.qtyCap),
      per_customer_cap: parseOptionalPositiveInt(draft.perCustomerCap),
    };

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      if (editingId) {
        await ticketsClient.updateTicketType(editingId, payload);
      } else {
        await ticketsClient.createTicketType(eventId, payload);
      }
      setNotice(t("tickets.saved"));
      resetForm();
      await loadTypes();
    } catch {
      setError(t("tickets.errors.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (typeId: string) => {
    if (!window.confirm(t("tickets.actions.confirmDelete"))) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await ticketsClient.deleteTicketType(typeId);
      setNotice(t("tickets.deleted"));
      if (editingId === typeId) {
        resetForm();
      }
      await loadTypes();
    } catch {
      setError(t("tickets.errors.deleteFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (sessionLoading || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label={t("tickets.loading")} />
        <span className="sr-only">{t("tickets.loading")}</span>
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-muted-foreground">{t("tickets.errors.unauthorized")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-xl font-semibold">{t("tickets.heading")}</h1>
        <p className="text-sm text-muted-foreground">{t("tickets.subheading")}</p>
      </div>

      <Link
        href={`/${locale}/events/${eventId}/edit`}
        className="text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        {t("tickets.backToEvent")}
      </Link>

      {error ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary" role="status">
          {notice}
        </p>
      ) : null}

      {types.length === 0 && !showForm ? (
        <p className="text-sm text-muted-foreground">{t("tickets.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {types.map((type) => (
            <li key={type.id} className="rounded-lg border border-border bg-card p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{type.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {type.kind === "free_rsvp" ? formatK(0) : formatK(type.price_ngwee)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("tickets.fields.soldLabel", { count: type.tickets_sold })}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => startEdit(type)}
                    loadingLabel=""
                  >
                    {t("tickets.actions.edit")}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={saving || type.tickets_sold > 0}
                    onClick={() => void handleDelete(type.id)}
                    loadingLabel=""
                  >
                    {t("tickets.actions.delete")}
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {showForm ? (
        <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex flex-col gap-3">
            <FormField label={t("tickets.fields.kindLabel")}>
              <Select
                value={draft.kind}
                onChange={(event) => handleKindChange(event.target.value as TicketKind)}
              >
                <option value="fixed">{t("tickets.fields.kindFixed")}</option>
                <option value="tier">{t("tickets.fields.kindTier")}</option>
                <option value="free_rsvp">{t("tickets.fields.kindFreeRsvp")}</option>
              </Select>
            </FormField>

            <FormField label={t("tickets.fields.nameLabel")}>
              <Input
                value={draft.name}
                onChange={(event) => setDraft((c) => ({ ...c, name: event.target.value }))}
                placeholder={t("tickets.fields.namePlaceholder")}
              />
            </FormField>

            <FormField
              label={t("tickets.fields.priceLabel")}
              helpText={
                draft.kind === "free_rsvp"
                  ? t("tickets.fields.priceFreeHelp")
                  : t("tickets.fields.priceHelp")
              }
            >
              <Input
                inputMode="decimal"
                value={draft.kind === "free_rsvp" ? "0.00" : draft.priceZmw}
                onChange={(event) => setDraft((c) => ({ ...c, priceZmw: event.target.value }))}
                placeholder={t("tickets.fields.pricePlaceholder")}
                disabled={draft.kind === "free_rsvp"}
              />
            </FormField>

            <FormField
              label={t("tickets.fields.qtyCapLabel")}
              helpText={t("tickets.fields.qtyCapHelp")}
            >
              <Input
                inputMode="numeric"
                value={draft.qtyCap}
                onChange={(event) => setDraft((c) => ({ ...c, qtyCap: event.target.value }))}
                placeholder={t("tickets.fields.qtyCapPlaceholder")}
              />
            </FormField>

            <FormField
              label={t("tickets.fields.perCustomerCapLabel")}
              helpText={t("tickets.fields.perCustomerCapHelp")}
            >
              <Input
                inputMode="numeric"
                value={draft.perCustomerCap}
                onChange={(event) =>
                  setDraft((c) => ({ ...c, perCustomerCap: event.target.value }))
                }
                placeholder={t("tickets.fields.perCustomerCapPlaceholder")}
              />
            </FormField>

            <div className="flex gap-2 pt-1">
              <Button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving}
                loading={saving}
                loadingLabel={t("tickets.saving")}
              >
                {t("tickets.actions.save")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={resetForm}
                disabled={saving}
                loadingLabel=""
              >
                {t("tickets.actions.cancel")}
              </Button>
            </div>
          </div>
        </section>
      ) : (
        <Button type="button" onClick={startCreate} loadingLabel="">
          {t("tickets.addType")}
        </Button>
      )}
    </div>
  );
}
