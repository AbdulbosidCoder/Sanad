import { DEFAULT_LOCALE, type Locale } from "@sanad/i18n";

/** Current interface language. Language switching (cookie + profile) arrives with the identity module. */
export function getLocale(): Locale {
  return DEFAULT_LOCALE;
}
