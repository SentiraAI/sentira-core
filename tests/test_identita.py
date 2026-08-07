"""Test del modulo identita' (validazione JWT Cloudflare Access + ruolo).

Il valore di questi test non e' coprire righe: e' fissare i quattro comportamenti
da cui dipende la sicurezza dietro Cloudflare Access -- un token con firma
sbagliata non passa, un token scaduto non passa, l'header email da solo (senza
JWT valido) non passa, e un ruolo insufficiente non passa. Ogni test difende uno
di questi; se uno manca, il modulo non e' pronto.
"""

import time

import jwt
import jwt.algorithms as alg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from sentira_core.identita import crea_identita

TEAM = "test"
ISS = f"https://{TEAM}.cloudflareaccess.com"
AUD = "app-test"


def _keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = alg.RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "test-key-1"
    jwk["alg"] = "RS256"
    return priv, jwk


def _jwks(jwk):
    return {"keys": [jwk]}


def _token(priv, *, email="alice@sentira.tech", aud=AUD, iss=ISS,
           exp=None, kid="test-key-1", extra=None):
    payload = {
        "email": email,
        "iss": iss,
        "aud": aud,
        "iat": int(time.time()),
        "exp": exp if exp is not None else int(time.time()) + 3600,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, priv, algorithm="RS256", headers={"kid": kid})


def _app(ruolo_per_email, jwks, *, aud=AUD, gerarchia=None):
    """App di test con una route protetta da require_ruolo('approvatore')."""
    identita = crea_identita(
        team=TEAM, ruolo_per_email=ruolo_per_email, aud=aud,
        gerarchia=gerarchia, _jwks=jwks,
    )
    app = FastAPI()

    @app.get("/api/bozze/approva")
    def approva(email: str = Depends(identita.require_ruolo("approvatore"))):
        return {"email": email}

    return app, identita


# ---- un token valido firma-buota passa ----

def test_jwt_valido_passa_e_ritorna_email():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 200
    assert r.json()["email"] == "alice@sentira.tech"


# ---- firma sbagliata -> 401 ----

def test_jwt_con_firma_sbagliata_rifiutato():
    priv, jwk = _keypair()
    altro_priv, _ = _keypair()  # chiave diversa, stesso kid
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(altro_priv)})
    assert r.status_code == 401


# ---- scaduto -> 401 ----

def test_jwt_scaduto_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion":
                                     _token(priv, exp=int(time.time()) - 10)})
    assert r.status_code == 401


# ---- audience sbagliata -> 401 ----

def test_jwt_con_audience_sbagliata_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv, aud="SBAGLIATA")})
    assert r.status_code == 401


# ---- issuer sbagliato -> 401 ----

def test_jwt_con_issuer_sbagliato_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion":
                                     _token(priv, iss="https://malevolo.cloudflareaccess.com")})
    assert r.status_code == 401


# ---- ruolo corrispondente -> ok ----

def test_ruolo_corrispondente_autorizza():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 200


# ---- ruolo insufficiente -> 403 ----

def test_ruolo_insufficiente_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "lettore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 403


# ---- email non in tabella (lookup None) -> 403 ----

def test_utente_non_registrato_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: None, _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 403


# ---- header email da solo, senza JWT valido -> 401 ----

def test_header_email_senza_jwt_valido_non_basta():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    # solo l'header email, niente JWT
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Authenticated-User-Email": "admin@sentira.tech"})
    assert r.status_code == 401
    # JWT malformato + header email: continua a non bastare
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": "non.e.un.jwt",
                                     "Cf-Access-Authenticated-User-Email": "admin@sentira.tech"})
    assert r.status_code == 401


# ---- gerarchia: ruolo piu' privilegiato passa ----

def test_gerarchia_ruolo_piu_privilegiato_passa():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "admin", _jwks(jwk),
                  gerarchia={"lettore": 1, "approvatore": 2, "admin": 3})
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 200


# ---- senza gerarchia: admin NON passa route approvatore (match esatto) ----

def test_senza_gerarchia_admin_non_passa_approvatore():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "admin", _jwks(jwk))  # gerarchia=None
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 403


# ---- token mancante -> 401 ----

def test_senza_token_rifiutato():
    priv, jwk = _keypair()
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    assert TestClient(app).get("/api/bozze/approva").status_code == 401


# ---- IDENTITA_DEV=1 in dev simula un utente ----

def test_dev_mode_accetta_email_fissa(monkeypatch):
    priv, jwk = _keypair()
    monkeypatch.setenv("IDENTITA_DEV", "1")
    monkeypatch.setenv("IDENTITA_DEV_EMAIL", "dev@sentira.tech")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    r = TestClient(app).get("/api/bozze/approva")  # nessun JWT
    assert r.status_code == 200
    assert r.json()["email"] == "dev@sentira.tech"


# ---- IDENTITA_DEV NON vale in produzione ----

def test_dev_mode_disarmata_in_produzione(monkeypatch):
    priv, jwk = _keypair()
    monkeypatch.setenv("IDENTITA_DEV", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    app, _ = _app(lambda e: "approvatore", _jwks(jwk))
    # senza JWT: il flag dev e' ininfluente, quindi 401
    assert TestClient(app).get("/api/bozze/approva").status_code == 401


# ---- kid sconosciuto nel JWKS -> 401 ----

def test_kid_sconosciuto_rifiutato():
    priv, jwk = _keypair()
    jwk_altro_kid = dict(jwk)
    jwk_altro_kid["kid"] = "un-altro-kid"
    app, _ = _app(lambda e: "approvatore", _jwks(_jwks(jwk_altro_kid)))
    r = TestClient(app).get("/api/bozze/approva",
                            headers={"Cf-Access-Jwt-Assertion": _token(priv)})
    assert r.status_code == 401
