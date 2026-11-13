import { translator } from "@sanad/i18n";
import { Logo } from "@sanad/ui";

import { getLocale } from "./locale";
import { SystemOverview } from "./system-overview";

export default function AdminHome() {
  const locale = getLocale();
  const t = translator(locale);
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <Logo name={t("brand.name")} />
        <span className="text-sm font-semibold text-ink-muted">{t("admin.title")}</span>
      </header>
      <h1 className="font-display text-2xl font-extrabold">{t("admin.ops.title")}</h1>
      <SystemOverview locale={locale} />
    </main>
  );
}
