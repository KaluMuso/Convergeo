"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { LinkButton } from "@vergeo/ui/src/link-button";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

export default function AccountError({ reset }: { reset: () => void }) {
  const locale = useLocale();
  const t = useTranslations("account.errorPage");
  return (
    <div data-testid="account-error" className="py-6">
      <EmptyState
        title={t("title")}
        body={t("body")}
        action={
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              className="min-h-11 rounded-lg border px-5 text-sm font-semibold"
              onClick={reset}
            >
              {t("retry")}
            </button>
            <LinkButton
              href={`/${locale}/account`}
              variant="secondary"
              LinkComponent={Link}
              className="rounded-lg text-sm"
            >
              {t("back")}
            </LinkButton>
          </div>
        }
      />
    </div>
  );
}
