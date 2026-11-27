import { loadNamespace, type Locale } from "@vergeo/i18n";
import { setRequestLocale } from "next-intl/server";

import {
  pickMessages,
  ROUTE_SPEC,
  specNamespaces,
  type MessageSpec,
  type RouteKey,
} from "../../../lib/route-messages";

import { MessagesExtension } from "./messages-extension";

import type { AbstractIntlMessages } from "next-intl";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function RouteMessages({
  locale,
  route,
  children,
}: {
  locale: string;
  route: RouteKey;
  children: React.ReactNode;
}) {
  const spec: MessageSpec = ROUTE_SPEC[route];
  const namespaces = specNamespaces(spec);
  const loaded = await Promise.all(
    namespaces.map((namespace) => loadNamespace(locale as Locale, namespace)),
  );
  const messages: Record<string, unknown> = {};
  namespaces.forEach((namespace, index) => {
    messages[namespace] = pickMessages(
      loaded[index] ?? {},
      spec[namespace] as readonly string[] | true,
    );
  });
  return (
    <MessagesExtension messages={messages as AbstractIntlMessages}>{children}</MessagesExtension>
  );
}

/** Segment layout factory: `export default routeMessagesLayout("listings")`. */
export function routeMessagesLayout(route: RouteKey) {
  return async function RouteMessagesLayout({ children, params }: LayoutProps) {
    const { locale } = await params;
    setRequestLocale(locale);
    return (
      <RouteMessages locale={locale} route={route}>
        {children}
      </RouteMessages>
    );
  };
}
