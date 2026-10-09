"use client";

import { useEffect, useState } from "react";
import { getJson } from "../api/cliente";

/** Un contatore del menu (bozze da rivedere, lead nuovi…): `path` letto subito, poi
 *  ogni `ms` e quando la scheda torna in primo piano. Gli errori sono muti: un badge
 *  che manca è meglio di un allarme rosso accanto al menu. */
export function useConteggio<T>(path: string, ms = 30000): T | null {
  const [dato, setDato] = useState<T | null>(null);

  useEffect(() => {
    let annullato = false;
    async function carica() {
      try {
        const d = await getJson<T>(path);
        if (!annullato) setDato(d);
      } catch {
        /* il 401 porta già al login; il resto non vale un avviso */
      }
    }
    void carica();
    const timer = setInterval(() => void carica(), ms);
    const alRitorno = () => {
      if (document.visibilityState === "visible") void carica();
    };
    document.addEventListener("visibilitychange", alRitorno);
    return () => {
      annullato = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", alRitorno);
    };
  }, [path, ms]);

  return dato;
}
