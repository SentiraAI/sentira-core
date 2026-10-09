/* Mattoni dell'interfaccia comuni ai frontend Sentira.

   I componenti shadcn (button, card, dialog, sidebar…) stanno qui accanto, un file
   ciascuno: l'app li importa come sempre da "@/components/ui/<nome>", perché il suo
   tsconfig.json manda quel percorso in node_modules/sentira-core/web/ui. */
export { cn } from "./utils";
export { useIsMobile } from "./use-mobile";
export { EmptyState, ErrorState, KpiCard, LoadingState } from "./stati";
export { Conferma } from "./Conferma";
export { ChartTooltip, coloreSerie, type ChartDatum } from "./grafici";
