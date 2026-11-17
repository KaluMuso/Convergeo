export type PhoneOtpEnvBag = {
  NEXT_PUBLIC_PHONE_OTP_ENABLED?: string;
};

/**
 * Phone OTP (SMS) is fail-closed during the cash-on-delivery pilot: until an SMS
 * provider is live, sign-in and sign-up default to the email tab. Set
 * `NEXT_PUBLIC_PHONE_OTP_ENABLED=true` to make phone the default tab again.
 *
 * Direct `process.env.NEXT_PUBLIC_PHONE_OTP_ENABLED` access is required so Next.js
 * inlines the flag into client bundles.
 */
export function isPhoneOtpEnabled(env: PhoneOtpEnvBag = {}): boolean {
  const configured = env.NEXT_PUBLIC_PHONE_OTP_ENABLED ?? process.env.NEXT_PUBLIC_PHONE_OTP_ENABLED;
  return configured === "true";
}
