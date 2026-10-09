"use client";

import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3 } from "lucide-react";

/* Grafico dentro una risposta della chat. Il backend (mostra_grafico, vedi
   sentira_core.chat.grafico) lo scrive nel testo come blocco ```grafico con questo
   JSON, con i numeri presi dal database. */

interface Spec {
  titolo: string;
  forma: "barre" | "colonne";
  serie: { chiave: string; nome: string }[];
  dati: ({ nome: string } & Record<string, string | number>)[];
  nota?: string; // la base dei numeri, es. "Su 70 richieste nuove"
}

// stessa scala dei grafici della pagina Lead: toni lontani per le colonne impilate
const COLORI = ["var(--chart-1)", "var(--chart-4)", "var(--chart-2)", "var(--chart-5)"];

function leggi(testo: string): Spec | null {
  try {
    const s = JSON.parse(testo) as Spec;
    return Array.isArray(s?.dati) && s.serie?.length ? s : null;
  } catch {
    return null; // blocco troncato o malformato: niente grafico, niente crash
  }
}

function TooltipBarre({ active, payload }: {
  active?: boolean;
  payload?: { payload: { nome: string; valore: number } }[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-primary/40 bg-card/90 px-3 py-2 text-sm shadow backdrop-blur-sm">
      <div className="font-medium">{p.nome}</div>
      <div className="text-muted-foreground">{p.valore}</div>
    </div>
  );
}

function TooltipColonne({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const totale = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div className="rounded-lg border border-primary/40 bg-card/90 px-3 py-2 text-sm shadow backdrop-blur-sm">
      <div className="font-medium">{label}{payload.length > 1 && ` · ${totale}`}</div>
      {payload.filter((p) => p.value).map((p) => (
        <div key={p.name} className="text-muted-foreground">
          {payload.length > 1 && <span style={{ color: p.color }}>■ </span>}{p.name}: {p.value}
        </div>
      ))}
    </div>
  );
}

export function GraficoChat({ testo }: { testo: string }) {
  const s = leggi(testo);
  if (!s) return <p className="text-xs italic text-muted-foreground">Grafico non disponibile.</p>;

  const vuoto = s.dati.every((d) => s.serie.every((x) => !Number(d[x.chiave])));
  const piuSerie = s.serie.length > 1;

  return (
    <figure className="not-prose my-3 w-[36rem] max-w-full rounded-md border border-border/70 bg-background/40 p-3">
      <figcaption className="mb-2 flex items-center gap-2 text-sm font-medium">
        <BarChart3 size={15} className="text-primary" /> {s.titolo}
      </figcaption>
      {s.nota && <p className="-mt-1 mb-2 text-xs text-muted-foreground">{s.nota}</p>}
      {vuoto ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Nessun dato da mostrare.</p>
      ) : s.forma === "barre" ? (
        <ResponsiveContainer width="100%" height={s.dati.length * 28 + 16}>
          <BarChart
            data={s.dati.map((d) => ({ nome: d.nome, valore: Number(d[s.serie[0].chiave]) }))}
            layout="vertical" margin={{ left: 4, right: 32 }}
          >
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis type="category" dataKey="nome" fontSize={12} tickLine={false} axisLine={false} width={140} />
            <Tooltip content={<TooltipBarre />} cursor={{ fill: "var(--muted)", opacity: 0.3 }} />
            <Bar dataKey="valore" fill={COLORI[0]} radius={[0, 4, 4, 0]} animationDuration={600}
              label={{ position: "right", fontSize: 12, fill: "var(--muted-foreground)" }} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={s.dati} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="nome" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
            <Tooltip content={<TooltipColonne />} cursor={{ fill: "var(--muted)", opacity: 0.3 }} />
            {piuSerie && <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} />}
            {s.serie.map((x, i) => (
              <Bar key={x.chiave} dataKey={x.chiave} name={x.nome} stackId="serie" fill={COLORI[i % COLORI.length]}
                radius={i === s.serie.length - 1 ? [4, 4, 0, 0] : 0} animationDuration={600} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
      {!vuoto && (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none hover:text-foreground">Vedi i numeri</summary>
          <table className="mt-2 w-full border-collapse">
            <thead>
              <tr>
                <th className="border-b border-border px-2 py-1 text-left font-medium" />
                {s.serie.map((x) => <th key={x.chiave} className="border-b border-border px-2 py-1 text-right font-medium">{x.nome}</th>)}
              </tr>
            </thead>
            <tbody>
              {s.dati.map((d, i) => (
                <tr key={i}>
                  <td className="px-2 py-0.5">{d.nome}</td>
                  {s.serie.map((x) => <td key={x.chiave} className="px-2 py-0.5 text-right tabular-nums">{d[x.chiave] ?? 0}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </figure>
  );
}
