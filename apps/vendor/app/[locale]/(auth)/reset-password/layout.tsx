import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";

export default async function VendorResetLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!LOCALES.includes(locale as Locale)) notFound();
  setRequestLocale(locale);
  const [baseMessages, auth] = await Promise.all([
    getMessages(),
    loadNamespace(locale as Locale, "auth"),
  ]);

  return (
    <NextIntlClientProvider messages={{ ...baseMessages, auth }}>
      <main className="mx-auto flex min-h-dvh w-full max-w-[400px] flex-col justify-center px-4 py-8">
        {children}
      </main>
    </NextIntlClientProvider>
  );
}
