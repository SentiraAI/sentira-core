"use client";

import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { SidebarMenuButton, useSidebar } from "../ui/sidebar";

/** Scuro ↔ chiaro, come voce del menu laterale (va dentro un SidebarMenuItem).
 *  `resolvedTheme`, non `theme`: è il tema davvero applicato. Finché next-themes non
 *  l'ha letto vale undefined, e trattarlo da scuro è giusto: è il tema dell'HTML
 *  statico, quindi primo e secondo disegno coincidono. */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const { state } = useSidebar();
  const scuro = resolvedTheme !== "light";

  return (
    <SidebarMenuButton onClick={() => setTheme(scuro ? "light" : "dark")} tooltip={scuro ? "Tema chiaro" : "Tema scuro"}>
      {scuro ? <Sun size={18} className="text-primary" /> : <Moon size={18} className="text-primary" />}
      {state !== "collapsed" && <span>{scuro ? "Chiaro" : "Scuro"}</span>}
    </SidebarMenuButton>
  );
}
