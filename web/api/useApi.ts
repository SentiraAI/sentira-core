"use client";

import { useCallback, useEffect, useState } from "react";
import { getJson, messaggio } from "./cliente";

/** GET di `url` al montaggio e a ogni cambio di `url`; `refetch()` lo ripete.
 *  Passa dal client comune: 401 → login, errori già in italiano. La richiesta
 *  precedente si annulla, così una risposta lenta non sovrascrive una più nuova. */
export function useApi<T>(url: string): { data: T | null; error: string | null; refetch: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [giro, setGiro] = useState(0);
  // l'errore vale solo per la richiesta che l'ha prodotto: un refetch o un altro url lo nascondono
  const [errore, setErrore] = useState<{ chiave: string; testo: string } | null>(null);
  const chiave = `${giro}:${url}`;

  useEffect(() => {
    const ctrl = new AbortController();
    getJson<T>(url, { signal: ctrl.signal })
      .then((d) => {
        setData(d);
        setErrore(null);
      })
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        setErrore({ chiave: `${giro}:${url}`, testo: messaggio(e, "Server non raggiungibile") });
        setData(null);
      });
    return () => ctrl.abort();
  }, [url, giro]);

  const refetch = useCallback(() => setGiro((g) => g + 1), []);
  return { data, error: errore?.chiave === chiave ? errore.testo : null, refetch };
}
