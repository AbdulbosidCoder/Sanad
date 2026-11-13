/**
 * Design tokens — the single source of truth for colors, type and shape.
 * Primary: forest-800 #124929 (hsl 145 60% 18%). See the design canvas:
 * https://claude.ai/artifact/88UWca9HczPSqwZn8XyYnM
 */
export const colors = {
  forest: {
    50: "#F1F9F4",
    100: "#DBF0E4",
    200: "#B7E1C8",
    300: "#81CFA2",
    400: "#42BD75",
    500: "#2C9658",
    600: "#1F7543",
    700: "#165A32",
    800: "#124929",
    900: "#0D351E",
    950: "#082112",
  },
  emerald: { 50: "#D6F5EA", 300: "#35D49A", 500: "#1FAD79" },
  sand: { 50: "#F7F0E2", 500: "#C8A464", 700: "#8C6B2E" },
  neutral: {
    bg: "#F5F7F6",
    surface: "#FFFFFF",
    border: "#E1E6E3",
    borderStrong: "#C9D1CC",
    muted: "#66706A",
    text: "#17201B",
  },
  status: { success: "#1F7543", warning: "#8A4B06", danger: "#B42318", info: "#1D4ED8" },
} as const;

export const fonts = {
  display: "var(--font-display), Manrope, system-ui, sans-serif",
  body: "var(--font-body), Inter, system-ui, sans-serif",
} as const;

export const radii = { sm: "8px", md: "12px", lg: "16px", xl: "20px", pill: "999px" } as const;
