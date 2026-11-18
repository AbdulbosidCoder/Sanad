import { translator } from "@sanad/i18n";
import { Button, Card, Logo, ThemeToggle } from "@sanad/ui";

import { getLocale } from "./locale";

export default function HomePage() {
  const locale = getLocale();
  const t = translator(locale);
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-5">
      <header className="flex items-center justify-between gap-4">
        <Logo name={t("brand.name")} />
        <ThemeToggle locale={locale} />
      </header>

      <label className="flex h-12 items-center gap-3 rounded-lg border border-line bg-surface px-4">
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink-muted">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          type="search"
          aria-label={t("common.search.placeholder")}
          placeholder={t("common.search.placeholder")}
          className="flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-muted"
        />
      </label>

      <section className="flex flex-col gap-2 rounded-xl bg-hero p-6 text-hero-fg">
        <span className="text-xs font-semibold uppercase tracking-widest text-hero-accent">
          {t("web.home.weeklyHits.label")}
        </span>
        <h1 className="font-display text-2xl font-extrabold md:text-3xl">{t("web.home.weeklyHits.title")}</h1>
        <div className="mt-2">
          <Button variant="secondary" className="border-0">{t("web.home.weeklyHits.cta")}</Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-bold">{t("web.home.recommended")}</h2>
        <Card className="text-sm text-ink-muted">{t("web.home.emptyCatalog")}</Card>
      </section>
    </main>
  );
}
