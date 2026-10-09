"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Check, MessageSquare, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { BOTTONE, dataRelativa, richiesta } from "./api";

interface Sessione {
  id: number;
  title: string | null;
  created_at: string;
}

interface Props {
  attiva: number | null;
  onSeleziona: (id: number) => void;
  onNuova: () => void;
  onRegistraAggiorna: (fn: () => void) => void;
  testata?: ReactNode;
}

const ICONA = `${BOTTONE} size-8 hover:bg-muted hover:text-foreground`;

export function PannelloSessioni({ attiva, onSeleziona, onNuova, onRegistraAggiorna, testata }: Props) {
  const [sessioni, setSessioni] = useState<Sessione[]>([]);
  const [cerca, setCerca] = useState("");
  const [caricamento, setCaricamento] = useState(false);
  const [rinomina, setRinomina] = useState<number | null>(null);
  const [nuovoTitolo, setNuovoTitolo] = useState("");
  const [confermaTutte, setConfermaTutte] = useState(false);
  const inputRinomina = useRef<HTMLInputElement>(null);

  const carica = useCallback(async () => {
    setCaricamento(true);
    try {
      setSessioni(await (await richiesta("GET", "/api/chat/sessions")).json());
    } catch {
      /* elenco non disponibile: resta quello che c'era */
    } finally {
      setCaricamento(false);
    }
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  useEffect(() => {
    onRegistraAggiorna(carica);
  }, [onRegistraAggiorna, carica]);

  const elimina = useCallback(async (id: number) => {
    try {
      await richiesta("DELETE", `/api/chat/sessions/${id}`);
    } catch (e) {
      // la chat esiste ancora sul server: la riga resta, altrimenti ricomparirebbe
      toast.error("Eliminazione fallita: " + (e as Error).message);
      return;
    }
    setSessioni((prev) => prev.filter((s) => s.id !== id));
    if (attiva === id) onNuova();
  }, [attiva, onNuova]);

  const eliminaTutte = useCallback(async () => {
    setConfermaTutte(false);
    try {
      await richiesta("DELETE", "/api/chat/sessions");
    } catch (e) {
      toast.error("Eliminazione fallita: " + (e as Error).message);
      return;
    }
    setSessioni([]);
    onNuova();
  }, [onNuova]);

  const iniziaRinomina = useCallback((s: Sessione) => {
    setRinomina(s.id);
    setNuovoTitolo(s.title ?? "");
    setTimeout(() => inputRinomina.current?.focus(), 50);
  }, []);

  const salvaRinomina = useCallback(async (id: number) => {
    const title = nuovoTitolo.trim();
    setRinomina(null);
    if (!title) return;
    try {
      const aggiornata: Sessione = await (await richiesta("PATCH", `/api/chat/sessions/${id}`, { title })).json();
      setSessioni((prev) => prev.map((s) => (s.id === id ? { ...s, title: aggiornata.title } : s)));
    } catch (e) {
      toast.error("Rinomina fallita: " + (e as Error).message);
    }
  }, [nuovoTitolo]);

  const filtrate = cerca.trim()
    ? sessioni.filter((s) => s.title?.toLowerCase().includes(cerca.trim().toLowerCase()))
    : sessioni;

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r bg-background">
      <div className="flex items-center gap-2 border-b border-border/60 px-3 py-3">
        {testata}
        <span className="led led-on text-primary" />
        <h2 className="font-display tracking-[0.1em] text-base">CHAT</h2>
      </div>

      <div className="flex gap-2 px-3 py-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={cerca}
            onChange={(e) => setCerca(e.target.value)}
            placeholder="Cerca..."
            aria-label="Cerca nelle chat"
            className="h-8 w-full rounded-lg border border-input bg-transparent pl-7 pr-2 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          />
        </div>
        {sessioni.length > 0 && (
          <button type="button" className={`${ICONA} text-muted-foreground hover:text-destructive`}
            onClick={() => setConfermaTutte(true)} title="Elimina tutte le chat" aria-label="Elimina tutte le chat">
            <Trash2 className="h-4 w-4" />
          </button>
        )}
        <button type="button" className={`${ICONA} border-border`} onClick={onNuova}
          title="Nuova chat" aria-label="Nuova chat">
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {confermaTutte && (
        <div role="alertdialog" aria-label="Eliminare tutte le chat?"
          className="mx-3 mb-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
          <p className="font-medium text-foreground">Eliminare tutte le chat?</p>
          <p className="mt-1 text-muted-foreground">Cancella tutte le conversazioni e non si può annullare.</p>
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" className={`${BOTTONE} h-7 border-border px-2.5 text-xs hover:bg-muted`}
              onClick={() => setConfermaTutte(false)}>Annulla</button>
            <button type="button" className={`${BOTTONE} h-7 bg-destructive/10 px-2.5 text-xs text-destructive hover:bg-destructive/20`}
              onClick={eliminaTutte}>Elimina tutto</button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-2">
        {caricamento && sessioni.length === 0 ? (
          <div className="space-y-2 px-2 py-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 w-full animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : filtrate.length === 0 ? (
          <div className="relative flex flex-col items-center justify-center gap-3 overflow-hidden rounded-md py-12 text-muted-foreground">
            <div className="absolute inset-0 grid-instrument opacity-40" aria-hidden />
            <MessageSquare className="relative h-8 w-8 opacity-30" />
            <p className="relative text-[11px] font-mono uppercase tracking-wider">
              {cerca.trim() ? "Nessun risultato" : "Nessuna chat"}
            </p>
          </div>
        ) : (
          <ul className="space-y-0.5 py-1">
            {filtrate.map((s) => {
              const selezionata = s.id === attiva;
              return (
                <li key={s.id}
                  className={`group relative flex items-center gap-2.5 rounded-md border px-3 py-2 transition-colors ${
                    selezionata ? "accent-rail border-primary/30 bg-primary/10"
                      : "border-transparent hover:border-border/60 hover:bg-accent/60"}`}>
                  <MessageSquare className={`h-3.5 w-3.5 shrink-0 ${selezionata ? "text-primary" : "text-muted-foreground"}`} />
                  {rinomina === s.id ? (
                    <input
                      ref={inputRinomina}
                      value={nuovoTitolo}
                      aria-label="Nuovo titolo"
                      onChange={(e) => setNuovoTitolo(e.target.value)}
                      onBlur={() => salvaRinomina(s.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") salvaRinomina(s.id);
                        if (e.key === "Escape") setRinomina(null);
                      }}
                      className="min-w-0 flex-1 border-b border-primary bg-transparent text-xs outline-none"
                    />
                  ) : (
                    <button type="button" onClick={() => onSeleziona(s.id)} className="min-w-0 flex-1 text-left">
                      <p className="truncate text-xs font-medium">{s.title ?? "Chat senza titolo"}</p>
                      <p className="font-mono text-[10px] tabular-nums text-muted-foreground/80">{dataRelativa(s.created_at)}</p>
                    </button>
                  )}
                  {rinomina === s.id ? (
                    <span className="flex shrink-0 gap-0.5">
                      <button type="button" className={`${ICONA} size-6`} onMouseDown={(e) => e.preventDefault()}
                        onClick={() => salvaRinomina(s.id)} aria-label="Salva titolo"><Check className="h-3.5 w-3.5" /></button>
                      <button type="button" className={`${ICONA} size-6`} onMouseDown={(e) => e.preventDefault()}
                        onClick={() => setRinomina(null)} aria-label="Annulla"><X className="h-3.5 w-3.5" /></button>
                    </span>
                  ) : (
                    <span className="flex shrink-0 gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                      <button type="button" className={`${ICONA} size-6`} onClick={() => iniziaRinomina(s)}
                        title="Rinomina" aria-label="Rinomina"><Pencil className="h-3.5 w-3.5" /></button>
                      <button type="button" className={`${ICONA} size-6 hover:text-destructive`} onClick={() => elimina(s.id)}
                        title="Elimina" aria-label="Elimina"><Trash2 className="h-3.5 w-3.5" /></button>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
