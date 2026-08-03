"""Invio email via Resend + rendering template Jinja2.

- `invia()`: POST a https://api.resend.com/emails con httpx. Supporta
  l'header Idempotency-Key (dedup 24h lato Resend): doppia protezione contro
  invii duplicati, in aggiunta all'idempotenza sul database dell'applicazione.
- `rendi()`: corpo email in testo/markdown con placeholder Jinja2.
- Cap giornaliero (`EMAIL_DAILY_CAP`, default 50).

Se `EMAIL_PROVIDER_API_KEY` o `EMAIL_FROM` mancano: logga "email disabilitata" e
restituisce None. Non solleva — un'applicazione senza email configurata deve
poter girare lo stesso.

## Il contatore giornaliero

Il conteggio va persistito, ma *dove* dipende dallo schema dell'applicazione, ed
è l'unica ragione per cui questo modulo non era estraibile prima. Ora lo si
inietta:

    from sentira_core import emailer
    from . import db

    def _contatore(chiave, incrementa):
        with db.get_session() as s:
            riga = s.get(db.SyncState, chiave)
            attuale = int(riga.value) if riga and riga.value else 0
            if incrementa:
                if riga: riga.value = str(attuale + 1)
                else:    s.add(db.SyncState(key=chiave, value="1"))
                s.commit()
            return attuale

    emailer.usa_contatore(_contatore)

Senza contatore registrato il cap non viene applicato e la cosa viene loggata
una volta sola: meglio inviare senza cap che non inviare per una dipendenza
mancante — ma è giusto che si veda nei log.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Callable

import httpx
import markdown as _md
from jinja2 import Environment, StrictUndefined, TemplateError

log = logging.getLogger("emailer")

RESEND_URL = "https://api.resend.com/emails"

_env = Environment(undefined=StrictUndefined, autoescape=False)

# (chiave, incrementa) -> conteggio attuale
_contatore: Callable[[str, bool], int] | None = None
_avvisato_senza_contatore = False


class EmailError(Exception):
    """Errore di invio o di rendering: mai fallimenti silenziosi."""


def usa_contatore(fn: Callable[[str, bool], int]) -> None:
    """Registra la funzione che persiste il conteggio giornaliero."""
    global _contatore
    _contatore = fn


def rendi(testo: str, variabili: dict) -> str:
    """Rendering Jinja2 del corpo/oggetto email.

    Solleva EmailError se una variabile usata nel template manca: meglio
    scoprirlo qui che spedire a un cliente una email con un buco dentro.
    """
    try:
        return _env.from_string(testo).render(**variabili)
    except TemplateError as e:
        raise EmailError(f"Template non valido: {e}") from e


def _testo_in_html(testo: str) -> str:
    """Testo o markdown → HTML leggibile, con stili sicuri per le email."""
    interno = _md.markdown(testo, extensions=["extra", "nl2br"], output_format="html5")
    return ('<div style="font-family:system-ui,Arial,sans-serif;font-size:15px;'
            'line-height:1.5;color:#1a1a1a;max-width:600px">'
            f'{interno}</div>')


def _sotto_il_cap() -> bool:
    global _avvisato_senza_contatore
    if _contatore is None:
        if not _avvisato_senza_contatore:
            log.warning("Nessun contatore registrato (sentira_core.emailer.usa_contatore): "
                        "il cap giornaliero NON viene applicato.")
            _avvisato_senza_contatore = True
        return True
    cap = int(os.environ.get("EMAIL_DAILY_CAP", "50"))
    chiave = f"email_count_{date.today().isoformat()}"
    if _contatore(chiave, False) >= cap:
        log.warning("Cap giornaliero email raggiunto (%s): invio bloccato", cap)
        return False
    _contatore(chiave, True)
    return True


def _lista(v: str | list[str] | None) -> list[str]:
    """Accetta sia "a@x.it,b@y.it" sia ["a@x.it", "b@y.it"]."""
    if not v:
        return []
    elementi = v.split(",") if isinstance(v, str) else v
    return [x.strip() for x in elementi if x and x.strip()]


def invia(to: str | list[str], oggetto: str, html: str | None = None,
          testo: str | None = None, idempotency_key: str | None = None,
          cc: str | list[str] | None = None) -> str | None:
    """Invia una email via Resend. Ritorna l'id Resend, o None se disabilitata.

    `idempotency_key`: stessa chiave entro 24h → Resend non duplica l'invio.
    """
    api_key = os.environ.get("EMAIL_PROVIDER_API_KEY", "")
    mittente = os.environ.get("EMAIL_FROM", "")
    destinatari = _lista(to)

    if not api_key or not mittente:
        log.info("email disabilitata (EMAIL_PROVIDER_API_KEY o EMAIL_FROM mancante): "
                 "to=%s subject=%r", destinatari, oggetto)
        return None
    if not destinatari:
        log.info("email saltata: nessun destinatario. subject=%r", oggetto)
        return None
    if html is None:
        html = _testo_in_html(testo or "")
    if not _sotto_il_cap():
        raise EmailError("Cap giornaliero email raggiunto: invio bloccato")

    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:256]

    payload = {"from": mittente, "to": destinatari, "subject": oggetto, "html": html}
    if testo:
        payload["text"] = testo
    if _lista(cc):
        payload["cc"] = _lista(cc)

    try:
        resp = httpx.post(RESEND_URL, json=payload, headers=headers, timeout=30)
    except httpx.HTTPError as e:
        log.error("Errore di rete verso Resend: %s", e)
        raise EmailError(f"Errore di rete verso Resend: {e}") from e

    if resp.status_code >= 400:
        log.error("Resend ha risposto %s: %s", resp.status_code, resp.text)
        raise EmailError(f"Resend {resp.status_code}: {resp.text}")

    email_id = resp.json().get("id")
    log.info("Email inviata: id=%s to=%s subject=%r", email_id, destinatari, oggetto)
    return email_id


# ── Compatibilità con i nomi usati finora nei due progetti ──────────────────
# Le applicazioni chiamano send_html_email()/render_template(): questi alias
# rendono la migrazione un cambio di import, non una riscrittura dei chiamanti.
send_html_email = invia
render_template = rendi
