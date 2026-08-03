"""Notifiche operative su Discord.

Un solo webhook (`DISCORD_WEBHOOK_URL`). **Non propaga mai eccezioni**: una
notifica rotta non deve far fallire il job che la chiama — sarebbe il colmo che
il meccanismo di allarme causasse il guasto che deve segnalare.

Se il webhook non è configurato, il messaggio finisce nei log e basta: in
sviluppo non serve un canale Discord per far girare la pipeline.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("notify")

LIMITE_DISCORD = 1900  # il limite vero è 2000, teniamo margine per il markdown


def manda(contenuto: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url:
        log.info("Discord disabilitato (DISCORD_WEBHOOK_URL mancante): %s", contenuto)
        return
    try:
        httpx.post(url, json={"content": contenuto[:LIMITE_DISCORD]}, timeout=10)
    except httpx.HTTPError as e:
        log.warning("invio Discord fallito: %s", e)


def allarme_job(prodotto: str, job: str, stato: str,
                entrati: int, usciti: int, errore: str | None = None) -> None:
    """Segnala un job fallito o concluso senza risultati.

    "concluso senza risultati" è uno stato a sé e non un successo: un job che
    riceve dati e non ne produce ha quasi sempre un problema silenzioso a monte.
    Distinguerlo è il motivo per cui questa funzione esiste.
    """
    fallito = stato == "failed"
    icona = "🔴" if fallito else "🟡"
    etichetta = "FALLITO" if fallito else "COMPLETATO SENZA RISULTATI"
    righe = [f"{icona} **[{prodotto}] Job `{job}` {etichetta}**",
             f"in={entrati} out={usciti}"]
    if errore:
        righe.append(f"```{errore}```")
    manda("\n".join(righe))


def riepilogo(prodotto: str, titolo: str, conteggi: dict[str, int]) -> None:
    """Una notifica sola con i totali, invece di N notifiche separate."""
    totale = sum(conteggi.values())
    if totale == 0:
        return
    dettaglio = ", ".join(f"{v} {k}" for k, v in sorted(conteggi.items()) if v)
    manda(f"🔔 **[{prodotto}] {titolo}** — {totale} in totale: {dettaglio}.")
