"use client";

import { createBrowserClient } from "@vergeo/auth";
import { useRouter } from "next/navigation";
import { useState } from "react";

type SignOutButtonProps = {
  locale: string;
  label: string;
  className?: string;
};

/**
 * Actually signs the admin out. The header used to be a plain <Link> to /login,
 * which navigated away but left the Supabase session intact — so the next visit
 * to any admin route was still authenticated. This clears the session first,
 * then returns to the login screen.
 */
export function SignOutButton({ locale, label, className }: SignOutButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  const handleSignOut = async () => {
    setPending(true);
    try {
      await createBrowserClient().auth.signOut();
    } finally {
      router.replace(`/${locale}/login`);
      router.refresh();
    }
  };

  return (
    <button
      type="button"
      className={className}
      disabled={pending}
      onClick={() => void handleSignOut()}
    >
      {label}
    </button>
  );
}
