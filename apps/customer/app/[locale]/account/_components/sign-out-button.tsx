"use client";

import { Button } from "@vergeo/ui/src/button";
import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  locale: string;
  label: string;
  loadingLabel: string;
};

export function SignOutButton({ locale, label, loadingLabel }: Props) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  return (
    <Button
      type="button"
      variant="ghost"
      size="md"
      className="shrink-0"
      loading={loading}
      loadingLabel={loadingLabel}
      data-testid="account-sign-out"
      onClick={() => {
        setLoading(true);
        void (async () => {
          try {
            const { createBrowserClient } = await import("@vergeo/auth/browser-client");
            const supabase = createBrowserClient();
            await supabase.auth.signOut();
            router.replace(`/${locale}/login`);
            router.refresh();
          } catch {
            setLoading(false);
          }
        })();
      }}
    >
      {label}
    </Button>
  );
}
