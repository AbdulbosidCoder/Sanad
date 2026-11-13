import type { ReactNode } from "react";

import { cn } from "../cn";

const tones = {
  success: "bg-forest-100 text-forest-700",
  warning: "bg-[#FDF0DC] text-warning",
  danger: "bg-[#FDE7E5] text-danger",
  neutral: "bg-bg text-ink-muted",
} as const;

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return (
    <span className={cn("inline-flex h-7 items-center rounded-sm px-2.5 text-xs font-semibold", tones[tone])}>
      {children}
    </span>
  );
}
