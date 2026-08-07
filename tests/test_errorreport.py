"""Test dell'handler di error tracking (dedup + notifica Discord)."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from sentira_core import errorreport


class _Risposta:
    def __init__(self, message_id="m1"):
        self._message_id = message_id

    def json(self):
        return {"id": self._message_id}


@pytest.fixture
def catturate(monkeypatch):
    """Cattura POST (nuovi messaggi) e PATCH (aggiornamenti contatore)."""
    inviate, aggiornate = [], []
    monkeypatch.setattr(errorreport.httpx, "post",
                        lambda url, json=None, timeout=None: (inviate.append(json["content"]), _Risposta())[1])
    monkeypatch.setattr(errorreport.httpx, "patch",
                        lambda url, json=None, timeout=None: aggiornate.append(json["content"]))
    return inviate, aggiornate


@pytest.fixture
def app(catturate):
    report = errorreport.crea_errorreport(tenant="test", webhook_from_env=False)
    report.webhook_url = "https://discord.test/webhook"  # forza l'invio nei test

    api = FastAPI()
    api.middleware("http")(report.middleware)

    @api.get("/boom")
    def boom():
        raise ValueError("die")

    @api.get("/deliberata")
    def deliberata():
        raise HTTPException(500, "controllata")

    @api.get("/bad")
    def bad():
        return JSONResponse(status_code=400, content={"detail": "client error"})

    @api.post("/pii")
    async def pii(payload: dict):
        raise RuntimeError("errore interno")  # il body (con la PII) non viene mai letto qui

    api.state.report = report
    return TestClient(api, raise_server_exceptions=False)


def test_eccezione_non_gestita_notifica(app, catturate):
    inviate, _ = catturate
    r = app.get("/boom")
    assert r.status_code == 500
    assert len(inviate) == 1
    assert "ValueError" in inviate[0] and "test" in inviate[0]


def test_4xx_non_notifica(app, catturate):
    inviate, aggiornate = catturate
    r = app.get("/bad")
    assert r.status_code == 400
    assert inviate == [] and aggiornate == []


def test_httpexception_deliberata_non_notifica(app, catturate):
    inviate, aggiornate = catturate
    r = app.get("/deliberata")
    assert r.status_code == 500
    assert inviate == [] and aggiornate == []


def test_stessa_eccezione_10_volte_una_notifica_piu_contatore(app, catturate):
    inviate, aggiornate = catturate
    for _ in range(10):
        app.get("/boom")
    assert len(inviate) == 1
    assert len(aggiornate) == 9
    assert "+9" in aggiornate[-1]


def test_finestra_scaduta_nuova_notifica(app, catturate, monkeypatch):
    inviate, _ = catturate
    orologio = [0.0]
    monkeypatch.setattr(errorreport.time, "monotonic", lambda: orologio[0])

    app.get("/boom")
    orologio[0] += errorreport.FINESTRA_SECONDI + 1
    app.get("/boom")

    assert len(inviate) == 2


def test_dry_run_non_manda(catturate):
    inviate, aggiornate = catturate
    report = errorreport.crea_errorreport(tenant="test", webhook_from_env=False, dry_run=True)
    report.webhook_url = "https://discord.test/webhook"

    api = FastAPI()
    api.middleware("http")(report.middleware)

    @api.get("/boom")
    def boom():
        raise ValueError("die")

    TestClient(api, raise_server_exceptions=False).get("/boom")
    assert inviate == [] and aggiornate == []


def test_pii_nel_body_non_appare_nella_notifica(app, catturate):
    inviate, _ = catturate
    app.post("/pii", json={"codice_fiscale": "RSSMRA80A01H501U"})
    assert len(inviate) == 1
    assert "RSSMRA80A01H501U" not in inviate[0]
