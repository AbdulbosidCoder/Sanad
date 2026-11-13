import type { ButtonHTMLAttributes } from "react";

import { cn } from "../cn";

const variants = {
  primary: "bg-primary text-primary-fg hover:bg-forest-900",
  secondary: "border-[1.5px] border-primary bg-surface text-primary hover:bg-forest-50",
  soft: "bg-forest-100 text-primary hover:bg-forest-200",
  accent: "bg-emerald-300 text-forest-950 hover:bg-emerald-500",
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
}

export function Button({ variant = "primary", className, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex h-12 items-center justify-center rounded-md px-5 text-[15px] font-semibold transition-colors",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-500",
        "disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-muted",
        variants[variant],
        className,
      )}
      {...rest}
    />
  );
}
