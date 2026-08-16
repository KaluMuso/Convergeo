"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "../../../../listings/new/_lib/ui";

export type ScanResultKind =
  | "valid"
  | "queued"
  | "conflict"
  | "rejected"
  | "unknown_ticket"
  | "stale_window"
  | "not_synced"
  | "invalid_sig"
  | "invalid_format";

export type ScanTicketContext = {
  holderName: string | null;
  ticketTypeName: string | null;
  eventTitle: string | null;
  idCheckRequired: boolean;
};

export type ScanResultState =
  { kind: "idle" } | { kind: ScanResultKind; ticketId: string | null; context?: ScanTicketContext };

const SUCCESS_KINDS = new Set<ScanResultKind>(["valid", "queued"]);

const MESSAGE_KEY_BY_KIND: Record<ScanResultKind, string> = {
  valid: "valid",
  queued: "queued",
  conflict: "conflict",
  rejected: "rejected",
  unknown_ticket: "unknownTicket",
  stale_window: "staleWindow",
  not_synced: "notSynced",
  invalid_sig: "invalidSig",
  invalid_format: "invalidFormat",
};

type ScanResultFlashProps = {
  state: ScanResultState;
  onDismiss: () => void;
  onOverride?: (reason: string) => void;
  overrideBusy?: boolean;
};

export function ScanResultFlash({
  state,
  onDismiss,
  onOverride,
  overrideBusy = false,
}: ScanResultFlashProps) {
  const t = useTranslations("vendor");
  const [reason, setReason] = useState("");

  if (state.kind === "idle") {
    return null;
  }

  const isSuccess = SUCCESS_KINDS.has(state.kind);
  const messageKey = `scan.eventCheckIn.result.${MESSAGE_KEY_BY_KIND[state.kind]}`;
  const tone = isSuccess ? "success" : "danger";
  const context = state.context;

  return (
    <div
      data-testid={isSuccess ? "event-scan-flash-success" : "event-scan-flash-error"}
      role={isSuccess ? "status" : "alert"}
      style={{
        borderRadius: "var(--r)",
        border: `1px solid var(--${tone})`,
        background: `color-mix(in srgb, var(--${tone}) 10%, var(--surface))`,
        padding: "var(--sp-4)",
        textAlign: "center",
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-display)",
          fontSize: "var(--fs-h3)",
          color: `var(--${tone})`,
        }}
      >
        {t(`${messageKey}.title`)}
      </p>
      {context?.eventTitle ? (
        <p style={{ margin: "var(--sp-2) 0 0", fontWeight: 600 }}>{context.eventTitle}</p>
      ) : null}
      {context?.holderName ? (
        <p style={{ margin: "var(--sp-1) 0 0" }}>
          {t("scan.eventCheckIn.result.holder", { name: context.holderName })}
        </p>
      ) : null}
      {context?.ticketTypeName ? (
        <p style={{ margin: "var(--sp-1) 0 0", color: "var(--text-2)" }}>
          {t("scan.eventCheckIn.result.tier", { name: context.ticketTypeName })}
        </p>
      ) : null}
      {context?.idCheckRequired ? (
        <p
          style={{
            margin: "var(--sp-2) 0 0",
            fontWeight: 600,
            color: "var(--warning)",
          }}
        >
          {t("scan.eventCheckIn.result.idCheck")}
        </p>
      ) : null}
      <p style={{ margin: "var(--sp-2) 0 var(--sp-4)", color: "var(--text-2)" }}>
        {t(`${messageKey}.body`, { ticketId: state.ticketId ? state.ticketId.slice(0, 8) : "" })}
      </p>
      {state.kind === "rejected" && state.ticketId && onOverride ? (
        <form
          className="mb-4 flex flex-col gap-2 text-left"
          onSubmit={(event) => {
            event.preventDefault();
            if (reason.trim().length < 3) {
              return;
            }
            onOverride(reason.trim());
          }}
        >
          <label className="text-sm font-medium" htmlFor="override-reason">
            {t("scan.eventCheckIn.override.reasonLabel")}
          </label>
          <input
            id="override-reason"
            className="min-h-11 rounded-md border border-border bg-bg px-3"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t("scan.eventCheckIn.override.reasonPlaceholder")}
          />
          <Button
            type="submit"
            variant="secondary"
            loading={overrideBusy}
            loadingLabel={t("scan.eventCheckIn.override.submitting")}
            disabled={overrideBusy || reason.trim().length < 3}
          >
            {t("scan.eventCheckIn.override.cta")}
          </Button>
        </form>
      ) : null}
      <Button
        type="button"
        variant={isSuccess ? "primary" : "secondary"}
        loading={false}
        loadingLabel={t("scan.eventCheckIn.result.scanAnother")}
        onClick={onDismiss}
      >
        {t("scan.eventCheckIn.result.scanAnother")}
      </Button>
    </div>
  );
}
