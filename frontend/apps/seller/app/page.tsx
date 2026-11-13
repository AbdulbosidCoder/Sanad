import { type MessageKey, translator } from "@sanad/i18n";
import { Badge, Card, Logo } from "@sanad/ui";

import { getLocale } from "./locale";

const NAV: MessageKey[] = [
  "seller.nav.dashboard",
  "seller.nav.products",
  "seller.nav.orders",
  "seller.nav.inventory",
  "seller.nav.analytics",
];

export default function SellerHome() {
  const t = translator(getLocale());
  return (
    <div className="flex min-h-screen flex-wrap">
      <nav className="flex w-full flex-col gap-1 bg-forest-950 p-4 text-white md:w-60">
        <div className="mb-4 rounded-md bg-surface px-3 py-2">
          <Logo name={t("brand.name")} />
        </div>
        {NAV.map((key, i) => (
          <span
            key={key}
            aria-current={i === 0 ? "page" : undefined}
            className={`flex h-11 items-center justify-between rounded-md px-3 text-sm ${i === 0 ? "bg-forest-800 font-semibold" : "text-forest-200"}`}
          >
            {t(key)}
            {i > 0 && <span className="text-[11px] text-forest-300">{t("common.comingSoon")}</span>}
          </span>
        ))}
      </nav>
      <main className="min-w-0 flex-[999_1_560px] p-6">
        <h1 className="font-display text-2xl font-extrabold">{t("seller.title")}</h1>
        <Card className="mt-4 flex items-center justify-between gap-4">
          <p className="text-sm text-ink-muted">{t("seller.dashboard.placeholder")}</p>
          <Badge tone="neutral">{t("common.comingSoon")}</Badge>
        </Card>
      </main>
    </div>
  );
}
