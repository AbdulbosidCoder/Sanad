/**
 * Interface translations (uz / ru / en). Every UI string lives in locales/*.json;
 * components never hardcode text. Product content translations come from the API.
 */
import en from "./locales/en.json";
import ru from "./locales/ru.json";
import uz from "./locales/uz.json";

export const LOCALES = ["uz", "ru", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "ru";

export type MessageKey = keyof typeof ru;
export const messages: Record<Locale, Record<MessageKey, string>> = { uz, ru, en };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Translate a key; falls back to Russian, then to the key itself (visible in QA). */
export function t(locale: Locale, key: MessageKey): string {
  return messages[locale][key] ?? messages[DEFAULT_LOCALE][key] ?? key;
}

export function translator(locale: Locale): (key: MessageKey) => string {
  return (key) => t(locale, key);
}
