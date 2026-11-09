"use client";

import { emitToastKey, notify } from "@vergeo/ui/src/toast";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  isFollowingVendor,
  setVendorFollow,
} from "../../../../../lib/engagement-api";

type FollowVendorButtonProps = {
  vendorId: string;
  locale: string;
  labels: {
    follow: string;
    following: string;
    followedToast?: string;
    viewFeed?: string;
  };
};

/**
 * Follow / unfollow a store (PUT|DELETE /vendors/{id}/follow). Signed-out
 * shoppers are sent to login and returned here.
 */
export function FollowVendorButton({
  vendorId,
  locale,
  labels,
}: FollowVendorButtonProps) {
  const router = useRouter();
  const [following, setFollowing] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void isFollowingVendor(vendorId).then((value) => {
      if (!cancelled) {
        setFollowing(value);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [vendorId]);

  const onClick = async () => {
    if (following === null) {
      const next =
        typeof window !== "undefined" ? window.location.pathname : `/${locale}`;
      router.push(`/${locale}/login?next=${encodeURIComponent(next)}`);
      return;
    }
    setBusy(true);
    const target = !following;
    const ok = await setVendorFollow(vendorId, target);
    setBusy(false);
    if (!ok) {
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    setFollowing(target);
    if (target && labels.followedToast) {
      notify.success(labels.followedToast, {
        action: labels.viewFeed
          ? { label: labels.viewFeed, href: `/${locale}/account/following` }
          : undefined,
      });
    }
  };

  const isFollowing = following === true;

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      disabled={busy}
      aria-pressed={isFollowing}
      data-testid="vendor-follow"
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:shadow-focusRing disabled:opacity-60 ${
        isFollowing
          ? "border border-primary bg-primary-tint text-primary-deep"
          : "border border-border bg-surface text-text hover:border-primary hover:text-primary"
      }`}
    >
      <svg
        aria-hidden
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {isFollowing ? (
          <path d="m5 12.5 4.5 4.5L19 7.5" />
        ) : (
          <path d="M12 5v14M5 12h14" />
        )}
      </svg>
      {isFollowing ? labels.following : labels.follow}
    </button>
  );
}
