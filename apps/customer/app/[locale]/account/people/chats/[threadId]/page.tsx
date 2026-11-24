import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import dynamic from "next/dynamic";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { setRequestLocale } from "next-intl/server";

const ChatPanel = dynamic(() => import("../../_components/chat-panel").then((m) => m.ChatPanel), {
  ssr: false,
});

type PageProps = { params: Promise<{ locale: string; threadId: string }> };

export default async function PeopleChatPage({ params }: PageProps) {
  const { locale, threadId } = await params;
  if (!LOCALES.includes(locale as Locale)) return null;
  setRequestLocale(locale);
  const social = await loadNamespace(locale as Locale, "social");
  const t = createTranslator({
    locale,
    messages: { social } as AbstractIntlMessages,
    namespace: "social",
  });
  return (
    <>
      <h2 className="mb-4 font-display text-h2 text-display-ink">{t("chat.title")}</h2>
      <ChatPanel threadId={threadId} />
    </>
  );
}
