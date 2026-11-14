/** Tailwind preset shared by web, seller and admin: same tokens everywhere.
 *
 * Theme colors are CSS variables. Day (light) is the default, night (dark) applies when
 * `<html data-theme="dark">`, or when the OS is dark and the user has not picked a theme.
 */
import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

import { colors, fonts, radii, type ThemeToken, themes } from "./src/tokens";

function channels(hex: string): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

function vars(theme: Record<ThemeToken, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(theme).map(([k, v]) => [`--c-${k}`, channels(v)]));
}

const tokenNames = Object.keys(themes.light) as ThemeToken[];
const themeColors = Object.fromEntries(
  tokenNames.map((k) => [k, `rgb(var(--c-${k}) / <alpha-value>)`]),
);

const preset: Partial<Config> = {
  theme: {
    extend: {
      colors: {
        // Fixed brand scales (same in both themes) — for illustrations, not UI chrome.
        forest: colors.forest,
        emerald: colors.emerald,
        sand: colors.sand,
        // Semantic, theme-aware colors: use these in components.
        ...themeColors,
      },
      fontFamily: { display: [fonts.display], sans: [fonts.body] },
      borderRadius: radii,
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      addBase({
        ":root": { ...vars(themes.light), colorScheme: "light" },
        ':root[data-theme="dark"]': { ...vars(themes.dark), colorScheme: "dark" },
        "@media (prefers-color-scheme: dark)": {
          ':root:not([data-theme="light"])': { ...vars(themes.dark), colorScheme: "dark" },
        },
      });
    }),
  ],
};

export default preset;
