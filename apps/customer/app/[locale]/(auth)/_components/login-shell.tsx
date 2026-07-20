"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { resolvePostAuthPath } from "./auth-utils";
import { EmailForm } from "./email-form";
import { GoogleButton } from "./google-button";
import { PhoneForm } from "./phone-form";

export type AuthAppVariant = "customer" | "vendor" | "admin";

export type AuthLoginLabels = {
  title: string;
  subtitle: string;
  phone: {
    countryCode: string;
    nationalNumber: string;
    phoneLabel: string;
    phoneHelp: string;
    phonePlaceholder: string;
    submit: string;
    loading: string;
    required: string;
    invalidPhone: string;
    sendFailed: string;
    throttled: string;
  };
  email: {
    emailLabel: string;
    passwordLabel: string;
    submit: string;
    loading: string;
    required: string;
    invalidEmail: string;
    invalidPassword: string;
    generic: string;
    throttled: string;
  };
  divider: string;
  emailToggle: string;
  phoneToggle: string;
  google: string;
  googleLoading: string;
  signupPrompt?: string;
  signupLink?: string;
  genericError: string;
};

type AuthLoginShellProps = {
  locale: string;
  variant: AuthAppVariant;
  labels: AuthLoginLabels;
  otpPath?: string;
  signupPath?: string;
  defaultNextPath: string;
  nextParam?: string | null;
  showSignupLink?: boolean;
  phoneEnabled?: boolean;
};

export function AuthLoginShell({
  locale,
  variant,
  labels,
  otpPath = "/otp",
  signupPath = "/signup",
  defaultNextPath,
  nextParam,
  showSignupLink = variant === "customer",
  phoneEnabled = true,
}: AuthLoginShellProps) {
  const router = useRouter();
  const [method, setMethod] = useState<"phone" | "email">(phoneEnabled ? "phone" : "email");
  const [oauthError, setOauthError] = useState<string | null>(null);

  const postAuthPath = resolvePostAuthPath(locale, nextParam, defaultNextPath);

  useEffect(() => {
    const completeOAuth = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      if (!code) {
        return;
      }

      const supabase = await getBrowserClient();
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (error) {
        setOauthError(labels.genericError);
        return;
      }

      router.push(postAuthPath);
      router.refresh();
    };

    void completeOAuth();
  }, [labels.genericError, postAuthPath, router]);

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{labels.title}</h1>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
      </header>

      {phoneEnabled && method === "phone" ? (
        <PhoneForm locale={locale} labels={labels.phone} otpPath={otpPath} mode="login" />
      ) : (
        <EmailForm
          locale={locale}
          labels={labels.email}
          mode="login"
          defaultNextPath={defaultNextPath}
          nextParam={nextParam}
        />
      )}

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
        <span className="font-body text-xs uppercase tracking-wide text-text-3">
          {labels.divider}
        </span>
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
      </div>

      {phoneEnabled ? (
        <button
          type="button"
          className="min-h-11 font-body text-sm text-primary underline-offset-2 hover:underline"
          onClick={() => {
            setMethod((current) => (current === "phone" ? "email" : "phone"));
            setOauthError(null);
          }}
        >
          {method === "phone" ? labels.emailToggle : labels.phoneToggle}
        </button>
      ) : null}

      <GoogleButton
        label={labels.google}
        loadingLabel={labels.googleLoading}
        locale={locale}
        nextPath={postAuthPath}
        onError={() => setOauthError(labels.genericError)}
      />

      {oauthError ? (
        <p role="alert" className="text-center font-body text-sm text-danger">
          {oauthError}
        </p>
      ) : null}

      {showSignupLink && labels.signupPrompt && labels.signupLink ? (
        <p className="text-center font-body text-sm text-text-2">
          {labels.signupPrompt}{" "}
          <Link
            href={`/${locale}${signupPath}${nextParam ? `?next=${encodeURIComponent(nextParam)}` : ""}`}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            {labels.signupLink}
          </Link>
        </p>
      ) : null}
    </div>
  );
}

export type AuthSignupLabels = {
  title: string;
  subtitle: string;
  phone: AuthLoginLabels["phone"];
  email: AuthLoginLabels["email"] & { submit: string };
  divider: string;
  emailToggle: string;
  phoneToggle: string;
  google: string;
  googleLoading: string;
  loginPrompt: string;
  loginLink: string;
  genericError: string;
};

type AuthSignupShellProps = {
  locale: string;
  labels: AuthSignupLabels;
  otpPath?: string;
  loginPath?: string;
  defaultNextPath: string;
  nextParam?: string | null;
};

export function AuthSignupShell({
  locale,
  labels,
  otpPath = "/otp",
  loginPath = "/login",
  defaultNextPath,
  nextParam,
}: AuthSignupShellProps) {
  const router = useRouter();
  const [method, setMethod] = useState<"phone" | "email">("phone");
  const [oauthError, setOauthError] = useState<string | null>(null);

  const postAuthPath = resolvePostAuthPath(locale, nextParam, defaultNextPath);

  useEffect(() => {
    const completeOAuth = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      if (!code) {
        return;
      }

      const supabase = await getBrowserClient();
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (error) {
        setOauthError(labels.genericError);
        return;
      }

      router.push(postAuthPath);
      router.refresh();
    };

    void completeOAuth();
  }, [labels.genericError, postAuthPath, router]);

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">{labels.title}</h1>
        <p className="font-body text-sm text-text-2">{labels.subtitle}</p>
      </header>

      {method === "phone" ? (
        <PhoneForm locale={locale} labels={labels.phone} otpPath={otpPath} mode="signup" />
      ) : (
        <EmailForm
          locale={locale}
          labels={labels.email}
          mode="signup"
          defaultNextPath={defaultNextPath}
          nextParam={nextParam}
        />
      )}

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
        <span className="font-body text-xs uppercase tracking-wide text-text-3">
          {labels.divider}
        </span>
        <span className="h-px flex-1 bg-border" aria-hidden="true" />
      </div>

      <button
        type="button"
        className="min-h-11 font-body text-sm text-primary underline-offset-2 hover:underline"
        onClick={() => setMethod((current) => (current === "phone" ? "email" : "phone"))}
      >
        {method === "phone" ? labels.emailToggle : labels.phoneToggle}
      </button>

      <GoogleButton
        label={labels.google}
        loadingLabel={labels.googleLoading}
        locale={locale}
        nextPath={postAuthPath}
        onError={() => setOauthError(labels.genericError)}
      />

      {oauthError ? (
        <p role="alert" className="text-center font-body text-sm text-danger">
          {oauthError}
        </p>
      ) : null}

      <p className="text-center font-body text-sm text-text-2">
        {labels.loginPrompt}{" "}
        <Link
          href={`/${locale}${loginPath}${nextParam ? `?next=${encodeURIComponent(nextParam)}` : ""}`}
          className="font-medium text-primary underline-offset-2 hover:underline"
        >
          {labels.loginLink}
        </Link>
      </p>
    </div>
  );
}
