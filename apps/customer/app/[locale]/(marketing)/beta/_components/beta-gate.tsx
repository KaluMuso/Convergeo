"use client";

import { Button } from "@vergeo/ui/src/button";
import {
  FeedbackWidget,
  type FeedbackInput,
  type FeedbackSubmitResult,
  type FeedbackWidgetLabels,
} from "@vergeo/ui/src/feedback-widget";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

type RedeemOutcome = "redeemed" | "public" | "invalid" | "expired" | "exhausted" | "inactive";

type Status = "idle" | "submitting" | "success" | "error";

const OUTCOME_ERROR_KEY: Record<Exclude<RedeemOutcome, "redeemed" | "public">, string> = {
  invalid: "errors.invalid",
  expired: "errors.expired",
  exhausted: "errors.exhausted",
  inactive: "errors.inactive",
};

export function BetaGate({ locale }: { locale: string }) {
  const t = useTranslations("marketing.beta");
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setErrorText(null);

    const trimmed = code.trim();
    if (!trimmed) {
      setErrorText(t("errors.empty"));
      return;
    }
    setStatus("submitting");

    try {
      const res = await fetch(`${getApiBaseUrl()}/beta/redeem`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: trimmed }),
      });

      if (res.status === 429) {
        setStatus("error");
        setErrorText(t("errors.rateLimited"));
        return;
      }
      if (!res.ok) {
        setStatus("error");
        setErrorText(t("errors.generic"));
        return;
      }

      const body = (await res.json()) as { outcome: RedeemOutcome; granted: boolean };
      if (body.granted) {
        // Client-side hint that access was granted; server-side gating stays the
        // source of truth (the public_launch flag / invite redemption).
        try {
          document.cookie = `vg_beta_access=1; path=/; max-age=${60 * 60 * 24 * 90}; samesite=lax`;
        } catch {
          /* cookies may be unavailable; success screen still shows */
        }
        setStatus("success");
        return;
      }

      setStatus("error");
      const key =
        body.outcome in OUTCOME_ERROR_KEY
          ? OUTCOME_ERROR_KEY[body.outcome as keyof typeof OUTCOME_ERROR_KEY]
          : "errors.generic";
      setErrorText(t(key));
    } catch {
      setStatus("error");
      setErrorText(t("errors.generic"));
    }
  }

  function feedbackLabels(): FeedbackWidgetLabels {
    return {
      trigger: t("feedback.trigger"),
      heading: t("feedback.heading"),
      close: t("feedback.close"),
      categoryLabel: t("feedback.categoryLabel"),
      categoryBug: t("feedback.categoryBug"),
      categoryIdea: t("feedback.categoryIdea"),
      categoryConfusing: t("feedback.categoryConfusing"),
      categoryPraise: t("feedback.categoryPraise"),
      categoryOther: t("feedback.categoryOther"),
      messageLabel: t("feedback.messageLabel"),
      messagePlaceholder: t("feedback.messagePlaceholder"),
      screenshotLabel: t("feedback.screenshotLabel"),
      requiredMarker: t("feedback.requiredMarker"),
      submit: t("feedback.submit"),
      submitting: t("feedback.submitting"),
      success: t("feedback.success"),
      errorGeneric: t("feedback.errorGeneric"),
      errorRateLimited: t("feedback.errorRateLimited"),
      validation: { messageRequired: t("feedback.validation.messageRequired") },
    };
  }

  async function submitFeedback(input: FeedbackInput): Promise<FeedbackSubmitResult> {
    try {
      const res = await fetch(`${getApiBaseUrl()}/beta/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: input.category,
          message: input.message,
          screenshot: input.screenshot,
          path: typeof window !== "undefined" ? window.location.pathname : undefined,
        }),
      });
      return { ok: res.ok, rateLimited: res.status === 429 };
    } catch {
      return { ok: false };
    }
  }

  if (status === "success") {
    return (
      <section className="space-y-4 rounded-lg border border-success/30 bg-success/10 p-6">
        <h2 className="font-display text-h2 text-display-ink">{t("success.heading")}</h2>
        <p className="text-body text-text">{t("success.body")}</p>
        <LinkButton href={`/${locale}`} variant="primary" className="px-5" LinkComponent={Link}>
          {t("success.cta")}
        </LinkButton>
        <FeedbackWidget labels={feedbackLabels()} onSubmit={submitFeedback} />
      </section>
    );
  }

  return (
    <>
      <form className="flex flex-col gap-4" noValidate onSubmit={onSubmit}>
        <FormField
          label={t("form.codeLabel")}
          required
          requiredMarker={t("form.requiredMarker")}
          errorMessage={errorText ?? undefined}
        >
          <Input
            name="code"
            value={code}
            error={Boolean(errorText)}
            placeholder={t("form.codePlaceholder")}
            autoComplete="off"
            autoCapitalize="characters"
            onChange={(event) => setCode(event.target.value)}
          />
        </FormField>

        <Button
          type="submit"
          loading={status === "submitting"}
          loadingLabel={t("form.submitting")}
          className="self-start"
        >
          {t("form.submit")}
        </Button>
      </form>

      <FeedbackWidget labels={feedbackLabels()} onSubmit={submitFeedback} />
    </>
  );
}
