"use client";

import { type Locale, t } from "@sanad/i18n";
import { useEffect, useState } from "react";

import { applyTheme, readThemePreference, THEME_PREFERENCES, type ThemePreference } from "../theme";

const ICONS: Record<ThemePreference, string> = {
  system: "M4 5h16v11H4zM8 20h8M12 16v4",
  light: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z",
  dark: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
};

const LABELS = { system: "theme.system", light: "theme.light", dark: "theme.dark" } as const;

/** Cycles system → day → night. The choice is remembered in this browser. */
export function ThemeToggle({ locale }: { locale: Locale }) {
  const [pref, setPref] = useState<ThemePreference>("system");

  useEffect(() => {
    setPref(readThemePreference());
  }, []);

  function next() {
    const i = THEME_PREFERENCES.indexOf(pref);
    const value = THEME_PREFERENCES[(i + 1) % THEME_PREFERENCES.length] ?? "system";
    applyTheme(value);
    setPref(value);
  }

  const label = `${t(locale, "theme.toggle")}: ${t(locale, LABELS[pref])}`;
  return (
    <button
      type="button"
      onClick={next}
      aria-label={label}
      title={label}
      className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-3 text-sm font-semibold text-ink hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
    >
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d={ICONS[pref]} />
      </svg>
      <span className="hidden sm:inline">{t(locale, LABELS[pref])}</span>
    </button>
  );
}
