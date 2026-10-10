"use client";

import { useState, type ReactNode } from "react";
import { CreditCard, Loader2, RefreshCw } from "lucide-react";
import { useApi } from "../api";
import { data as dataIt, plurale } from "../formato";
import { Card, CardContent } from "../ui/card";

/* Forma di usage_stats (sentira_core.ai_usage). */
interface Voce { richieste: number; cost_eur: number }
interface Consumo {
  current: {
    mese: string; cost_eur: number; richieste: number;
    per_feature: Record<string, Voce>;
  };
  history: { mese: string; cost_eur: number; richieste: number }[];
  totals: {
    richieste: number; cost_eur: number;
    prompt_tokens: number; completion_tokens: number; dal: string | null;
  };
}

const MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];
const meseBreve = (mese: string) => MESI_BREVI[parseInt(mese.slice(5, 7), 10) - 1] ?? mese;

/** Barra orizzontale: etichetta + barra proporzionale + valore. */
function BarraCosto({ label, cost, max }: { label: string; cost: number; max: number }) {
  const pct = max > 0 ? Math.max((cost / max) * 100, 2) : 0;
  return (
    <div className="flex items-center gap-2.5">
      <span className="font-instrument text-[11px] uppercase tracking-[0.12em] text-muted-foreground w-40 shrink-0 truncate">
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-muted/50 overflow-hidden">
        <div className="h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-foreground/80 tabular-nums w-16 text-right">
        € {cost.toFixed(2)}
      </span>
    </div>
  );
}

/** Spesa AI in euro: mese corrente, storico a barre (6/12/24 mesi), costo per funzione
 *  e totali dall'inizio. `etichette` traduce i nomi delle feature dell'app;
 *  `intestazione` sostituisce il titolo; `className` va sulla card. */
export function ConsumoAI({ etichette = {}, intestazione, className }: {
  etichette?: Record<string, string>;
  intestazione?: ReactNode;
  className?: string;
}) {
  const [mesi, setMesi] = useState(6);
  const [hovered, setHovered] = useState<string | null>(null);
  const { data, error, refetch } = useApi<Consumo>(`/api/usage/stats?mesi=${mesi}`);

  const titolo = intestazione ?? (
    <div className="flex items-center gap-3 pb-3 border-b border-border/60">
      <CreditCard size={15} className="text-primary" strokeWidth={1.75} />
      <h2 className="font-display tracking-[0.18em] text-base text-foreground/90">CONSUMO AI</h2>
    </div>
  );

  if (!data) {
    return (
      <Card className={className}><CardContent className="pt-6">
        {titolo}
        {error ? (
          <p className="text-sm text-destructive pt-3">Errore caricamento: {error}</p>
        ) : (
          <div className="pt-4 flex items-center gap-2 text-muted-foreground">
            <Loader2 className="animate-spin h-4 w-4" />
            <span className="text-sm">Caricamento statistiche…</span>
          </div>
        )}
      </CardContent></Card>
    );
  }

  const c = data.current;
  const t = data.totals;
  const maxMese = Math.max(...data.history.map(h => h.cost_eur), 0.0001);
  const features = Object.entries(c.per_feature)
    .map(([k, v]) => ({ label: etichette[k] ?? k, ...v }))
    .sort((a, b) => b.cost_eur - a.cost_eur);
  const maxFeature = Math.max(...features.map(f => f.cost_eur), 0.0001);

  return (
    <Card className={className}>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {titolo}
            <span className="font-instrument text-[10px] uppercase tracking-[0.12em] text-primary/70 border border-primary/30 rounded px-1.5 py-0.5">
              Pay-per-use
            </span>
          </div>
          <button onClick={refetch} title="Aggiorna"
            className="text-muted-foreground/60 hover:text-primary transition-colors">
            <RefreshCw size={13} />
          </button>
        </div>

        {t.richieste === 0 ? (
          <p className="text-sm text-muted-foreground pt-4">
            Nessuna attività AI registrata. Apparirà qui non appena l&apos;AI verrà usata.
          </p>
        ) : (
          <div className="pt-4 space-y-5">
            <div>
              <div className="flex items-baseline justify-between">
                <div className="flex items-baseline gap-2">
                  <span className="font-display text-3xl tracking-wide tabular-nums">
                    € {c.cost_eur.toFixed(2)}
                  </span>
                  <span className="font-instrument text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
                    questo mese
                  </span>
                </div>
                <div className="font-mono text-sm text-muted-foreground tabular-nums">
                  {plurale(c.richieste, "richiesta", "richieste")}
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground/70 mt-1.5">
                Pay-per-use — paghi solo ciò che consumi, nessun tetto mensile.
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="font-instrument text-[11px] uppercase tracking-[0.15em] text-muted-foreground">
                  Ultimi {mesi} mesi
                </div>
                <div className="flex gap-0.5">
                  {[6, 12, 24].map(m => (
                    <button key={m} onClick={() => setMesi(m)}
                      className={`font-instrument text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                        mesi === m ? "bg-primary/20 text-primary" : "text-muted-foreground/60 hover:text-foreground"
                      }`}>
                      {m}
                    </button>
                  ))}
                </div>
              </div>
              <div className={`flex items-end justify-between h-20 ${mesi > 12 ? "gap-0.5" : "gap-1"}`}>
                {data.history.map((h, i) => {
                  const altezza = h.cost_eur > 0 ? Math.max((h.cost_eur / maxMese) * 100, 4) : 0;
                  const corrente = h.mese === c.mese;
                  const showLabel = i % (mesi > 12 ? 2 : 1) === 0 || corrente;
                  const isHover = hovered === h.mese;
                  return (
                    <div key={h.mese}
                      className="relative flex flex-col items-center gap-1 flex-1 h-full"
                      onMouseEnter={() => setHovered(h.mese)}
                      onMouseLeave={() => setHovered(null)}>
                      {isHover && (
                        <div className="absolute -top-1 left-1/2 -translate-x-1/2 -translate-y-full z-10 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 shadow-lg pointer-events-none">
                          <div className="font-mono text-xs text-foreground">€ {h.cost_eur.toFixed(2)}</div>
                          <div className="text-[10px] text-muted-foreground">{plurale(h.richieste, "richiesta", "richieste")}</div>
                        </div>
                      )}
                      <div className="w-full flex-1 min-h-0 flex items-end justify-center">
                        <div
                          className={`w-full max-w-[1.75rem] rounded-t-sm transition-all ${
                            h.cost_eur > 0
                              ? (corrente || isHover) ? "bg-primary" : "bg-primary/40"
                              : "bg-muted/30"
                          }`}
                          style={{ height: `${altezza}%`, minHeight: h.cost_eur > 0 ? "3px" : "1px" }}
                        />
                      </div>
                      {showLabel && (
                        <span className={`font-instrument text-[10px] ${corrente ? "text-primary" : "text-muted-foreground/60"}`}>
                          {meseBreve(h.mese)}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {features.length > 0 && (
              <div>
                <div className="font-instrument text-[11px] uppercase tracking-[0.15em] text-muted-foreground mb-2">
                  Per funzione
                </div>
                <div className="space-y-1.5">
                  {features.map(f => (
                    <BarraCosto key={f.label} label={f.label} cost={f.cost_eur} max={maxFeature} />
                  ))}
                </div>
              </div>
            )}

            <div className="pt-3 border-t border-border/40">
              <div className="font-instrument text-[11px] uppercase tracking-[0.15em] text-muted-foreground mb-2">
                Dal primo utilizzo {t.dal && <span className="text-foreground/60">· {dataIt(t.dal, "media")}</span>}
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="font-display text-xl tabular-nums">{t.richieste.toLocaleString("it-IT")}</div>
                  <div className="font-instrument text-[10px] uppercase tracking-[0.12em] text-muted-foreground">richieste totali</div>
                </div>
                <div>
                  <div className="font-display text-xl tabular-nums">€ {t.cost_eur.toFixed(2)}</div>
                  <div className="font-instrument text-[10px] uppercase tracking-[0.12em] text-muted-foreground">spesa totale</div>
                </div>
                <div>
                  <div className="font-display text-xl tabular-nums">{((t.prompt_tokens + t.completion_tokens) / 1_000_000).toFixed(2)}M</div>
                  <div className="font-instrument text-[10px] uppercase tracking-[0.12em] text-muted-foreground">token processati</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
