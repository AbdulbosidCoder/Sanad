import type { ReactNode } from "react";

import { cn } from "../cn";

const tones = {
  success: "bg-success-bg text-success-fg",
  warning: "bg-warning-bg text-warning-fg",
  danger: "bg-danger-bg text-danger-fg",
  neutral: "bg-surface-2 text-ink-muted",
} as const;

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return (
    <span className={cn("inline-flex h-7 items-center rounded-sm px-2.5 text-xs font-semibold", tones[tone])}>
      {children}
    </span>
  );
}
