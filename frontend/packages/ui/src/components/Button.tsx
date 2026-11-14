import type { ButtonHTMLAttributes } from "react";

import { cn } from "../cn";

const variants = {
  primary: "bg-primary text-primary-fg hover:bg-primary-hover",
  secondary: "border-[1.5px] border-primary bg-surface text-primary hover:bg-primary-soft",
  soft: "bg-primary-soft text-primary-soft-fg hover:bg-surface-2",
  accent: "bg-accent text-accent-fg hover:brightness-95",
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
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        "disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-muted",
        variants[variant],
        className,
      )}
      {...rest}
    />
  );
}
