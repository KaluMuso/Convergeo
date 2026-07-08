"use client";

import { createBrowserClient } from "@vergeo/auth/browser-client";
import { Button } from "@vergeo/ui/src/button";
import { useState } from "react";

type GoogleButtonProps = {
  label: string;
  loadingLabel: string;
  locale: string;
  nextPath: string;
  onError: (message: string) => void;
};

export function GoogleButton({
  label,
  loadingLabel,
  locale,
  nextPath,
  onError,
}: GoogleButtonProps) {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      const supabase = createBrowserClient();
      const redirectTo = `${window.location.origin}/${locale}/login?next=${encodeURIComponent(nextPath)}`;

      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo,
        },
      });

      if (error) {
        onError(error.message);
        setLoading(false);
      }
    } catch {
      onError("generic");
      setLoading(false);
    }
  };

  return (
    <Button
      type="button"
      variant="secondary"
      size="lg"
      className="w-full"
      loading={loading}
      loadingLabel={loadingLabel}
      onClick={() => {
        void handleClick();
      }}
    >
      {label}
    </Button>
  );
}
