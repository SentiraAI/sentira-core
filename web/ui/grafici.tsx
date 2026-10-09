/* Pezzi comuni dei grafici recharts. */

export type ChartDatum = { nome: string; valore: number; extra?: string };

// toni lontani prima dei vicini: due serie affiancate o impilate non si confondono
const ORDINE = [1, 4, 2, 5, 3];

/** Colore della serie (o della barra) i-esima, dai token --chart-1…5 del tema:
 *  segue da solo il cambio chiaro/scuro. */
export function coloreSerie(i: number): string {
  return `var(--chart-${ORDINE[i % ORDINE.length]})`;
}

/** Tooltip di un grafico a una serie: nome, valore e una riga in più facoltativa. */
export function ChartTooltip({ active, payload }: {
  active?: boolean;
  payload?: { payload: ChartDatum }[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-primary/40 bg-card/90 px-3 py-2 text-sm shadow backdrop-blur-sm">
      <div className="font-medium">{p.nome}</div>
      <div className="text-muted-foreground">{p.valore}</div>
      {p.extra && <div className="text-xs text-muted-foreground/70">{p.extra}</div>}
    </div>
  );
}
