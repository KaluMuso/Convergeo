/** Defer existing-password policy to Auth; apply the UI minimum to new passwords. */
export function isPasswordLengthAllowed(password: string, mode: "login" | "signup"): boolean {
  return mode === "login" || password.length >= 8;
}
