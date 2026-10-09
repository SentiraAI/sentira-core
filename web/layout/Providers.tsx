"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { TooltipProvider } from "../ui/tooltip";

/** Tema (scuro di default, chiaro con data-theme="light"), tooltip e toast. */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
      {/* 300ms: abbastanza perché un tooltip non insegua il puntatore lungo la sidebar */}
      <TooltipProvider delay={300}>{children}</TooltipProvider>
      <Toaster position="top-right" richColors closeButton />
    </ThemeProvider>
  );
}
