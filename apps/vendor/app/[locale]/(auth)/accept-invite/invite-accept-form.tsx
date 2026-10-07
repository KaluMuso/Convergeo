"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";

type InviteSession = { userId: string; accessToken: string };
type Ready = "checking" | "ready" | "invalid";

export function InviteAcceptForm({ locale }: { locale: string }) {
  const t = useTranslations("auth");
  const [ready, setReady] = useState<Ready>("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inviteSession = useRef<InviteSession | null>(null);
  // A single verification promise also survives React's development effect replay.
  const verification = useRef<Promise<InviteSession | null> | null>(null);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    if (!verification.current) {
      const params = new URLSearchParams(window.location.hash.slice(1));
      const tokenHash = params.get("token_hash");
      const type = params.get("type");
      // Remove the one-time token before loading Auth or making a network request.
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname,
      );
      verification.current = (async () => {
        if (type !== "invite" || !tokenHash) return null;
        try {
          const supabase = await getBrowserClient();
          if (!mounted.current) return null;
          const { data, error: verifyError } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: "invite",
          });
          if (
            verifyError ||
            !data.session?.user.id ||
            !data.session.access_token
          )
            return null;
          return {
            userId: data.session.user.id,
            accessToken: data.session.access_token,
          };
        } catch {
          return null;
        }
      })();
    }
    void verification.current.then((session) => {
      if (!active) return;
      inviteSession.current = session;
      setReady(session ? "ready" : "invalid");
    });
    return () => {
      active = false;
      mounted.current = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || done || ready !== "ready") return;
    setError(null);
    if (password.length < 8) {
      setError(t("reset.invalidPassword"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("reset.mismatch"));
      return;
    }
    setSaving(true);
    try {
      const supabase = await getBrowserClient();
      const { data } = await supabase.auth.getSession();
      const expected = inviteSession.current;
      if (
        !expected ||
        data.session?.user.id !== expected.userId ||
        data.session.access_token !== expected.accessToken
      ) {
        setReady("invalid");
        return;
      }
      const { error: updateError } = await supabase.auth.updateUser({
        password,
      });
      if (updateError) {
        setError(t("errors.generic"));
        return;
      }
      inviteSession.current = null;
      setDone(true);
    } catch {
      setError(t("errors.generic"));
    } finally {
      setSaving(false);
    }
  };

  if (ready === "checking") {
    return <p role="status">{t("invite.checking")}</p>;
  }
  if (ready === "invalid") {
    return (
      <div className="flex flex-col gap-4 text-center">
        <h1 className="font-display text-h2 text-display-ink">
          {t("invite.title")}
        </h1>
        <p role="alert" className="font-body text-sm text-danger">
          {t("invite.linkInvalid")}
        </p>
        <Link
          href={`/${locale}/reset-password`}
          className="font-body text-sm text-primary underline"
        >
          {t("invite.recoveryLink")}
        </Link>
      </div>
    );
  }
  if (done) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <h1 className="font-display text-h2 text-display-ink">
          {t("invite.title")}
        </h1>
        <p role="status">{t("invite.success")}</p>
        <Link
          href={`/${locale}/login`}
          className="font-body text-sm text-primary underline"
        >
          {t("reset.goToLogin")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <header className="space-y-1.5 text-center">
        <h1 className="font-display text-h2 text-display-ink">
          {t("invite.title")}
        </h1>
        <p className="font-body text-sm text-text-2">{t("invite.subtitle")}</p>
      </header>
      <form
        className="flex w-full flex-col gap-4"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <FormField
          label={t("reset.newPasswordLabel")}
          required
          requiredMarker="*"
        >
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            error={Boolean(error)}
            onChange={(event) => setPassword(event.target.value)}
          />
        </FormField>
        <FormField
          label={t("reset.confirmPasswordLabel")}
          required
          requiredMarker="*"
        >
          <Input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            error={Boolean(error)}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </FormField>
        {error ? (
          <p role="alert" className="font-body text-sm text-danger">
            {error}
          </p>
        ) : null}
        <Button
          type="submit"
          size="lg"
          className="w-full"
          loading={saving}
          loadingLabel={t("invite.saving")}
        >
          {t("invite.submit")}
        </Button>
      </form>
    </div>
  );
}
