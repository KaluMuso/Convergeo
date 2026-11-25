import type { Metadata } from "next";

type LayoutProps = { children: React.ReactNode; params: Promise<{ locale: string }> };

export async function generateMetadata(_props: LayoutProps): Promise<Metadata> {
  return { title: "Notifications" };
}

export default function NotificationsLayout({ children }: LayoutProps) {
  return children;
}