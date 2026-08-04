"""Auth minima a password singola, con cookie di sessione firmato HMAC.

Il modello è deliberatamente povero: una dashboard per un cliente, una password,
nessun utente, nessun database delle sessioni. Il token è autoconsistente e
firmato, quindi non serve tenere stato lato server.

Il segreto di firma è derivato dalla password: cambiare `DASHBOARD_PASSWORD`
invalida da sola tutte le sessioni esistenti. È il motivo per cui non esiste un
comando "logout globale" — non serve.

Uso, in `src/auth.py` dell'applicazione:

    from sentira_core.auth import crea_auth

    auth = crea_auth(nome_cookie="lh-session", giorni=30, ambito="lead-hunter")
    router = auth.router
    require_auth = auth.require_auth

Le tre differenze fra un progetto e l'altro erano esattamente queste — nome del
cookie, durata, stringa di ambito nella derivazione del segreto — e sono ora
parametri invece di 112 righe copiate.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

log = logging.getLogger("auth")

TENTATIVI_MAX = 5      # per IP
FINESTRA_SECONDI = 60


class LoginIn(BaseModel):
    password: str


@dataclass
class Auth:
    router: APIRouter
    require_auth: object
    make_token: object
    check_token: object
    abilitata: object
    # Il dizionario dei tentativi per IP, esposto di proposito: i test del rate
    # limit devono poterlo azzerare fra un caso e l'altro, altrimenti il quinto
    # test fallisce per colpa del quarto.
    tentativi: dict


def crea_auth(*, nome_cookie: str, giorni: int, ambito: str) -> Auth:
    """Costruisce router e dipendenza di autenticazione per un'applicazione.

    `ambito` entra nella derivazione del segreto: due applicazioni con la stessa
    password non devono accettare i reciproci cookie.
    """
    ttl = giorni * 24 * 60 * 60
    router = APIRouter()
    tentativi: dict[str, list[float]] = {}

    def _segreto() -> bytes:
        base = os.environ.get("SESSION_SECRET") or os.environ.get("DASHBOARD_PASSWORD", "")
        return hashlib.sha256(f"{ambito}-session:{base}".encode()).digest()

    def _firma(payload: str) -> str:
        return hmac.new(_segreto(), payload.encode(), hashlib.sha256).hexdigest()

    def make_token() -> str:
        payload = f"ok:{int(time.time()) + ttl}"
        return f"{payload}:{_firma(payload)}"

    def check_token(token: str | None) -> bool:
        if not token:
            return False
        try:
            prefisso, scadenza, firma = token.rsplit(":", 2)
        except ValueError:
            return False
        if not hmac.compare_digest(firma, _firma(f"{prefisso}:{scadenza}")):
            return False
        try:
            return int(scadenza) > time.time()
        except ValueError:
            return False

    def abilitata() -> bool:
        return bool(os.environ.get("DASHBOARD_PASSWORD"))

    def require_auth(request: Request):
        """Dipendenza FastAPI per proteggere gli endpoint /api/*."""
        if not abilitata():
            return  # sviluppo: nessuna password configurata
        if not check_token(request.cookies.get(nome_cookie)):
            raise HTTPException(401, detail="non autenticato")

    def _troppi_tentativi(ip: str) -> bool:
        ora = time.time()
        finestra = [t for t in tentativi.get(ip, []) if ora - t < FINESTRA_SECONDI]
        tentativi[ip] = finestra
        if len(finestra) >= TENTATIVI_MAX:
            return True
        finestra.append(ora)
        return False

    @router.post("/api/auth/login")
    def login(body: LoginIn, request: Request, response: Response):
        if not abilitata():
            log.warning("Login chiamato ma DASHBOARD_PASSWORD non è impostata")
            return {"ok": True, "detail": "auth disattivata (sviluppo)"}
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
        if _troppi_tentativi(ip):
            raise HTTPException(429, detail="troppi tentativi, riprova tra un minuto")
        # encode() su entrambi: compare_digest con due str solleva TypeError se
        # uno contiene caratteri non ASCII, e una password con un accento è
        # perfettamente legittima. Confrontare byte evita l'errore 500.
        atteso = os.environ.get("DASHBOARD_PASSWORD", "")
        if not hmac.compare_digest(body.password.encode(), atteso.encode()):
            raise HTTPException(401, detail="password errata")
        response.set_cookie(nome_cookie, make_token(), max_age=ttl,
                            httponly=True, samesite="lax",
                            secure=os.environ.get("COOKIE_SECURE", "1") == "1")
        return {"ok": True}

    @router.post("/api/auth/logout")
    def logout(response: Response):
        response.delete_cookie(nome_cookie)
        return {"ok": True}

    @router.get("/api/auth/me")
    def me(request: Request):
        if not abilitata():
            return {"autenticato": True, "auth_disattivata": True}
        return {"autenticato": check_token(request.cookies.get(nome_cookie))}

    return Auth(router=router, require_auth=require_auth, make_token=make_token,
                check_token=check_token, abilitata=abilitata, tentativi=tentativi)
