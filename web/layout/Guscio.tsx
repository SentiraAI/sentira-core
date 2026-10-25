"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { LogOut } from "lucide-react";
import { AuthGuard } from "../auth/AuthGuard";
import { esci } from "../auth/esci";
import { Separator } from "../ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "../ui/sidebar";
import { cn } from "../ui/utils";
import { MobileBottomNav } from "./MobileBottomNav";
import { ThemeToggle } from "./ThemeToggle";
import { voceAttiva, type NavItem } from "./nav";

/** Il numero accanto a una voce del menu: da fare (colore del brand) oppure solo
 *  informativo, `{ n, tono: "info" }`. Zero non si mostra. */
export type Conteggio = number | { n: number; tono: "info" };

const nessunConteggio = (): Record<string, Conteggio> => ({});

/** Tutto ciò che sta intorno alle pagine protette, uguale in ogni prodotto: login
 *  verificato, menu laterale (icone da chiuso, pannello su mobile), testata con il
 *  titolo della sezione e l'orologio, barra in basso su mobile. L'app passa solo ciò
 *  che è suo; in `app/(protected)/layout.tsx`:
 *
 *    <Guscio nome="Lead Hunter" logo={<Logo size={32} />} voci={NAV_ITEMS}
 *            useConteggi={useConteggiMenu}>{children}</Guscio>
 */
export function Guscio({ nome, logo, voci, useConteggi = nessunConteggio, testata, children }: {
  /** il nome del prodotto: accanto al logo e come titolo fuori dalle voci del menu */
  nome: string;
  /** il logo, già dimensionato (32 px) */
  logo: ReactNode;
  /** le voci del menu, da `lib/nav.ts` */
  voci: NavItem[];
  /** hook che restituisce i contatori per url (`{ "/inbox": 3 }`), di solito con
   *  `useConteggio`. Gira solo dopo il login: niente richieste da anonimi */
  useConteggi?: () => Record<string, Conteggio>;
  /** in testata, a destra prima dello stato: un'etichetta «Demo», un'azione globale */
  testata?: ReactNode;
  children: ReactNode;
}) {
  return (
    <AuthGuard>
      <SidebarProvider>
        <BarraLaterale nome={nome} logo={logo} voci={voci} useConteggi={useConteggi} />
        <main className="flex min-h-screen min-w-0 flex-1 flex-col">
          <Testata nome={nome} voci={voci}>{testata}</Testata>
          <div className="flex-1 p-6 pb-20 md:pb-6 print:p-0">{children}</div>
        </main>
        <MobileBottomNav items={voci} />
      </SidebarProvider>
    </AuthGuard>
  );
}

function Contatore({ c }: { c: Conteggio | undefined }) {
  const n = typeof c === "number" ? c : (c?.n ?? 0);
  if (n <= 0) return null;
  return (
    <span
      className={cn(
        "ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-bold",
        typeof c === "number" ? "bg-primary text-primary-foreground" : "bg-warning/20 text-warning",
      )}
    >
      {n}
    </span>
  );
}

function BarraLaterale({ nome, logo, voci, useConteggi }: {
  nome: string;
  logo: ReactNode;
  voci: NavItem[];
  useConteggi: () => Record<string, Conteggio>;
}) {
  const attiva = voceAttiva(voci, usePathname());
  const { state, setOpenMobile } = useSidebar();
  const collapsed = state === "collapsed";
  const conteggi = useConteggi();

  return (
    <Sidebar variant="sidebar" collapsible="icon">
      <SidebarHeader className="card-copper-top border-b px-4 py-3">
        <div className="flex items-center gap-2">
          {logo}
          {!collapsed && <span className="text-sm font-semibold">{nome}</span>}
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {voci.map((item) => {
                const active = item === attiva;
                return (
                  <SidebarMenuItem key={item.url}>
                    <motion.div
                      className="relative"
                      whileHover={{ scale: 1.02 }}
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    >
                      {active && (
                        <motion.div
                          layoutId="sidebar-active-indicator"
                          className="absolute top-1/2 left-0 h-7 w-[3px] -translate-y-1/2 rounded-r-full bg-primary"
                          style={{ boxShadow: "-2px 0 8px color-mix(in oklch, var(--primary) 50%, transparent)" }}
                          transition={{ type: "spring", stiffness: 380, damping: 30 }}
                        />
                      )}
                      <SidebarMenuButton
                        render={<Link href={item.url} />}
                        isActive={active}
                        tooltip={item.title}
                        // su mobile il menu è un pannello (si apre da "Altro" o dall'icona in alto): chiuderlo alla scelta
                        onClick={() => setOpenMobile(false)}
                      >
                        <item.icon size={18} />
                        <span>{item.title}</span>
                        <Contatore c={conteggi[item.url]} />
                      </SidebarMenuButton>
                    </motion.div>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t">
        <SidebarMenu>
          <SidebarMenuItem>
            <ThemeToggle />
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={esci} tooltip="Esci" className="text-muted-foreground hover:text-foreground">
              <LogOut size={18} />
              {!collapsed && <span>Esci</span>}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function Testata({ nome, voci, children }: { nome: string; voci: NavItem[]; children?: ReactNode }) {
  const titolo = voceAttiva(voci, usePathname())?.title ?? nome;
  // null al primo disegno: l'HTML statico non ha un'ora, e disegnarne una darebbe
  // un errore di hydration. Il primo tick arriva al frame dopo, poi uno al secondo.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    const raf = requestAnimationFrame(tick);
    const id = setInterval(tick, 1000);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(id);
    };
  }, []);

  const ora = now?.toLocaleTimeString("it-IT", { hour12: false }) ?? "--:--:--";
  const giorno = now?.toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "short" }) ?? "";

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md print:hidden">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-6" />
      <span className="font-display text-sm tracking-wide text-foreground/90">{titolo}</span>

      <div className="ml-auto flex items-center gap-3">
        {children}
        <span className="flex items-center gap-1.5 text-[10px] tracking-[0.18em] text-muted-foreground uppercase">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/50" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
          </span>
          Online
        </span>

        <Separator orientation="vertical" className="hidden h-5 sm:block" />

        <div className="hidden items-center gap-2 sm:flex">
          <span className="font-instrument text-sm text-foreground/80 tabular-nums">{ora}</span>
          <span className="text-[10px] tracking-[0.18em] text-muted-foreground uppercase">{giorno}</span>
        </div>
      </div>
    </header>
  );
}
