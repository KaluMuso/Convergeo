import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";

export type SendSmsHookPayload = {
  user: { phone: string };
  sms: { otp: string };
};

export function normalizeHookSecret(raw: string | undefined): string {
  if (!raw) {
    throw new Error("SEND_SMS_HOOK_SECRET is not configured");
  }
  return raw.replace(/^v\d+,whsec_/, "");
}

export function verifySendSmsHook(
  payload: string,
  headers: Record<string, string>,
  rawSecret: string,
): SendSmsHookPayload {
  const secret = normalizeHookSecret(rawSecret);
  const wh = new Webhook(secret);
  return wh.verify(payload, headers) as SendSmsHookPayload;
}

export function buildOtpMessage(otp: string): string {
  return `Your Vergeo5 code is ${otp}`;
}
