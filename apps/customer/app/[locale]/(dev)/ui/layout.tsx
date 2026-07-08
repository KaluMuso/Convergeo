import "@vergeo/ui/styles/base.css";

import { notFound } from "next/navigation";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "UI Kit Preview",
  robots: {
    index: false,
    follow: false,
  },
};

type LayoutProps = {
  children: React.ReactNode;
};

export default function UiPreviewLayout({ children }: LayoutProps) {
  if (
    process.env.NODE_ENV === "production" &&
    process.env.NEXT_PUBLIC_ENABLE_UI_PREVIEW !== "true"
  ) {
    notFound();
  }

  return (
    <div
      className="min-h-dvh bg-bg text-text"
      style={{ paddingBottom: "calc(4rem + env(safe-area-inset-bottom, 0px))" }}
    >
      {children}
    </div>
  );
}
