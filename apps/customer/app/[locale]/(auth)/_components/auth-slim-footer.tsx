import Link from "next/link";

import type { ReactNode } from "react";

type AuthSlimFooterProps = {
  locale: string;
  labels: {
    help: string;
    privacy: string;
    terms: string;
  };
  localeSwitcher: ReactNode;
};

export function AuthSlimFooter({ locale, labels, localeSwitcher }: AuthSlimFooterProps) {
  return (
    <footer className="border-t border-border bg-bg px-4 py-5" data-testid="auth-slim-footer">
      <nav
        aria-label={labels.help}
        className="mx-auto flex w-full max-w-[400px] flex-col items-center gap-3 text-sm text-text-2"
      >
        <ul className="m-0 flex list-none flex-wrap items-center justify-center gap-x-4 gap-y-2 p-0">
          <li>
            <Link
              href={`/${locale}/help`}
              className="inline-flex min-h-11 items-center rounded-sm px-1 font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.help}
            </Link>
          </li>
          <li>
            <Link
              href={`/${locale}/legal/privacy`}
              className="inline-flex min-h-11 items-center rounded-sm px-1 font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.privacy}
            </Link>
          </li>
          <li>
            <Link
              href={`/${locale}/legal/terms`}
              className="inline-flex min-h-11 items-center rounded-sm px-1 font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {labels.terms}
            </Link>
          </li>
        </ul>
        <div className="flex items-center justify-center">{localeSwitcher}</div>
      </nav>
    </footer>
  );
}
