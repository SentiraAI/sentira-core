"""Serve il frontend (export statico di Next.js) dalla stessa app FastAPI.

    from sentira_core.web import monta_frontend
    ...                       # tutte le route /api prima
    monta_frontend(app)       # per ultima: è un catch-all

Ordine di risoluzione di `/x`: il file `x`, poi `x.html`, poi `x/index.html`,
poi `404.html` (con stato 404), infine `index.html`. Una `/api/...` che non
esiste risponde 404 JSON, non la pagina 404: il frontend si aspetta JSON.

Path traversal: `/%2e%2e/data/app.db` arriva qui come `../data/app.db`. Ogni
percorso si risolve e deve restare dentro la cartella, altrimenti è 404. In
lead-hunter mancava: col container giusto si scaricava il database.

    from sentira_core.web import proteggi
    proteggi(app)             # subito dopo FastAPI(...): header + CSRF
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("web")

# Next.js (export statico) mette script inline per l'idratazione: 'unsafe-inline'
# serve, il resto resta chiuso. Nessuna risorsa esterna.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")
_METODI_SICURI = {"GET", "HEAD", "OPTIONS"}


def proteggi(app: FastAPI, csp: str = CSP) -> None:
    """Header di sicurezza su ogni risposta, e CSRF via Fetch Metadata.

    Il cookie di sessione è SameSite=Lax: ferma i siti esterni, non gli altri
    sottodomini di sentira.tech (stesso "site"). Un browser dichiara sempre da
    dove parte la richiesta in Sec-Fetch-Site: una scrittura che non nasce da
    questa stessa origine si rifiuta. Client senza l'header (CLI, test, webhook)
    non sono browser e non portano il cookie di qualcun altro."""
    header = {
        "Content-Security-Policy": csp,
        "Strict-Transport-Security": "max-age=31536000",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }

    @app.middleware("http")
    async def _sicurezza(request: Request, call_next):
        if (request.method not in _METODI_SICURI
                and request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none")):
            risposta = JSONResponse({"detail": "richiesta da un'altra origine rifiutata"}, 403)
        else:
            risposta = await call_next(request)
        for nome, valore in header.items():
            risposta.headers.setdefault(nome, valore)
        if request.url.path.startswith("/api/"):
            risposta.headers.setdefault("Cache-Control", "no-store")  # dati dei clienti
        return risposta


def _dentro(radice: Path, relativo: str) -> Path | None:
    """Il percorso risolto, o None se esce dalla cartella o non è valido."""
    try:
        percorso = (radice / relativo).resolve()
    except (OSError, ValueError):  # byte nullo, loop di symlink
        return None
    return percorso if percorso.is_relative_to(radice) else None


def monta_frontend(app: FastAPI, cartella: str | None = None) -> None:
    """Monta l'export in `cartella` (default STATIC_DIR, poi `static`). Se la
    cartella non c'è (sviluppo, test) non monta nulla."""
    cartella = cartella or os.environ.get("STATIC_DIR") or "static"
    if not os.path.isdir(cartella):
        log.info("frontend non montato: %s non esiste", cartella)
        return
    radice = Path(cartella).resolve()
    if (radice / "_next").is_dir():
        # JS/CSS con MIME type e cache gestiti da StaticFiles
        app.mount("/_next", StaticFiles(directory=radice / "_next"), name="next_static")

    @app.api_route("/{percorso:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend(percorso: str):
        pulito = percorso.lstrip("/")
        if pulito == "api" or pulito.startswith(("api/", "_next/")):
            raise HTTPException(404)
        if pulito and _dentro(radice, pulito) is None:
            raise HTTPException(404)  # tentativo di uscire dalla cartella
        candidati = (pulito, f"{pulito}.html", f"{pulito}/index.html") if pulito else ("index.html",)
        for candidato in candidati:
            trovato = _dentro(radice, candidato)
            if trovato and trovato.is_file():
                return FileResponse(trovato)
        if (radice / "404.html").is_file():
            return FileResponse(radice / "404.html", status_code=404)
        return FileResponse(radice / "index.html")
