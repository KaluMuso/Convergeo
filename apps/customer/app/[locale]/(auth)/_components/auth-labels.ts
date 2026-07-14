import { createTranslator } from "next-intl";

import type { AuthLoginLabels } from "./login-shell";
import type { AbstractIntlMessages } from "next-intl";

export function createLoginLabels(
  locale: string,
  messages: AbstractIntlMessages,
  options?: { variant?: "customer" | "vendor" | "admin" },
): AuthLoginLabels {
  const t = createTranslator({ locale, messages, namespace: "auth" });
  const variant = options?.variant ?? "customer";

  const subtitles: Record<typeof variant, string> = {
    customer: t("login.subtitle"),
    vendor: t("chrome.vendorTagline"),
    admin: t("chrome.adminTagline"),
  };

  // Passed to client components, so this must be a serializable string (not a
  // function): the `{seconds}` placeholder is interpolated client-side. Use
  // t.raw so the literal ICU template survives (t() would drop the placeholder).
  const throttled = String(t.raw("errors.throttled"));

  return {
    title: t("login.title"),
    subtitle: subtitles[variant],
    phone: {
      countryCode: t("login.countryCode"),
      nationalNumber: t("login.nationalNumber"),
      phoneLabel: t("login.phoneLabel"),
      phoneHelp: t("login.phoneHelp"),
      phonePlaceholder: t("login.phonePlaceholder"),
      submit: t("login.submit"),
      loading: t("loading.submit"),
      required: t("errors.required"),
      invalidPhone: t("errors.invalidPhone"),
      sendFailed: t("errors.sendFailed"),
      throttled,
    },
    email: {
      emailLabel: t("email.emailLabel"),
      passwordLabel: t("email.passwordLabel"),
      submit: t("email.submitLogin"),
      loading: t("loading.submit"),
      required: t("errors.required"),
      invalidEmail: t("errors.invalidEmail"),
      invalidPassword: t("errors.invalidPassword"),
      generic: t("errors.generic"),
      throttled,
    },
    divider: t("login.divider"),
    emailToggle: t("login.emailToggle"),
    phoneToggle: t("login.phoneToggle"),
    google: t("login.google"),
    googleLoading: t("google.loading"),
    signupPrompt: variant === "customer" ? t("login.noAccount") : undefined,
    signupLink: variant === "customer" ? t("login.signupLink") : undefined,
    genericError: t("errors.generic"),
  };
}
