"""Test dell'auth condivisa.

Il valore di questi test non è coprire righe: è fissare le tre proprietà da cui
dipende la sicurezza di ogni dashboard Sentira — un token non firmato non passa,
un token scaduto non passa, e il token di un prodotto non vale per un altro.
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentira_core.auth import crea_auth


@pytest.fixture
def app_e_auth(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "segreta-per-i-test")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    auth = crea_auth(nome_cookie="test-session", giorni=1, ambito="prodotto-a")
    app = FastAPI()
    app.include_router(auth.router)
    return app, auth


def test_login_corretto_imposta_il_cookie(app_e_auth):
    app, _ = app_e_auth
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"password": "segreta-per-i-test"})
    assert r.status_code == 200
    assert "test-session" in r.cookies
    assert c.get("/api/auth/me").json()["autenticato"] is True


def test_password_sbagliata_rifiutata(app_e_auth):
    app, _ = app_e_auth
    r = TestClient(app).post("/api/auth/login", json={"password": "sbagliata"})
    assert r.status_code == 401


def test_password_con_accento_non_causa_errore_500(app_e_auth, monkeypatch):
    """compare_digest su due `str` solleva TypeError se non sono ASCII.

    Una password con un accento è legittima; prima dell'encode() esplicito
    questo caso produceva un 500 invece di un 401 — e un 500 su un login è
    anche un canale di informazione per chi prova a indovinare.
    """
    app, _ = app_e_auth
    monkeypatch.setenv("DASHBOARD_PASSWORD", "città-però-così")
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"password": "sbagliatà"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "città-però-così"}).status_code == 200


def test_token_manomesso_rifiutato(app_e_auth):
    _, auth = app_e_auth
    token = auth.make_token()
    assert auth.check_token(token) is True
    corpo, firma = token.rsplit(":", 1)
    assert auth.check_token(f"{corpo}:{'0' * len(firma)}") is False


def test_token_scaduto_rifiutato(app_e_auth, monkeypatch):
    import sentira_core.auth as modulo
    _, auth = app_e_auth
    token = auth.make_token()
    assert auth.check_token(token) is True
    # avanti di due giorni: il token dura un giorno
    adesso = time.time()
    monkeypatch.setattr(modulo.time, "time", lambda: adesso + 2 * 24 * 3600)
    assert auth.check_token(token) is False


def test_token_di_un_prodotto_non_vale_per_un_altro(monkeypatch):
    """Due prodotti con la STESSA password non devono accettare i reciproci cookie."""
    monkeypatch.setenv("DASHBOARD_PASSWORD", "identica")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    a = crea_auth(nome_cookie="s", giorni=1, ambito="lead-hunter")
    b = crea_auth(nome_cookie="s", giorni=1, ambito="dropbox-agent")
    assert b.check_token(a.make_token()) is False


def test_cambiare_password_invalida_le_sessioni(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "prima")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    auth = crea_auth(nome_cookie="s", giorni=1, ambito="x")
    token = auth.make_token()
    assert auth.check_token(token) is True
    monkeypatch.setenv("DASHBOARD_PASSWORD", "dopo")
    assert auth.check_token(token) is False


def test_senza_password_auth_disattivata(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    auth = crea_auth(nome_cookie="s", giorni=1, ambito="x")
    assert auth.abilitata() is False
    app = FastAPI()
    app.include_router(auth.router)
    assert TestClient(app).get("/api/auth/me").json()["auth_disattivata"] is True


def test_rate_limit_dopo_cinque_tentativi(app_e_auth):
    app, _ = app_e_auth
    c = TestClient(app)
    esiti = [c.post("/api/auth/login", json={"password": "no"}).status_code
             for _ in range(6)]
    assert esiti[:5] == [401] * 5
    assert esiti[5] == 429


def test_token_malformato_non_esplode(app_e_auth):
    _, auth = app_e_auth
    for cattivo in (None, "", "senzadueppunti", "a:b:c:d", "ok:nonunnumero:ff"):
        assert auth.check_token(cattivo) is False


def test_i_tentativi_sono_azzerabili_dai_test(app_e_auth):
    """Il dizionario dei tentativi e' esposto apposta: senza, il test del rate
    limit contaminerebbe quelli successivi."""
    app, auth = app_e_auth
    c = TestClient(app)
    for _ in range(6):
        c.post("/api/auth/login", json={"password": "no"})
    auth.tentativi.clear()
    assert c.post("/api/auth/login", json={"password": "segreta-per-i-test"}).status_code == 200
