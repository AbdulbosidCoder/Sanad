import "./globals.css";

import type { Metadata } from "next";
import { themeInitScript } from "@sanad/ui";
import { Inter, Manrope } from "next/font/google";
import type { ReactNode } from "react";

import { getLocale } from "./locale";

const display = Manrope({ subsets: ["latin", "cyrillic"], weight: ["700", "800"], variable: "--font-display" });
const body = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-body" });

export const metadata: Metadata = { title: "Sanad" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: the inline script sets data-theme before React hydrates.
    <html lang={getLocale()} className={`${display.variable} ${body.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
