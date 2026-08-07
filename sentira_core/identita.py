"""Identita' via Cloudflare Access: validazione JWT + ruolo.

Quando Access e' davanti a un'app, l'identita' della persona arriva nel JWT
`Cf-Access-Jwt-Assertion`. Questo modulo valida la firma contro il JWKS pubblico
di Cloudflare, estrae l'email, e offre una dipendenza `require_ruolo` che l'app
usa per proteggere le route per ruolo.

Perche' il JWT va validato davvero
----------------------------------
Access manda anche l'header `Cf-Access-Authenticated-User-Email`, leggibile ma
spoofabile: chiunque possa raggiungere l'origine con una richiesta forgiata lo
imposta a piacere. Le app Sentira non hanno porte pubbliche (dietro tunnel), ma
validare la firma contro il JWKS pubblico costa ~30 righe e toglie l'unica
assunzione su cui non vale la pena scommettere. L'header email da solo non e'
mai fonte di verita': lo si legge solo DOPO che il JWT ha validato.

Cosa resta nell'app
-------------------
Questo modulo valida il token ed estrae l'email. Il mapping email -> ruolo sta
nella tabella `utenti` dell'app (vedi il prompt 13): il modulo lo ignora e chiama
una funzione `ruolo_per_email(email) -> str | None` fornita dall'app. Cosi' non
conosce lo schema del DB di nessun cliente e non importa SQLAlchemy.

Uso
---
    from sentira_core.identita import crea_identita

    identita = crea_identita(
        team="sentira",                 # per iss/jwks/log
        ruolo_per_email=mio_lookup,     # funzione dell'app: email -> ruolo
        aud="uuid-dell-app-access",     # audience dell'app Access (opz. ma consigliato)
        gerarchia={"lettore": 1, "approvatore": 2, "admin": 3},  # opzionale
    )
    require_ruolo = identita.require_ruolo

    @app.get("/api/bozze/approva")
    def approva(email: str = Depends(require_ruolo("approvatore"))):
        ...

Modalita' dev
-------------
Senza Access davanti (sviluppo locale) si imposta `IDENTITA_DEV=1` e
`IDENTITA_DEV_EMAIL=chi@sentira.tech`: ogni richiesta e' accettata con quell'email
fissa, senza JWT. Il flag e' ininfluente in produzione: `ENVIRONMENT=production`
lo disarma, qualunque sia il suo valore.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

import httpx
import jwt
from fastapi import HTTPException, Request

log = logging.getLogger("identita")

# Header inoltrati da Cloudflare Access all'origine.
JWT_HEADER = "Cf-Access-Jwt-Assertion"
EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"

JWKS_TTL = 3600  # 1h: rotazione delle chiavi CF e' rara, rifetchare ogni req e' latenza inutile


@dataclass
class Identita:
    """Prodotto di `crea_identita`. `.require_ruolo` protegge le route, `.verifica_token`
    ritorna l'email di un token gia' validato (per l'app che vuole sapere 'chi e'')."""

    require_ruolo: Callable[[str], Callable]
    verifica_token: Callable[[Optional[str]], str]


def crea_identita(
    *,
    team: str,
    ruolo_per_email: Callable[[str], Optional[str]],
    aud: Optional[str] = None,
    gerarchia: Optional[dict[str, int]] = None,
    _jwks: Optional[dict] = None,
    jwks_ttl: int = JWKS_TTL,
) -> Identita:
    """Costruisce la dipendenza di identita' Cloudflare Access per un'app.

    `team` entra in issuer (`https://<team>.cloudflareaccess.com`) e nell'URL del
    JWKS. `aud` e' l'audience dell'app Access: se passato, il `aud` del JWT deve
    combaciare (consigliato in produzione); se omesso, la verifica audience e'
    saltata. `gerarchia` opzionale mappa ruolo -> livello: un ruolo passa se e'
    uguale o piu' privilegiato dell'atteso; senza gerarchia vale il match esatto.

    `_jwks` e' un JWKS gia' caricato (per i test): bypassa il fetch HTTP.
    `ruolo_per_email` e' la funzione dell'app che conosce la sua tabella `utenti`.
    """
    iss = f"https://{team}.cloudflareaccess.com"
    jwks_url = f"{iss}/cdn-cgi/access/certs"

    # Cache delle chiavi: {"kid": chiave_pubblica} + scadenza.
    stato: dict = {"chiavi": {}, "scadenza": 0.0}

    def _chiavi_dalla_jwks(jwks: dict) -> dict:
        out: dict = {}
        for jwk in jwks.get("keys", []):
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                if jwk.get("kty") == "RSA":
                    out[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                elif jwk.get("kty") == "EC":
                    out[kid] = jwt.algorithms.ECAlgorithm.from_jwk(jwk)
            except (ValueError, KeyError):
                continue  # chiave malformata: la salto, non faccio cadere tutto
        return out

    def _carica_chiavi(force: bool = False) -> dict:
        # JWKS iniettato (test): niente da fetchare, ricarica solo se forzato.
        if _jwks is not None:
            if force or not stato["chiavi"]:
                stato["chiavi"] = _chiavi_dalla_jwks(_jwks)
            return stato["chiavi"]
        # Cache ancora valida?
        if stato["chiavi"] and stato["scadenza"] > time.time() and not force:
            return stato["chiavi"]
        try:
            resp = httpx.get(jwks_url, timeout=10)
            resp.raise_for_status()
            jwks = resp.json()
        except Exception as exc:  # httpx.HTTPError, JSON malformato, ecc.
            log.error("JWKS %s non recuperabile: %s", jwks_url, exc)
            # Meglio una cache scaduta che niente: i token ancora validi passano.
            if stato["chiavi"]:
                return stato["chiavi"]
            raise HTTPException(503, detail="servizio di identita' non disponibile")
        stato["chiavi"] = _chiavi_dalla_jwks(jwks)
        stato["scadenza"] = time.time() + jwks_ttl
        return stato["chiavi"]

    def _decode(token: str, chiavi: dict) -> dict:
        header = jwt.get_unverified_header(token)
        key = chiavi.get(header.get("kid"))
        if key is None:
            raise KeyError("kid")  # segnala: rifetch (rotazione)
        alg = header.get("alg", "RS256")
        opzioni = {} if aud else {"verify_aud": False}
        return jwt.decode(token, key, algorithms=[alg], audience=aud,
                          issuer=iss, options=opzioni)

    def verifica_token(token: Optional[str]) -> str:
        """Valida il JWT e ritorna l'email. HTTPException(401) se invalido/assente."""
        if not token:
            raise HTTPException(401, detail="token di identita' mancante")
        # Due tentativi: il secondo rifetcha il JWKS, per la rotazione delle
        # chiavi in cui il kid e' nuovo o la firma non verifica con chiavi vecchie.
        for tentativo in (1, 2):
            try:
                payload = _decode(token, _carica_chiavi(force=tentativo == 2 and _jwks is None))
                return payload.get("email")
            except KeyError:
                if tentativo == 1 and _jwks is None:
                    continue
                raise HTTPException(401, detail="chiave di firma non trovata")
            except jwt.InvalidSignatureError:
                if tentativo == 1 and _jwks is None:
                    continue
                raise HTTPException(401, detail="firma del token non valida")
            except jwt.ExpiredSignatureError:
                raise HTTPException(401, detail="token scaduto")
            except (jwt.InvalidAudienceError, jwt.InvalidIssuerError):
                raise HTTPException(401, detail="audience o issuer non validi")
            except jwt.DecodeError:
                raise HTTPException(401, detail="token malformato")
            except jwt.PyJWTError:
                raise HTTPException(401, detail="token non valido")
        # Irraggiungibile: il ciclo o ritorna o solleva. Qui per mypy.
        raise HTTPException(401, detail="token non valido")

    def _dev_attivo() -> bool:
        # IDENTITA_DEV non vale MA in produzione: ENVIRONMENT disarma il flag.
        return os.environ.get("IDENTITA_DEV") == "1" and os.environ.get("ENVIRONMENT") != "production"

    def _email_dalla_request(request: Request) -> str:
        """Dev-mode o JWT validato. Mai l'header email da solo."""
        if _dev_attivo():
            return os.environ.get("IDENTITA_DEV_EMAIL", "dev@sentira.tech")
        email = verifica_token(request.headers.get(JWT_HEADER))
        # Fallback all'header SOLO dopo JWT valido: copre i token CF senza claim email.
        return email or request.headers.get(EMAIL_HEADER, "")

    def _ruolo_sufficiente(ruolo: Optional[str], atteso: str) -> bool:
        if ruolo == atteso:
            return True
        if gerarchia and ruolo in gerarchia and atteso in gerarchia:
            return gerarchia[ruolo] >= gerarchia[atteso]
        return False

    def require_ruolo(ruolo_atteso: str):
        def _dipendenza(request: Request) -> str:
            email = _email_dalla_request(request)
            ruolo = ruolo_per_email(email)
            if ruolo is None:
                raise HTTPException(403, detail="utente non registrato")
            if not _ruolo_sufficiente(ruolo, ruolo_atteso):
                raise HTTPException(403, detail="ruolo insufficiente")
            return email
        return _dipendenza

    return Identita(require_ruolo=require_ruolo, verifica_token=verifica_token)
