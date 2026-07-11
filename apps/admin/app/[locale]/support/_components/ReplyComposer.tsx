"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { CANNED_TEMPLATE_KEYS, supportApi } from "./api";

type ReplyComposerProps = {
  customerId: string;
  orderId: string | null;
  onSent: () => void;
};

export function ReplyComposer({ customerId, orderId, onSent }: ReplyComposerProps) {
  const t = useTranslations("admin.support.reply");
  const tTemplates = useTranslations("admin.support.templates");
  const [templateKey, setTemplateKey] = useState<string>("");
  const [freeText, setFreeText] = useState("");
  const [mode, setMode] = useState<"canned" | "free_text">("canned");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const send = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const body =
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

      const result = await supportApi.request<{
        channel: string;
        deduped: boolean;
      }>("/admin/support/send", {
        method: "POST",
        body: JSON.stringify(body),
      });

      setSuccess(
        result.deduped
          ? t("successDeduped", { channel: result.channel })
          : t("success", { channel: result.channel }),
      );
      if (mode === "free_text") {
        setFreeText("");
      }
      onSent();
    } catch {
      setError(t("failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4 rounded-lg border border-[#E8DFD0] bg-white p-4">
      <header className="space-y-1">
        <h2 className="font-serif text-lg text-[#2A2118]">{t("title")}</h2>
        <p className="text-sm text-[#6B5E4C]">{t("subtitle")}</p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
            mode === "canned"
              ? "border-[#2D4A7A] bg-[#EEF3FA] text-[#2D4A7A]"
              : "border-[#E8DFD0] text-[#2A2118]"
          }`}
          onClick={() => setMode("canned")}
        >
          {t("modeCanned")}
        </button>
        <button
          type="button"
          className={`inline-flex min-h-11 items-center rounded-md border px-3 text-sm ${
            mode === "free_text"
              ? "border-[#2D4A7A] bg-[#EEF3FA] text-[#2D4A7A]"
              : "border-[#E8DFD0] text-[#2A2118]"
          }`}
          onClick={() => setMode("free_text")}
        >
          {t("modeFreeText")}
        </button>
      </div>

      {mode === "canned" ? (
        <label className="block space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("templateLabel")}</span>
          <select
            className="min-h-11 w-full rounded-md border border-[#E8DFD0] px-3"
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
            <p className="text-xs text-[#6B5E4C]">{tTemplates(`${templateKey}.body`)}</p>
          ) : null}
        </label>
      ) : (
        <label className="block space-y-1 text-sm">
          <span className="text-[#6B5E4C]">{t("freeTextLabel")}</span>
          <textarea
            className="min-h-28 w-full rounded-md border border-[#E8DFD0] px-3 py-2"
            value={freeText}
            onChange={(event) => setFreeText(event.target.value)}
            placeholder={t("freeTextPlaceholder")}
            maxLength={2000}
          />
          <p className="text-xs text-[#6B5E4C]">{t("freeTextAudit")}</p>
        </label>
      )}

      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-md bg-[#2D4A7A] px-4 text-sm font-medium text-white disabled:opacity-60"
        disabled={submitting || (mode === "canned" ? !templateKey : freeText.trim().length === 0)}
        onClick={() => void send()}
      >
        {submitting ? t("submitting") : t("submit")}
      </button>

      {error ? <p className="text-sm text-[#9B2C2C]">{error}</p> : null}
      {success ? <p className="text-sm text-[#2F6B3A]">{success}</p> : null}
    </section>
  );
}
