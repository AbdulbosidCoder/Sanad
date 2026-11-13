import { LOCALES, messages, t } from "./index";

describe("interface translations", () => {
  const reference = Object.keys(messages.ru).sort();

  it.each(LOCALES)("%s has exactly the same keys as ru", (locale) => {
    expect(Object.keys(messages[locale]).sort()).toEqual(reference);
  });

  it.each(LOCALES)("%s has no empty strings", (locale) => {
    const empty = Object.entries(messages[locale]).filter(([, v]) => !v.trim());
    expect(empty).toEqual([]);
  });

  it("translates", () => {
    expect(t("uz", "error.retry")).toBe("Qayta urinish");
    expect(t("en", "error.retry")).toBe("Try again");
  });
});
