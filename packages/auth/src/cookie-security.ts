type EnvBag = Record<string, string | undefined>;

export type SecureCookieOptions = {
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: "lax" | "strict" | "none" | boolean;
  path?: string;
  maxAge?: number;
  domain?: string;
  expires?: Date;
};

/** Production auth/session cookies must be HttpOnly + Secure + SameSite=Lax. */
export function secureCookieDefaults(env: EnvBag = process.env): SecureCookieOptions {
  const isProduction = env.NODE_ENV === "production";
  return {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
  };
}

export function mergeSecureCookieOptions(
  options: SecureCookieOptions | undefined,
  env: EnvBag = process.env,
): SecureCookieOptions {
  const defaults = secureCookieDefaults(env);
  return {
    ...options,
    httpOnly: options?.httpOnly ?? defaults.httpOnly,
    secure: options?.secure ?? defaults.secure,
    sameSite: options?.sameSite ?? defaults.sameSite,
  };
}
