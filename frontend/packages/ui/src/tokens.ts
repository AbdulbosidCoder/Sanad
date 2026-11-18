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

/**
 * Semantic theme tokens: components use these names (bg, surface, ink, primary…),
 * never raw hex, so every screen works in both day (light) and night (dark) mode.
 * The Tailwind preset turns them into CSS variables switched by `data-theme`.
 */
export const themes = {
  light: {
    bg: "#F5F7F6",
    surface: "#FFFFFF",
    "surface-2": "#EEF2EF",
    line: "#E1E6E3",
    "line-strong": "#C9D1CC",
    ink: "#17201B",
    "ink-muted": "#5F6963",
    primary: "#124929",
    "primary-fg": "#FFFFFF",
    "primary-hover": "#0D351E",
    "primary-soft": "#DBF0E4",
    "primary-soft-fg": "#124929",
    link: "#1F7543",
    accent: "#35D49A",
    "accent-fg": "#082112",
    hero: "#082112",
    "hero-fg": "#FFFFFF",
    "hero-accent": "#35D49A",
    nav: "#082112",
    "nav-fg": "#FFFFFF",
    "nav-muted": "#B7E1C8",
    "nav-active": "#124929",
    "success-bg": "#DBF0E4",
    "success-fg": "#165A32",
    "warning-bg": "#FDF0DC",
    "warning-fg": "#8A4B06",
    "danger-bg": "#FDECEA",
    "danger-fg": "#B42318",
    "danger-line": "#F4C7C2",
    focus: "#2C9658",
  },
  dark: {
    bg: "#0A140F",
    surface: "#111D16",
    "surface-2": "#172A1F",
    line: "#223529",
    "line-strong": "#2F4739",
    ink: "#E8F0EB",
    "ink-muted": "#9EADA4",
    primary: "#42BD75",
    "primary-fg": "#06170D",
    "primary-hover": "#81CFA2",
    "primary-soft": "#173A26",
    "primary-soft-fg": "#B7E1C8",
    link: "#81CFA2",
    accent: "#35D49A",
    "accent-fg": "#082112",
    hero: "#0F2A1B",
    "hero-fg": "#FFFFFF",
    "hero-accent": "#35D49A",
    nav: "#060E0A",
    "nav-fg": "#E8F0EB",
    "nav-muted": "#9EADA4",
    "nav-active": "#173A26",
    "success-bg": "#173A26",
    "success-fg": "#81CFA2",
    "warning-bg": "#3A2A10",
    "warning-fg": "#F5C778",
    "danger-bg": "#3A1714",
    "danger-fg": "#FF9C8F",
    "danger-line": "#5C2420",
    focus: "#42BD75",
  },
} as const;

export type ThemeName = keyof typeof themes;
export type ThemeToken = keyof (typeof themes)["light"];
