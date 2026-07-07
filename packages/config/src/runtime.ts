import type { LoadedEnv, PublicEnv, ServerEnv } from "./env";

export type FeatureFlags = {
  askVergeo: boolean;
  whatsappNotifications: boolean;
  cardPayments: boolean;
};

export type PublicRuntimeConfig = {
  features: FeatureFlags;
  public: PublicEnv;
};

export type ServerRuntimeConfig = {
  features: FeatureFlags;
  server: ServerEnv;
  public: PublicEnv;
};

const defaultFeatures = (): FeatureFlags => ({
  askVergeo: true,
  whatsappNotifications: true,
  cardPayments: true,
});

export function createPublicRuntimeConfig(publicEnv: PublicEnv): PublicRuntimeConfig {
  return {
    features: defaultFeatures(),
    public: publicEnv,
  };
}

export function createServerRuntimeConfig(env: LoadedEnv): ServerRuntimeConfig {
  return {
    features: defaultFeatures(),
    server: env.server,
    public: env.public,
  };
}
