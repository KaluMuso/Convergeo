import { tailwindPreset } from "@vergeo/config";

import type { Config } from "tailwindcss";

const config: Config = {
  presets: [tailwindPreset as Config],
  content: ["./app/**/*.{ts,tsx}"],
};

export default config;
