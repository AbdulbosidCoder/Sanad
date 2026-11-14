import { type MessageKey, translator } from "@sanad/i18n";
import { Badge, Card, Logo, ThemeToggle } from "@sanad/ui";

import { getLocale } from "./locale";

const NAV: MessageKey[] = [
  "seller.nav.dashboard",
  "seller.nav.products",
  "seller.nav.orders",
  "seller.nav.inventory",
  "seller.nav.analytics",
];

export default function SellerHome() {
  const locale = getLocale();
  const t = translator(locale);
  return (
    <div className="flex min-h-screen flex-wrap">
      <nav className="flex w-full flex-col gap-1 border-b border-line bg-nav p-4 text-nav-fg md:w-60 md:border-b-0 md:border-r">
        <div className="mb-4 rounded-md bg-surface px-3 py-2">
          <Logo name={t("brand.name")} />
        </div>
        {NAV.map((key, i) => (
          <span
            key={key}
            aria-current={i === 0 ? "page" : undefined}
            className={`flex h-11 items-center justify-between rounded-md px-3 text-sm ${i === 0 ? "bg-nav-active font-semibold" : "text-nav-muted"}`}
          >
            {t(key)}
            {i > 0 && <span className="text-[11px] text-nav-muted">{t("common.comingSoon")}</span>}
          </span>
        ))}
      </nav>
      <main className="min-w-0 flex-[999_1_560px] p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-display text-2xl font-extrabold">{t("seller.title")}</h1>
          <ThemeToggle locale={locale} />
        </div>
        <Card className="mt-4 flex items-center justify-between gap-4">
          <p className="text-sm text-ink-muted">{t("seller.dashboard.placeholder")}</p>
          <Badge tone="neutral">{t("common.comingSoon")}</Badge>
        </Card>
      </main>
    </div>
  );
}
