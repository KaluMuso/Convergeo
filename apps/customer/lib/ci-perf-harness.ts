import { isCiPerfSupabaseOrigin } from "@vergeo/config/ci-perf-server";

import {
  ciPerfPublicEnabled,
  ciPerfPublicEnv,
  type CiPerfPublicEnv,
} from "../../../packages/ui/src/media/ci-perf-fixture";

export type CiPerfServerEnv = CiPerfPublicEnv & {
  CI?: string;
  GITHUB_ACTIONS?: string;
  CI_PERF_HARNESS?: string;
  CI_PERF_UPSTREAM_ORIGIN?: string;
  ENV?: string;
  NODE_ENV?: string;
  SUPABASE_URL?: string;
  VERCEL?: string;
  VERCEL_ENV?: string;
};

export function ciPerfServerEnabled(env: CiPerfServerEnv = process.env): boolean {
  return (
    ciPerfPublicEnabled(env) &&
    env.CI === "true" &&
    env.GITHUB_ACTIONS === "true" &&
    env.CI_PERF_HARNESS === "1" &&
    env.ENV === "development" &&
    env.NODE_ENV === "production" &&
    !env.VERCEL &&
    !env.VERCEL_ENV &&
    isCiPerfSupabaseOrigin(env.SUPABASE_URL) &&
    env.CI_PERF_UPSTREAM_ORIGIN === env.NEXT_PUBLIC_API_BASE_URL
  );
}

export function assertCiPerfBuild(): void {
  const publicEnv = ciPerfPublicEnv();
  if (
    publicEnv.NEXT_PUBLIC_CI_PERF_HARNESS === "1" &&
    !ciPerfServerEnabled({ ...process.env, ...publicEnv, NODE_ENV: "production" })
  ) {
    throw new Error("CI performance features require the isolated GitHub harness");
  }
}
