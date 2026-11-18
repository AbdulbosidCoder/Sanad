"use client";

import { type Locale, t } from "@sanad/i18n";
import { useState } from "react";

import { Button } from "./Button";

export interface ErrorDetails {
  code?: string;
  module?: string;
  requestId?: string;
}

/**
 * Shown when a request fails. It always displays the error code, the backend
 * module and the request id, so a bug report needs nothing else.
 */
export function ErrorNotice({
  locale,
  error,
  onRetry,
}: {
  locale: Locale;
  error: ErrorDetails;
  onRetry?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const report = [
    error.code && `${t(locale, "error.code")}: ${error.code}`,
    error.module && error.module !== "-" && `${t(locale, "error.module")}: ${error.module}`,
    error.requestId && `${t(locale, "error.requestId")}: ${error.requestId}`,
  ]
    .filter(Boolean)
    .join("\n");

  async function copy() {
    await navigator.clipboard?.writeText(report);
    setCopied(true);
  }

  return (
    <div role="alert" className="rounded-xl border border-danger-line bg-danger-bg p-5 text-ink">
      <p className="font-display text-lg font-bold">{t(locale, "error.title")}</p>
      <p className="mt-1 text-sm text-ink-muted">{t(locale, "error.hint")}</p>
      <pre className="mt-3 whitespace-pre-wrap rounded-md bg-surface p-3 font-mono text-[13px] text-ink">{report}</pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={copy}>
          {copied ? t(locale, "error.copied") : t(locale, "error.copy")}
        </Button>
        {onRetry && <Button onClick={onRetry}>{t(locale, "error.retry")}</Button>}
      </div>
    </div>
  );
}
