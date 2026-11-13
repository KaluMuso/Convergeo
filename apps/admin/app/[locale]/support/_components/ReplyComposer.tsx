"use client";

import { getBrowserAccessToken } from "@vergeo/auth";
import { ApiError } from "@vergeo/config";
import { decodeJwt } from "jose";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import {
  CANNED_TEMPLATE_KEYS,
  supportApiForToken,
  type SendRequest,
  type SendResponse,
} from "./api";

type ReplyComposerProps = {
  customerId: string;
  orderId: string | null;
  onSent: () => void;
};

type PendingOperation = { id: string; fingerprint: string };

async function fingerprintRequest(request: string): Promise<string> {
  const bytes = new TextEncoder().encode(request);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function storedOperation(key: string): PendingOperation | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) ?? "null");
    if (
      value &&
      typeof value === "object" &&
      "id" in value &&
      typeof value.id === "string" &&
      "fingerprint" in value &&
      typeof value.fingerprint === "string"
    ) {
      return { id: value.id, fingerprint: value.fingerprint };
    }
  } catch {
    // The in-memory operation still covers retries when storage is unavailable.
  }
  return null;
}

export function ReplyComposer({ customerId, orderId, onSent }: ReplyComposerProps) {
  const t = useTranslations("admin.support.reply");
  const tTemplates = useTranslations("admin.support.templates");
  const [templateKey, setTemplateKey] = useState<string>("");
  const [freeText, setFreeText] = useState("");
  const [mode, setMode] = useState<"canned" | "free_text">("canned");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const pendingOperation = useRef<PendingOperation | null>(null);
  const sending = useRef(false);

  const send = async () => {
    if (sending.current) return;
    sending.current = true;
    setSubmitting(true);
    setError(null);
    setConflict(false);
    setSuccess(null);
    try {
      const reply =
        mode === "canned"
          ? {
              customer_id: customerId,
              order_id: orderId,
              template_key: templateKey,
            }
          : {
              customer_id: customerId,
              order_id: orderId,
              free_text: freeText.trim(),
            };

      const request = JSON.stringify(reply);
      const token = await getBrowserAccessToken();
      const actorId = token ? decodeJwt(token).sub : null;
      if (!token || !actorId) throw new Error("Admin session is unavailable");
      const fingerprint = await fingerprintRequest(`${actorId}\0${request}`);
      const storageKey = `admin-support:pending:${fingerprint}`;
      if (pendingOperation.current?.fingerprint !== fingerprint) {
        const stored = storedOperation(storageKey);
        pendingOperation.current =
          stored?.fingerprint === fingerprint ? stored : { id: crypto.randomUUID(), fingerprint };
      }
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(pendingOperation.current));
      } catch {
        // Retain the operation in memory for this tab if storage is unavailable.
      }
      const messageId = pendingOperation.current.id;
      const body: SendRequest = { ...reply, message_id: messageId };
      const result = await supportApiForToken(token).request<SendResponse>("/admin/support/send", {
        method: "POST",
        body: JSON.stringify(body),
      });

      pendingOperation.current = null;
      if (storedOperation(storageKey)?.id === messageId) {
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          // A confirmed send is complete even if storage cannot be cleared.
        }
      }
      setSuccess(
        result.deduped
          ? t("successDeduped", { channel: result.channel })
          : t("success", { channel: result.channel }),
      );
      if (mode === "free_text") {
        setFreeText((current) => (current.trim() === reply.free_text ? "" : current));
      }
      onSent();
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "idempotency_conflict") {
        setConflict(true);
        setError(t("conflict"));
      } else {
        setError(t("failure"));
      }
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4 rounded-lg border border-border bg-surface p-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-text">{t("title")}</h2>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
            mode === "canned"
              ? "border-primary bg-primary-tint text-primary"
              : "border-border text-text"
          }`}
          onClick={() => setMode("canned")}
        >
          {t("modeCanned")}
        </button>
        <button
          type="button"
          className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
            mode === "free_text"
              ? "border-primary bg-primary-tint text-primary"
              : "border-border text-text"
          }`}
          onClick={() => setMode("free_text")}
        >
          {t("modeFreeText")}
        </button>
      </div>

      {mode === "canned" ? (
        <label className="block space-y-1 text-sm">
          <span className="text-muted">{t("templateLabel")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-border px-3"
            value={templateKey}
            onChange={(event) => setTemplateKey(event.target.value)}
          >
            <option value="">{t("templatePlaceholder")}</option>
            {CANNED_TEMPLATE_KEYS.map((key) => (
              <option key={key} value={key}>
                {tTemplates(`${key}.label`)}
              </option>
            ))}
          </select>
          {templateKey ? (
            <p className="text-xs text-muted">{tTemplates(`${templateKey}.body`)}</p>
          ) : null}
        </label>
      ) : (
        <label className="block space-y-1 text-sm">
          <span className="text-muted">{t("freeTextLabel")}</span>
          <textarea
            className="min-h-28 w-full rounded-md border border-border px-3 py-2"
            value={freeText}
            onChange={(event) => setFreeText(event.target.value)}
            placeholder={t("freeTextPlaceholder")}
            maxLength={2000}
          />
          <p className="text-xs text-muted">{t("freeTextAudit")}</p>
        </label>
      )}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={
          submitting ||
          conflict ||
          (mode === "canned" ? !templateKey : freeText.trim().length === 0)
        }
        onClick={() => void send()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>

      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {conflict ? (
        <button
          type="button"
          className="min-h-11 rounded-md border border-border px-3 text-sm text-text"
          onClick={() => {
            const pending = pendingOperation.current;
            if (pending) {
              const key = `admin-support:pending:${pending.fingerprint}`;
              if (storedOperation(key)?.id === pending.id) {
                try {
                  sessionStorage.removeItem(key);
                } catch {
                  // A new in-memory operation is still possible without storage.
                }
              }
            }
            pendingOperation.current = null;
            setConflict(false);
            setError(null);
          }}
        >
          {t("startNew")}
        </button>
      ) : null}
      {success ? <p className="text-sm text-success">{success}</p> : null}
    </section>
  );
}
