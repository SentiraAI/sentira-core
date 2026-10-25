/* L'impalcatura delle pagine dei frontend Sentira, uguale in ogni prodotto: il guscio
   delle pagine protette (menu, testata, barra mobile), login, 404, errore, provider,
   tema. Nell'app restano voci di menu, logo, contatori e i colori del brand. */
export { ErrorPage } from "./ErrorPage";
export { Guscio, type Conteggio } from "./Guscio";
export { Login } from "./Login";
export { NotFound } from "./NotFound";
export { Providers } from "./Providers";
export { voceAttiva, type NavItem } from "./nav";
export { useConteggio } from "./useConteggio";
