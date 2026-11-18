"use client";

import { ApiError, createClient, type HealthReport, type ModuleInfo } from "@sanad/api-client";
import { type Locale, translator } from "@sanad/i18n";
import { Badge, Card, type ErrorDetails, ErrorNotice } from "@sanad/ui";
import { useCallback, useEffect, useState } from "react";

/**
 * Live system map for tech operations: health of each infrastructure component
 * and every backend module with its connections (from /api/v1/system/modules).
 */
export function SystemOverview({ locale }: { locale: Locale }) {
  const t = translator(locale);
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [modules, setModules] = useState<ModuleInfo[] | null>(null);
  const [error, setError] = useState<ErrorDetails | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const api = createClient({ locale });
    try {
      const [h, m] = await Promise.all([api.health(), api.modules()]);
      setHealth(h);
      setModules(m.modules);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      setError({ code: err?.code ?? "FRONTEND.UNKNOWN", module: err?.module, requestId: err?.requestId });
    }
  }, [locale]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorNotice locale={locale} error={error} onRetry={load} />;
  if (!health || !modules) return <p className="text-sm text-ink-muted">{t("common.loading")}</p>;

  return (
    <>
      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-bold">{t("admin.ops.health")}</h2>
        <div className="flex flex-wrap gap-3">
          {Object.entries(health.components).map(([name, status]) => (
            <Card key={name} className="flex min-w-48 items-center justify-between gap-4 py-4">
              <span className="font-semibold">{name}</span>
              <Badge tone={status === "ok" ? "success" : "danger"}>
                {status === "ok" ? t("admin.ops.status.ok") : t("admin.ops.status.down")}
              </Badge>
            </Card>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-bold">
          {t("admin.ops.modules")} · {modules.length}
        </h2>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
          {modules.map((m) => (
            <Card key={m.name} className="flex flex-col gap-2">
              <span className="font-mono text-sm font-semibold text-link">{m.name}</span>
              <p className="text-sm">{m.summary}</p>
              <Links label={t("admin.ops.dependsOn")} items={m.depends_on} />
              <Links label={t("admin.ops.emits")} items={m.emits} />
              <Links label={t("admin.ops.listens")} items={m.listens_to} />
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}

function Links({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <p className="text-xs text-ink-muted">
      <span className="font-semibold">{label}:</span> {items.join(", ")}
    </p>
  );
}
