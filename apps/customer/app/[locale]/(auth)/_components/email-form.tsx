"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { parseAuthError, resolvePostAuthPath } from "./auth-utils";

type EmailFormLabels = {
  emailLabel: string;
  passwordLabel: string;
  submit: string;
  loading: string;
  required: string;
  invalidEmail: string;
  invalidPassword: string;
  generic: string;
  throttled: string;
  invalidCredentials: string;
  emailNotConfirmed: string;
  alreadyRegistered: string;
};

function messageForAuthError(
  parsed: ReturnType<typeof parseAuthError>,
  labels: EmailFormLabels,
  mode: "login" | "signup",
): string {
  if (parsed.code === "throttled" && parsed.retryAfterSeconds) {
    return labels.throttled.replace("{seconds}", String(parsed.retryAfterSeconds));
  }
  if (parsed.code === "email_not_confirmed") {
    return labels.emailNotConfirmed;
  }
  if (mode === "signup" && parsed.code === "already_registered") {
    return labels.alreadyRegistered;
  }
  if (mode === "login" && (parsed.code === "invalid_credentials" || parsed.code === "wrong_code")) {
    return labels.invalidCredentials;
  }
  return labels.generic;
}

type EmailFormProps = {
  locale: string;
  labels: EmailFormLabels;
  mode: "login" | "signup";
  defaultNextPath: string;
  nextParam?: string | null;
};

export function EmailForm({ locale, labels, mode, defaultNextPath, nextParam }: EmailFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isValidEmail = (value: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    if (!email.trim() || !password.trim()) {
      setErrorMessage(labels.required);
      return;
    }

    if (!isValidEmail(email)) {
      setErrorMessage(labels.invalidEmail);
      return;
    }

    if (password.length < 8) {
      setErrorMessage(labels.invalidPassword);
      return;
    }

    setLoading(true);

    try {
      const supabase = await getBrowserClient();

      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) {
          setErrorMessage(messageForAuthError(parseAuthError(error), labels, "signup"));
          return;
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          setErrorMessage(messageForAuthError(parseAuthError(error), labels, "login"));
          return;
        }
      }

      const destination = resolvePostAuthPath(locale, nextParam, defaultNextPath);
      router.push(destination);
      router.refresh();
    } catch {
      setErrorMessage(labels.generic);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="flex w-full flex-col gap-4" onSubmit={(event) => void handleSubmit(event)}>
      <FormField label={labels.emailLabel} required requiredMarker="*">
        <Input
          size="lg"
          type="email"
          autoComplete="email"
          value={email}
          error={Boolean(errorMessage)}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      <FormField label={labels.passwordLabel} required requiredMarker="*">
        <Input
          size="lg"
          type="password"
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          value={password}
          error={Boolean(errorMessage)}
          onChange={(event) => setPassword(event.target.value)}
        />
      </FormField>

      {errorMessage ? (
        <p role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}

      <Button
        type="submit"
        size="lg"
        className="w-full"
        loading={loading}
        loadingLabel={labels.loading}
      >
        {labels.submit}
      </Button>
    </form>
  );
}
