"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoadingState } from "../ui/stati";

/** Niente di ciò che sta dietro il login si vede finché il cookie non è verificato.
 *
 *  Il controllo è nel browser (export statico: nessun server che reindirizzi prima).
 *  Si sblocca SOLO con `autenticato: true`: qualunque altro esito (401, rete giù,
 *  risposta strana) porta al login, senza far lampeggiare la pagina protetta. Se il
 *  componente sparisce prima della risposta, la risposta viene ignorata. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [verificato, setVerificato] = useState(false);

  useEffect(() => {
    let annullato = false;

    async function controlla() {
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        const corpo = res.ok ? await res.json() : null;
        if (annullato) return;
        if (!corpo?.autenticato) {
          router.replace("/login");
          return;
        }
        setVerificato(true);
      } catch {
        if (!annullato) router.replace("/login");
      }
    }

    void controlla();
    return () => {
      annullato = true;
    };
  }, [router]);

  if (!verificato) {
    return (
      <div className="flex min-h-screen flex-col gap-4 p-6">
        <LoadingState rows={1} height="h-9" className="max-w-xs" />
        <LoadingState rows={3} height="h-28" grid />
        <LoadingState rows={1} height="h-64" />
      </div>
    );
  }

  return <>{children}</>;
}
