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

/** Il titolo della sezione aperta, se è una voce del menu. */
export function titoloSezione(items: NavItem[], pathname: string | null): string | undefined {
  return items.find((i) => i.url === pathname)?.title;
}
