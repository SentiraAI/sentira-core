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
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("web")


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
