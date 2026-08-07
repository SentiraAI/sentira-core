"""Notifica le eccezioni non gestite, con deduplica.

Cattura le eccezioni non gestite (500 inaspettati) delle route FastAPI e
notifica via Discord con un webhook dedicato, separato da `notify.py`. Le
`HTTPException` non arrivano qui: Starlette le gestisce prima che risalgano
al middleware, quindi il filtro "solo 5xx inaspettati" è gratis, non va
scritto a mano.

Deduplica per (tipo eccezione, file dove è esplosa): il primo colpo manda un
messaggio Discord, i successivi nella stessa finestra aggiornano lo stesso
messaggio con un contatore (PATCH sul webhook, niente spam di messaggi
nuovi). ponytail: dedup in memoria (dict), persa al riavvio — va bene per
non-spammare Discord, non è uno storico. Multi-worker perderebbe la
deduplica fra processi: non è il caso di questi deploy (un solo container).

Uso:

    from sentira_core.errorreport import crea_errorreport
    report = crea_errorreport(tenant="giallo")
    app.middleware("http")(report.middleware)
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from dataclasses import dataclass

import httpx
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("errorreport")

FINESTRA_SECONDI = 15 * 60
LIMITE_DISCORD = 1900
RIGHE_TRACEBACK = 20


@dataclass
class _Voce:
    message_id: str | None
    scade: float
    extra: int = 0


class ErrorReport:
    def __init__(self, tenant: str, webhook_url: str, dry_run: bool = False):
        self.tenant = tenant
        self.webhook_url = webhook_url
        self.dry_run = dry_run
        self._visti: dict[tuple[str, str], _Voce] = {}

    def _chiave(self, exc: BaseException) -> tuple[str, str]:
        tb = traceback.extract_tb(exc.__traceback__)
        file_rilevante = tb[-1].filename if tb else "?"
        return (type(exc).__name__, file_rilevante)

    def _messaggio(self, exc: BaseException, metodo: str, path: str) -> str:
        # Solo tipo + traceback: niente body, niente header. Un parametro
        # cliente puo' finire nel messaggio dell'eccezione, ma mai qui il
        # payload della request (dove finiscono i dati sensibili veri).
        titolo = f"🔴 **[{self.tenant}] {type(exc).__name__} in {metodo} {path}**"
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        righe = "\n".join(stack.splitlines()[-RIGHE_TRACEBACK:])
        corpo = f"```{righe}```"
        return f"{titolo}\n{corpo}"[:LIMITE_DISCORD]

    def _invia(self, contenuto: str) -> str | None:
        if self.dry_run:
            log.info("errorreport (dry-run): %s", contenuto)
            return None
        if not self.webhook_url:
            log.info("errorreport (webhook assente): %s", contenuto)
            return None
        try:
            r = httpx.post(f"{self.webhook_url}?wait=true",
                           json={"content": contenuto}, timeout=10)
            return r.json().get("id")
        except httpx.HTTPError as e:
            log.warning("invio errorreport fallito: %s", e)
            return None

    def _aggiorna(self, message_id: str, contenuto: str) -> None:
        if self.dry_run or not self.webhook_url:
            return
        try:
            httpx.patch(f"{self.webhook_url}/messages/{message_id}",
                       json={"content": contenuto}, timeout=10)
        except httpx.HTTPError as e:
            log.warning("aggiornamento errorreport fallito: %s", e)

    def registra(self, exc: BaseException, metodo: str, path: str) -> None:
        chiave = self._chiave(exc)
        ora = time.monotonic()
        voce = self._visti.get(chiave)
        if voce and ora < voce.scade:
            voce.extra += 1
            if voce.message_id:
                base = self._messaggio(exc, metodo, path)
                self._aggiorna(voce.message_id,
                               f"{base}\n_+{voce.extra} altre in questa finestra_")
            return
        contenuto = self._messaggio(exc, metodo, path)
        message_id = self._invia(contenuto)
        self._visti[chiave] = _Voce(message_id=message_id, scade=ora + FINESTRA_SECONDI)

    async def middleware(self, request, call_next):
        try:
            return await call_next(request)
        except StarletteHTTPException:
            raise
        except Exception as exc:
            self.registra(exc, request.method, request.url.path)
            raise


def crea_errorreport(tenant: str, webhook_from_env: bool = True,
                     dry_run: bool | None = None) -> ErrorReport:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL_ERRORI", "") if webhook_from_env else ""
    if dry_run is None:
        dry_run = os.environ.get("ERROR_REPORT_DRY_RUN", "") == "1"
    return ErrorReport(tenant=tenant, webhook_url=webhook_url, dry_run=dry_run)
