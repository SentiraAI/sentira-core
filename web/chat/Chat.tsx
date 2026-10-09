"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { Bot, Check, ChevronDown, ChevronRight, Copy, Plus, RefreshCw, Send, Square } from "lucide-react";
import { BOTTONE, richiesta } from "./api";
import { GraficoChat } from "./GraficoChat";
import { PannelloSessioni } from "./PannelloSessioni";

/* La pagina chat completa (elenco sessioni + conversazione), uguale per ogni cliente.
   Parla con le route di sentira_core.chat: POST /api/chat in SSE, /api/chat/sessions,
   /api/chat/config per i testi. */

interface Messaggio {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
}

interface Config {
  titolo: string;
  descrizione: string;
  suggerimenti: string[];
}

interface Props {
  /** chiave di localStorage della sessione aperta, diversa per ogni prodotto */
  chiaveSessione: string;
  /** cosa mettere in testa al pannello delle sessioni, es. il SidebarTrigger dell'app */
  testata?: ReactNode;
}

const PENSIERI = ["Sto pensando…", "Analizzo i dati…", "Consulto il database…",
  "Cerco informazioni…", "Collego i dati…", "Quasi pronto…"];

function Pensiero({ indice }: { indice: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className="accent-rail ml-1 flex items-center gap-3 py-2 pl-3 pr-4" role="status">
      <span className="inline-flex gap-1">
        <span className="size-1.5 rounded-full bg-primary animate-pulse-dot" />
        <span className="size-1.5 rounded-full bg-primary animate-pulse-dot" />
        <span className="size-1.5 rounded-full bg-primary animate-pulse-dot" />
      </span>
      <span className="font-instrument text-[11px] uppercase tracking-[0.18em] animate-shimmer bg-gradient-to-r from-muted-foreground/60 via-primary to-muted-foreground/60 bg-[length:200%_100%] bg-clip-text text-transparent">
        {PENSIERI[indice]}
      </span>
    </motion.div>
  );
}

function Strumento({ etichetta }: { etichetta: string }) {
  const ridotto = useReducedMotion();
  return (
    <motion.div initial={ridotto ? undefined : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      exit={ridotto ? undefined : { opacity: 0 }} transition={{ duration: 0.2 }} role="status"
      className="accent-rail ml-1 flex items-center gap-2.5 py-1.5 pl-3 pr-3 text-xs text-muted-foreground">
      <span className="led led-on text-primary" />
      <span className="animate-shimmer bg-gradient-to-r from-muted-foreground/60 via-primary to-muted-foreground/60 bg-[length:200%_100%] bg-clip-text font-mono tracking-wide text-transparent">
        {etichetta}
      </span>
    </motion.div>
  );
}

function BloccoCodice({ children, className }: { children?: ReactNode; className?: string }) {
  const [copiato, setCopiato] = useState(false);
  const testo = String(children).replace(/\n$/, "");
  return (
    <div className="group relative my-2">
      <pre className={`overflow-x-auto rounded-lg border bg-muted/50 p-3 text-sm ${className ?? ""}`}>
        <code>{children}</code>
      </pre>
      <button type="button" aria-label="Copia"
        className={`${BOTTONE} absolute right-1.5 top-1.5 size-7 opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100`}
        onClick={async () => {
          await navigator.clipboard.writeText(testo);
          setCopiato(true);
          setTimeout(() => setCopiato(false), 2000);
        }}>
        {copiato ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}

function Risposta({ testo }: { testo: string }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none break-words [&_a]:text-primary [&_a]:underline [&_a]:decoration-primary/40 [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          // il blocco lo disegnano BloccoCodice e GraficoChat: niente <pre> doppio
          pre: ({ children }) => <>{children}</>,
          // nessun tool produce immagini: una ![...](...) è inventata
          img: () => null,
          code({ className, children, ...props }) {
            if (className === "language-grafico") return <GraficoChat testo={String(children)} />;
            if (className?.startsWith("language-")) return <BloccoCodice className={className}>{children}</BloccoCodice>;
            return <code className="rounded bg-muted-foreground/15 px-1 py-0.5 font-mono text-xs" {...props}>{children}</code>;
          },
          a({ href, children, ...props }) {
            if (!href || !/^https?:/.test(href)) return <span className="line-through opacity-60">{children}</span>;
            return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
          },
        }}
      >
        {testo}
      </ReactMarkdown>
    </div>
  );
}

export function Chat({ chiaveSessione, testata }: Props) {
  const ridotto = useReducedMotion();
  const [config, setConfig] = useState<Config | null>(null);
  const [messaggi, setMessaggi] = useState<Messaggio[]>([]);
  const [input, setInput] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const [strumento, setStrumento] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [pensiero, setPensiero] = useState(0);
  const [sessionId, setSessionId] = useState<number | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = localStorage.getItem(chiaveSessione);
      return raw ? Number(raw) : null;
    } catch {
      return null;
    }
  });
  const [caricaStorico, setCaricaStorico] = useState(false);
  const [scorrimentoUtente, setScorrimentoUtente] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const caricatoRef = useRef(false);
  const aggiornaPannello = useRef<(() => void) | null>(null);

  const ricorda = useCallback((id: number | null) => {
    try {
      if (id) localStorage.setItem(chiaveSessione, String(id));
      else localStorage.removeItem(chiaveSessione);
    } catch {
      /* storage non disponibile: la sessione vale solo per questa pagina */
    }
  }, [chiaveSessione]);

  useEffect(() => {
    richiesta("GET", "/api/chat/config").then((r) => r.json()).then(setConfig).catch(() => {});
  }, []);

  useEffect(() => {
    if (!sessionId || caricatoRef.current) return;
    caricatoRef.current = true;
    setCaricaStorico(true);
    richiesta("GET", `/api/chat/sessions/${sessionId}`)
      .then((r) => r.json())
      .then((data: { messages: Messaggio[] }) => setMessaggi(data.messages ?? []))
      .catch(() => {
        // sessione sparita (404): l'id ricordato è vecchio
        ricorda(null);
        setSessionId(null);
      })
      .finally(() => setCaricaStorico(false));
  }, [sessionId, ricorda]);

  useEffect(() => {
    if (!inCorso || strumento) return;
    const t = setInterval(() => setPensiero((p) => (p + 1) % PENSIERI.length), 2200);
    return () => clearInterval(t);
  }, [inCorso, strumento]);

  useEffect(() => {
    ricorda(sessionId);
  }, [sessionId, ricorda]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && !scorrimentoUtente) el.scrollTop = el.scrollHeight;
  }, [messaggi, strumento, scorrimentoUtente]);

  const aggiornaUltimo = useCallback((fn: (m: Messaggio) => Messaggio) => {
    setMessaggi((prev) => {
      const ultimo = prev[prev.length - 1];
      return ultimo?.role === "assistant" ? [...prev.slice(0, -1), fn(ultimo)] : prev;
    });
  }, []);

  const invia = useCallback(async () => {
    const testo = input.trim();
    if (!testo || inCorso) return;
    setErrore(null);
    setInput("");
    setInCorso(true);
    setScorrimentoUtente(false);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setMessaggi((prev) => [...prev, { role: "user", content: testo },
      { role: "assistant", content: "", pending: true }]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await richiesta("POST", "/api/chat", { message: testo, session_id: sessionId }, controller.signal);
      const reader = res.body?.getReader();
      if (!reader) throw new Error("Nessuna risposta dal server");
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const righe = buffer.split("\n");
        buffer = righe.pop() || "";
        for (const riga of righe) {
          if (!riga.startsWith("data: ")) continue;
          let ev;
          try {
            ev = JSON.parse(riga.slice(6));
          } catch {
            continue;
          }
          if (ev.type === "text") {
            setStrumento(null);
            aggiornaUltimo((m) => ({ ...m, content: m.content + ev.content }));
          } else if (ev.type === "tool") {
            setStrumento(ev.etichetta || "Sto elaborando…");
          } else if (ev.type === "done") {
            setStrumento(null);
            setSessionId(ev.session_id);
            caricatoRef.current = true;
            // testo definitivo del server: senza grafici non usciti dal database
            aggiornaUltimo((m) => ({ ...m, content: ev.content ?? m.content, pending: false }));
            aggiornaPannello.current?.();
          } else if (ev.type === "error") {
            throw new Error(ev.detail || "Errore durante la risposta");
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        aggiornaUltimo((m) => ({ ...m, pending: false }));
      } else {
        setErrore((e as Error).message || "Errore di connessione");
        setMessaggi((prev) => (prev[prev.length - 1]?.pending ? prev.slice(0, -1) : prev));
      }
    } finally {
      setInCorso(false);
      setStrumento(null);
      abortRef.current = null;
    }
  }, [input, inCorso, sessionId, aggiornaUltimo]);

  const riprova = useCallback(() => {
    const idx = messaggi.findLastIndex((m) => m.role === "user");
    if (idx < 0) return;
    setInput(messaggi[idx].content);
    setMessaggi(messaggi.slice(0, idx));
    setErrore(null);
  }, [messaggi]);

  const nuova = useCallback(() => {
    setMessaggi([]);
    setSessionId(null);
    setErrore(null);
    caricatoRef.current = false;
    aggiornaPannello.current?.();
  }, []);

  const seleziona = useCallback((id: number) => {
    if (id === sessionId) return; // già aperta: ricaricarla svuoterebbe la vista
    setMessaggi([]);
    setErrore(null);
    caricatoRef.current = false;
    setSessionId(id);
  }, [sessionId]);

  const registraAggiorna = useCallback((fn: () => void) => {
    aggiornaPannello.current = fn;
  }, []);

  const ultimo = messaggi[messaggi.length - 1];

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-row">
      <PannelloSessioni attiva={sessionId} onSeleziona={seleziona} onNuova={nuova}
        onRegistraAggiorna={registraAggiorna} testata={testata} />

      <div className="relative flex min-w-0 flex-1 flex-col pl-6">
        <div className="flex shrink-0 items-center justify-between border-b border-border/60 pb-4">
          <div className="flex items-center gap-3">
            <span className={`led ${inCorso ? "led-on text-success" : "text-muted-foreground/50"}`} />
            <div>
              <h1 className="font-display text-3xl leading-none tracking-[0.08em]">CHAT</h1>
              <p className="mt-1.5 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">Sentira AI</p>
            </div>
          </div>
          {messaggi.length > 0 && (
            <button type="button" onClick={nuova}
              className={`${BOTTONE} h-7 border-border bg-background px-2.5 text-[0.8rem] hover:border-primary/50 hover:bg-primary/10`}>
              <Plus size={14} />
              <span className="hidden sm:inline">Nuova</span>
            </button>
          )}
        </div>

        <div ref={scrollRef} className="-mx-4 flex-1 overflow-y-auto px-4"
          onScroll={() => {
            const el = scrollRef.current;
            if (el) setScorrimentoUtente(el.scrollHeight - el.scrollTop - el.clientHeight >= 80);
          }}>
          {caricaStorico ? (
            <div className="flex h-full items-center justify-center py-20" role="status" aria-label="Caricamento">
              <div className="flex gap-1">
                <span className="h-2 w-2 rounded-full bg-primary/40 animate-pulse-dot" />
                <span className="h-2 w-2 rounded-full bg-primary/40 animate-pulse-dot" />
                <span className="h-2 w-2 rounded-full bg-primary/40 animate-pulse-dot" />
              </div>
            </div>
          ) : messaggi.length === 0 ? (
            <div className="relative flex min-h-[55vh] flex-col items-center justify-center gap-7 overflow-hidden rounded-xl py-8">
              <div className="absolute inset-0 grid-instrument opacity-60" aria-hidden />
              <div className="relative flex flex-col items-center gap-3 text-center">
                <div className="flex items-center gap-2.5">
                  <span className="led led-on text-primary" />
                  <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">Sistema pronto</span>
                </div>
                <h2 className="font-display text-2xl tracking-wide text-foreground">{config?.titolo ?? "Interroga i tuoi dati"}</h2>
                {config?.descrizione && <p className="max-w-sm text-sm text-muted-foreground">{config.descrizione}</p>}
              </div>
              <div className="relative flex w-full max-w-md flex-col gap-2 px-4">
                {(config?.suggerimenti ?? []).map((s, i) => (
                  <button key={s} type="button"
                    onClick={() => {
                      setInput(s);
                      textareaRef.current?.focus();
                    }}
                    className="tick-corners group flex items-center gap-3 rounded-md border bg-card/40 px-4 py-3 text-left text-sm transition-colors hover:border-primary/30 hover:bg-card">
                    <span className="font-mono text-[10px] tabular-nums text-primary/70">{String(i + 1).padStart(2, "0")}</span>
                    <span className="flex-1 text-foreground/85 group-hover:text-foreground">{s}</span>
                    <ChevronRight size={14} className="text-muted-foreground/40 transition-all group-hover:translate-x-0.5 group-hover:text-primary" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4 pb-4" aria-live="polite">
              <AnimatePresence mode="popLayout">
                {messaggi.map((m, i) => {
                  const utente = m.role === "user";
                  if (i === messaggi.length - 1 && m.pending && !m.content) return null;
                  return (
                    <motion.div key={i} initial={ridotto ? undefined : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, ease: "easeOut" }} className={`flex gap-3 ${utente ? "flex-row-reverse" : ""}`}>
                      {utente ? (
                        <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-primary shadow-[0_0_12px_color-mix(in_oklch,var(--primary)_45%,transparent)]">
                          <span className="font-mono text-[10px] font-semibold tracking-wider text-primary-foreground">TU</span>
                        </div>
                      ) : (
                        <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/5">
                          <Bot size={15} className="text-primary" />
                        </div>
                      )}
                      <div className={`max-w-[80%] rounded-md px-4 py-3 text-sm leading-relaxed ${utente
                        ? "console-glow rounded-tr-sm bg-primary text-primary-foreground"
                        : "accent-rail tick-corners rounded-tl-sm border border-border/70 bg-card text-foreground transition-colors hover:border-primary/30"}`}>
                        {utente ? <p className="whitespace-pre-wrap break-words">{m.content}</p> : <Risposta testo={m.content} />}
                      </div>
                    </motion.div>
                  );
                })}
                {strumento && (
                  <motion.div key="strumento" initial={ridotto ? undefined : { opacity: 0 }} animate={{ opacity: 1 }}
                    exit={ridotto ? undefined : { opacity: 0 }} className="flex items-center gap-3 pl-10">
                    <Strumento etichetta={strumento} />
                  </motion.div>
                )}
              </AnimatePresence>

              {inCorso && !strumento && ultimo?.role === "assistant" && (
                <div className="-mt-1 pl-10"><Pensiero indice={pensiero} /></div>
              )}

              {errore && (
                <div className="mt-1 flex items-center gap-2.5 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 pl-1" role="alert">
                  <span className="led text-destructive" />
                  <p className="flex-1 text-sm text-destructive">{errore}</p>
                  <button type="button" onClick={riprova}
                    className={`${BOTTONE} h-7 px-2.5 text-[0.8rem] text-destructive hover:bg-destructive/10`}>
                    <RefreshCw size={14} /> Riprova
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {scorrimentoUtente && messaggi.length > 0 && (
          <button type="button" aria-label="Vai in fondo"
            className="absolute bottom-28 left-1/2 z-10 -translate-x-1/2 rounded-full border border-border/70 bg-card p-2 shadow-[0_0_18px_color-mix(in_oklch,var(--primary)_18%,transparent)] transition-colors hover:border-primary/40 hover:bg-primary/10"
            onClick={() => {
              const el = scrollRef.current;
              if (el) el.scrollTop = el.scrollHeight;
              setScorrimentoUtente(false);
            }}>
            <ChevronDown size={18} className="text-primary" />
          </button>
        )}

        <div className="shrink-0 pb-4 pt-3">
          <div className="console-glow accent-rail rounded-lg border border-border/70 bg-card/40 p-1.5 pl-3.5 transition-colors focus-within:border-primary/40">
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                value={input}
                aria-label="Messaggio"
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    invia();
                  }
                }}
                placeholder="Scrivi un messaggio…"
                disabled={inCorso}
                rows={1}
                className="min-h-[44px] max-h-[160px] w-full resize-none border-0 bg-transparent px-0 py-2 text-base outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                style={{ fontSize: "16px" }}
              />
              {inCorso ? (
                <button type="button" aria-label="Interrompi" onClick={() => abortRef.current?.abort()}
                  className={`${BOTTONE} h-11 w-11 bg-destructive/10 text-destructive hover:bg-destructive/20`}>
                  <Square size={16} fill="currentColor" />
                </button>
              ) : (
                <button type="button" aria-label="Invia" onClick={invia} disabled={!input.trim()}
                  className={`${BOTTONE} h-11 w-11 bg-primary text-primary-foreground shadow-[0_0_14px_color-mix(in_oklch,var(--primary)_40%,transparent)] hover:bg-primary/80`}>
                  <Send size={16} />
                </button>
              )}
            </div>
          </div>
          <p className="mt-2 text-center font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            L&apos;AI può commettere errori · verifica le informazioni importanti
          </p>
        </div>
      </div>
    </div>
  );
}
