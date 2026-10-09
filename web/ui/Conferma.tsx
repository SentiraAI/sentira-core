"use client";

import { useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "./button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./dialog";

/** La domanda prima di un'azione che non si annulla, al posto di `window.confirm`.
 *  Se `onConferma` restituisce una promessa il bottone gira finché non finisce,
 *  poi il dialog si chiude da solo. */
export function Conferma({
  open, onOpenChange, titolo, descrizione, etichetta = "Conferma", distruttiva = false, onConferma,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titolo: ReactNode;
  descrizione?: ReactNode;
  /** testo del bottone di conferma; può avere un'icona */
  etichetta?: ReactNode;
  distruttiva?: boolean;
  onConferma: () => unknown;
}) {
  const [inCorso, setInCorso] = useState(false);

  async function conferma() {
    setInCorso(true);
    try {
      await onConferma();
    } finally {
      setInCorso(false);
      onOpenChange(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!inCorso) onOpenChange(o); }}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{titolo}</DialogTitle>
          {descrizione && <DialogDescription>{descrizione}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" disabled={inCorso} onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button variant={distruttiva ? "destructive" : "default"} disabled={inCorso} onClick={conferma} className="gap-1.5">
            {inCorso && <Loader2 size={14} className="animate-spin" />}
            {etichetta}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
