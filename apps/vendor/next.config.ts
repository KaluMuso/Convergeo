import createNextIntlPlugin from "next-intl/plugin";

import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("../../packages/i18n/src/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@vergeo/config", "@vergeo/i18n", "@vergeo/types", "@vergeo/ui"],
  eslint: {
    dirs: ["app"],
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "res.cloudinary.com",
      },
    ],
  },
};

export default withNextIntl(nextConfig);
