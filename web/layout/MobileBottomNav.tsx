"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { useSidebar } from "../ui/sidebar";
import type { NavItem } from "./nav";

const VOCE = "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] transition-colors";

/** La barra in basso su mobile: le voci `principale`; se ce ne sono altre, "Altro"
 *  apre il menu laterale (su mobile è un pannello). Va dentro SidebarProvider. */
export function MobileBottomNav({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const { setOpenMobile } = useSidebar();
  const principali = items.filter((i) => i.principale);
  const altre = principali.length < items.length;
  // "Altro" è acceso quando si è su una pagina che non sta nella barra
  const inAltro = !principali.some((i) => i.url === pathname);

  return (
    <nav
      className="pb-safe fixed right-0 bottom-0 left-0 z-50 flex border-t bg-background/95 px-2 pt-2 backdrop-blur-md md:hidden"
      aria-label="Navigazione principale"
    >
      {principali.map((item) => {
        const active = pathname === item.url;
        return (
          <Link
            key={item.url}
            href={item.url}
            className={`${VOCE} ${active ? "text-primary" : "text-muted-foreground"}`}
            aria-current={active ? "page" : undefined}
          >
            <item.icon size={20} aria-hidden="true" />
            <span>{item.short}</span>
          </Link>
        );
      })}
      {altre && (
        <button
          type="button"
          onClick={() => setOpenMobile(true)}
          className={`${VOCE} ${inAltro ? "text-primary" : "text-muted-foreground"}`}
          aria-label="Altre voci del menu"
        >
          <MoreHorizontal size={20} aria-hidden="true" />
          <span>Altro</span>
        </button>
      )}
    </nav>
  );
}
