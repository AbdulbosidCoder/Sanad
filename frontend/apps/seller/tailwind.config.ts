import preset from "@sanad/ui/tailwind-preset";
import type { Config } from "tailwindcss";

const config: Config = {
  presets: [preset as Config],
  content: ["./app/**/*.{ts,tsx}", "../../packages/ui/src/**/*.{ts,tsx}"],
};

export default config;
