/** Tailwind preset shared by web, seller and admin: same tokens everywhere. */
import type { Config } from "tailwindcss";

import { colors, fonts, radii } from "./src/tokens";

const preset: Partial<Config> = {
  theme: {
    extend: {
      colors: {
        forest: colors.forest,
        emerald: colors.emerald,
        sand: colors.sand,
        bg: colors.neutral.bg,
        surface: colors.neutral.surface,
        line: { DEFAULT: colors.neutral.border, strong: colors.neutral.borderStrong },
        ink: { DEFAULT: colors.neutral.text, muted: colors.neutral.muted },
        success: colors.status.success,
        warning: colors.status.warning,
        danger: colors.status.danger,
        info: colors.status.info,
        primary: { DEFAULT: colors.forest[800], fg: "#FFFFFF" },
      },
      fontFamily: { display: [fonts.display], sans: [fonts.body] },
      borderRadius: radii,
    },
  },
};

export default preset;
