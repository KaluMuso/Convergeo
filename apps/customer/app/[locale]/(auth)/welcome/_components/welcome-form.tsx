"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { createAccountApiClient } from "../../../account/_components/account-api";
import { LocaleSwitcher, type LocaleSwitcherLabels } from "../../../_components/locale-switcher";
import {
  ONBOARDING_INTERESTS,
  resolvePostAuthPath,
  type OnboardingInterest,
} from "../../_components/auth-utils";

export type WelcomeFormLabels = {
  languageLabel: string;
  interestsLabel: string;
  interestsHelp: string;
  interests: Record<OnboardingInterest, string>;
  continue: string;
  continuing: string;
  skip: string;
  error: string;
};

type WelcomeFormProps = {
  locale: string;
  labels: WelcomeFormLabels;
  localeSwitcherLabels: LocaleSwitcherLabels;
  nextParam?: string | null;
};

export function WelcomeForm({ locale, labels, localeSwitcherLabels, nextParam }: WelcomeFormProps) {
  const router = useRouter();
  const [selected, setSelected] = useState<OnboardingInterest[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const destination = useMemo(
    () => resolvePostAuthPath(locale, nextParam, `/${locale}`),
    [locale, nextParam],
  );

  const getToken = useCallback(async () => {
    const supabase = await getBrowserClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  }, []);

  const complete = async (interests: OnboardingInterest[]) => {
    setLoading(true);
    setError(null);

    try {
      const api = createAccountApiClient(getToken);
      await api.completeOnboarding({ interests, locale });
      router.push(destination);
      router.refresh();
    } catch {
      setError(labels.error);
      setLoading(false);
    }
  };

  const toggleInterest = (interest: OnboardingInterest) => {
    setSelected((current) =>
      current.includes(interest)
        ? current.filter((item) => item !== interest)
        : [...current, interest],
    );
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <section className="space-y-2">
        <h2 className="font-medium text-text">{labels.languageLabel}</h2>
        <LocaleSwitcher locale={locale} labels={localeSwitcherLabels} variant="shop" />
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <h2 className="font-medium text-text">{labels.interestsLabel}</h2>
          <p className="text-sm text-text-2">{labels.interestsHelp}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {ONBOARDING_INTERESTS.map((interest) => {
            const active = selected.includes(interest);
            return (
              <button
                key={interest}
                type="button"
                aria-pressed={active}
                className={
                  active
                    ? "min-h-11 rounded-pill border border-primary bg-primary/10 px-4 text-sm font-medium text-primary"
                    : "min-h-11 rounded-pill border border-border bg-surface px-4 text-sm text-text hover:border-primary/30"
                }
                onClick={() => toggleInterest(interest)}
              >
                {labels.interests[interest]}
              </button>
            );
          })}
        </div>
      </section>

      {error ? (
        <p role="alert" className="text-center text-sm text-danger">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        <Button
          type="button"
          size="lg"
          className="w-full"
          loading={loading}
          loadingLabel={labels.continuing}
          onClick={() => {
            void complete(selected);
          }}
        >
          {labels.continue}
        </Button>
        <button
          type="button"
          className="min-h-11 text-sm text-text-2 underline-offset-2 hover:underline"
          disabled={loading}
          onClick={() => {
            void complete([]);
          }}
        >
          {labels.skip}
        </button>
      </div>
    </div>
  );
}
