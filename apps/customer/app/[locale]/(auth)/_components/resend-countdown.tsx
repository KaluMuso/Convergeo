"use client";

import { Button } from "@vergeo/ui/src/button";
import { useEffect, useState } from "react";

type ResendCountdownProps = {
  cooldownSeconds: number;
  onResend: () => void | Promise<void>;
  resendLabel: string;
  resendInLabel: string;
  loadingLabel: string;
};

export function ResendCountdown({
  cooldownSeconds,
  onResend,
  resendLabel,
  resendInLabel,
  loadingLabel,
}: ResendCountdownProps) {
  const [secondsLeft, setSecondsLeft] = useState(cooldownSeconds);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (secondsLeft <= 0) {
      return;
    }

    const timer = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(0, current - 1));
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [secondsLeft]);

  const handleResend = async () => {
    if (secondsLeft > 0 || loading) {
      return;
    }

    setLoading(true);
    try {
      await onResend();
      setSecondsLeft(cooldownSeconds);
    } finally {
      setLoading(false);
    }
  };

  const disabled = secondsLeft > 0 || loading;

  return (
    <Button
      type="button"
      variant="ghost"
      size="md"
      className="w-full"
      disabled={disabled}
      loading={loading}
      loadingLabel={loadingLabel}
      onClick={() => {
        void handleResend();
      }}
    >
      {secondsLeft > 0 ? resendInLabel.replace("{seconds}", String(secondsLeft)) : resendLabel}
    </Button>
  );
}
