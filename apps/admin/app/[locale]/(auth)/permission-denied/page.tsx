import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function AdminPermissionDeniedPage({ params }: PageProps) {
  const { locale } = await params;

  if (!LOCALES.includes(locale as Locale)) {
    return null;
  }

  setRequestLocale(locale);
  const baseMessages = await getMessages();
  const adminMessages = await loadNamespace(locale as Locale, "admin");
  const commonMessages = await loadNamespace(locale as Locale, "common");
  const messages = {
    ...baseMessages,
    admin: adminMessages,
    common: commonMessages,
  } as AbstractIntlMessages;

  const tCommon = createTranslator({ locale, messages, namespace: "common" });
  const t = createTranslator({ locale, messages, namespace: "admin" });

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="flex items-center justify-center px-4 py-6">
        <p className="font-display text-lg text-display-ink">{tCommon("app.name")}</p>
      </header>
      <main className="mx-auto flex w-full max-w-[360px] flex-1 flex-col px-4 pb-8">
        <div className="flex w-full flex-col gap-3 text-center">
          <h1 className="font-display text-h2 text-display-ink">{t("accessDenied.title")}</h1>
          <p className="font-body text-sm text-text-2">{t("accessDenied.body")}</p>
          <p className="font-body text-sm text-text-3">{t("accessDenied.hint")}</p>
        </div>
      </main>
    </div>
  );
}
