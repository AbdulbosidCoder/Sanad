import { type ThemeToken, themes } from "./tokens";

function luminance(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

// [text, background] pairs that appear in the UI. WCAG AA: 4.5:1 for normal text.
const PAIRS: [ThemeToken, ThemeToken][] = [
  ["ink", "bg"], ["ink", "surface"], ["ink", "surface-2"], ["ink", "danger-bg"],
  ["ink-muted", "bg"], ["ink-muted", "surface"], ["ink-muted", "surface-2"],
  ["primary-fg", "primary"], ["primary", "surface"], ["primary", "bg"],
  ["primary-soft-fg", "primary-soft"], ["primary", "primary-soft"],
  ["link", "surface"], ["link", "bg"], ["accent-fg", "accent"],
  ["hero-fg", "hero"], ["hero-accent", "hero"],
  ["nav-fg", "nav"], ["nav-muted", "nav"], ["nav-fg", "nav-active"],
  ["success-fg", "success-bg"], ["warning-fg", "warning-bg"], ["danger-fg", "danger-bg"],
];

describe.each(["light", "dark"] as const)("%s theme", (name) => {
  const theme = themes[name];

  it("defines exactly the same tokens as the light theme", () => {
    expect(Object.keys(theme).sort()).toEqual(Object.keys(themes.light).sort());
  });

  it.each(PAIRS)("%s on %s is readable (≥ 4.5:1)", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
  });
});
