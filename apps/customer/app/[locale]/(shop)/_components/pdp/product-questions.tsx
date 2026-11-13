"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";

import {
  askProductQuestion,
  fetchProductQuestions,
  type ProductQuestion,
} from "../../../../../lib/engagement-api";

type ProductQuestionsProps = {
  productSlug: string;
  locale: string;
};

/** Public Q&A (GET/POST /products/{slug}/questions). Questions are moderated before showing. */
export function ProductQuestions({
  productSlug,
  locale,
}: ProductQuestionsProps) {
  const t = useTranslations("catalog.qa");
  const inputId = useId();
  const [questions, setQuestions] = useState<
    ProductQuestion[] | null | undefined
  >(undefined);
  const [draft, setDraft] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "sent" | "short">(
    "idle",
  );

  useEffect(() => {
    let active = true;
    void fetchProductQuestions(productSlug).then((rows) => {
      if (active) setQuestions(rows);
    });
    return () => {
      active = false;
    };
  }, [productSlug]);

  const submit = async () => {
    if (draft.trim().length < 5) {
      setState("short");
      return;
    }
    setState("busy");
    const result = await askProductQuestion(productSlug, draft.trim());
    if (result === "signed_out") {
      setState("idle");
      window.location.assign(
        `/${locale}/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
      return;
    }
    if (result === "error") {
      setState("idle");
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    setDraft("");
    setState("sent");
  };

  return (
    <section
      aria-labelledby={`${inputId}-title`}
      className="flex flex-col gap-3"
      data-testid="pdp-qa"
    >
      <h2
        id={`${inputId}-title`}
        className="m-0 font-display text-h3 font-bold text-text"
      >
        {t("title")}
      </h2>
      {questions === null ? (
        <p className="m-0 text-sm text-text-3">{t("loadFailed")}</p>
      ) : questions && questions.length > 0 ? (
        <ul className="m-0 flex list-none flex-col divide-y divide-border p-0">
          {questions.map((question) => (
            <li key={question.id} className="py-3">
              <p className="m-0 font-semibold text-text">{question.body}</p>
              {question.answers.map((answer) => (
                <p key={answer.id} className="m-0 mt-1.5 text-sm text-text-2">
                  <span className="mr-1.5 font-semibold text-primary">
                    {answer.author_role === "vendor"
                      ? (answer.vendor_name ?? t("sellerAnswer"))
                      : t("buyerAnswer")}
                  </span>
                  {answer.body}
                </p>
              ))}
            </li>
          ))}
        </ul>
      ) : questions ? (
        <p className="m-0 text-sm text-text-2">{t("empty")}</p>
      ) : null}
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          {t("askLabel")}
        </label>
        <input
          id={inputId}
          value={draft}
          maxLength={500}
          onChange={(event) => {
            setDraft(event.target.value);
            if (state !== "busy") setState("idle");
          }}
          placeholder={t("askPlaceholder")}
          className="min-h-11 min-w-0 flex-1 rounded border border-border bg-surface px-3 text-body text-text placeholder:text-text-3 focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          disabled={state === "busy"}
          className="inline-flex min-h-11 shrink-0 items-center justify-center rounded border border-primary px-4 text-sm font-semibold text-primary hover:bg-primary-tint disabled:opacity-60"
        >
          {state === "busy" ? t("submitting") : t("submit")}
        </button>
      </form>
      {state === "sent" ? (
        <p role="status" className="m-0 text-sm text-success">
          {t("sent")}
        </p>
      ) : state === "short" ? (
        <p role="alert" className="m-0 text-sm text-danger">
          {t("tooShort")}
        </p>
      ) : null}
    </section>
  );
}
