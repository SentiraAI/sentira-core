import type { LucideIcon } from "lucide-react";

/** Una voce del menu. L'elenco sta nell'app (lib/nav.ts), una volta sola: lo leggono
 *  sidebar, barra in basso su mobile e intestazione. */
export interface NavItem {
  /** sidebar e intestazione di pagina */
  title: string;
  /** etichetta breve per la barra in basso su mobile */
  short: string;
  url: string;
  icon: LucideIcon;
  /** nella barra in basso su mobile; le altre voci stanno dietro "Altro" */
  principale?: boolean;
}

/** La voce del menu della pagina aperta: quella con l'url uguale, altrimenti quella
 *  di cui la pagina è una sotto-pagina (`/aziende/detail` sta sotto `/aziende`).
 *  La usano menu, testata e barra mobile: la stessa voce accesa ovunque. */
export function voceAttiva(items: NavItem[], pathname: string | null): NavItem | undefined {
  if (!pathname) return undefined;
  return (
    items.find((i) => i.url === pathname) ??
    items.find((i) => i.url !== "/" && pathname.startsWith(`${i.url}/`))
  );
}
