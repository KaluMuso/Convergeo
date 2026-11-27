"use client";

import {
  NextIntlClientProvider,
  useLocale,
  useMessages,
  type AbstractIntlMessages,
} from "next-intl";
import { useMemo } from "react";

import { mergeMessageTrees } from "../../../lib/route-messages";

type Tree = Parameters<typeof mergeMessageTrees>[0];

/**
 * Adds a route's message branches on top of the app-wide provider (which only carries
 * the shell chrome). next-intl's nested provider replaces rather than merges, so the
 * parent messages are read back and merged here.
 */
export function MessagesExtension({
  messages,
  children,
}: {
  messages: AbstractIntlMessages;
  children: React.ReactNode;
}) {
  const parent = useMessages();
  const locale = useLocale();
  const merged = useMemo(
    () => mergeMessageTrees(parent as Tree, messages as Tree) as AbstractIntlMessages,
    [parent, messages],
  );
  return (
    <NextIntlClientProvider locale={locale} messages={merged}>
      {children}
    </NextIntlClientProvider>
  );
}
