"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "../ui/button";

/** Ultima difesa contro lo schermo bianco (app/error.tsx). Mai uno stack trace. */
export function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-4 text-center">
      <div>
        <AlertTriangle size={48} className="mx-auto mb-4 text-warning" />
        <h1 className="text-2xl font-bold">Qualcosa è andato storto</h1>
        <p className="mt-2 text-muted-foreground">
          Si è verificato un errore imprevisto. Prova a ricaricare la pagina.
        </p>
        <Button onClick={reset} className="mt-6">
          Riprova
        </Button>
        {error.digest && <p className="mt-4 text-xs text-muted-foreground">ID: {error.digest}</p>}
      </div>
    </div>
  );
}
