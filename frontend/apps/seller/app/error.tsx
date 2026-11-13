"use client";

import { ErrorNotice } from "@sanad/ui";

import { getLocale } from "./locale";

/** Any unexpected rendering error lands here and shows its digest for bug reports. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto max-w-xl p-6">
      <ErrorNotice
        locale={getLocale()}
        error={{ code: "FRONTEND.RENDER_ERROR", requestId: error.digest }}
        onRetry={reset}
      />
    </main>
  );
}
