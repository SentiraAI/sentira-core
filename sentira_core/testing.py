"""Aiuti per i test delle app: ambiente isolato, DB in memoria, finto OpenAI.

In `tests/conftest.py`, PRIMA di importare l'app:

    from sentira_core import testing
    testing.isola_ambiente("leadhunter-test-", segreti=("SERPAPI_KEY",),
                           valori={"OPENAI_MODEL_COMPOSE": "gpt-4o-mini"})
    from src import app, db

    @pytest.fixture(autouse=True)
    def fresh_db():
        with testing.db_in_memoria(db):
            yield

Nei test della chat:

    richieste = testing.finto_openai(monkeypatch, [[testing.chunk("Ciao.", finish_reason="stop")]])
    eventi = testing.eventi_sse(client, message="Ciao")
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

# Letti da sentira_core: in un test non devono mai arrivare dal .env locale.
SEGRETI = ("DASHBOARD_PASSWORD", "SESSION_SECRET", "OPENAI_API_KEY", "EMAIL_PROVIDER_API_KEY",
           "EMAIL_FROM", "DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL_ERRORI")


def isola_ambiente(prefisso: str = "test-", *, segreti: tuple[str, ...] = (),
                   valori: dict[str, str] | None = None) -> None:
    """DATA_DIR temporanea, scheduler spento, segreti tolti, `.env` locale ignorato.

    `load_dotenv` diventa un no-op: l'app lo chiama all'import e rimetteva i
    segreti del `.env` di sviluppo dopo che il conftest li aveva tolti. Così il
    test gira in locale con lo stesso ambiente della CI, che il `.env` non ce l'ha.
    """
    try:
        import dotenv
        dotenv.load_dotenv = lambda *a, **k: False
    except ImportError:
        pass
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix=prefisso)
    os.environ["DISABLE_SCHEDULER"] = "1"
    for chiave in (*SEGRETI, *segreti):
        os.environ.pop(chiave, None)
    os.environ.update(valori or {})


@contextmanager
def db_in_memoria(modulo_db, dopo=None):
    """Sostituisce `modulo_db.engine` con SQLite in memoria condiviso fra thread
    (StaticPool: TestClient serve le richieste da un threadpool), crea le
    tabelle, chiama `dopo()` (seed) e alla fine ripristina l'engine vero."""
    vecchio = modulo_db.engine
    modulo_db.engine = create_engine("sqlite://", poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
    modulo_db.Base.metadata.create_all(modulo_db.engine)
    if dopo:
        dopo()
    try:
        yield modulo_db.engine
    finally:
        modulo_db.Base.metadata.drop_all(modulo_db.engine)
        modulo_db.engine.dispose()
        modulo_db.engine = vecchio


def chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Un pezzo dello stream di chat.completions; con `usage` è il chunk finale dei consumi."""
    return SimpleNamespace(usage=usage, choices=[] if usage else [SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish_reason)])


def chiamata(nome, argomenti, indice=0, identificativo="call_0"):
    """Una tool call (anche frammentata: nome None e argomenti parziali)."""
    if not isinstance(argomenti, str):
        argomenti = json.dumps(argomenti)
    return SimpleNamespace(index=indice, id=identificativo,
                           function=SimpleNamespace(name=nome, arguments=argomenti))


def finto_openai(monkeypatch, risposte: list) -> list[dict]:
    """Sostituisce `openai.OpenAI`: la n-esima `create()` restituisce lo stream
    `risposte[n]` (lista di `chunk`). Restituisce la lista delle richieste fatte,
    da ispezionare (messaggi, modello, tool_choice…)."""
    richieste: list[dict] = []

    def create(**kwargs):
        richieste.append(deepcopy(kwargs))
        return iter(risposte[len(richieste) - 1])

    client = lambda *a, **k: SimpleNamespace(  # noqa: E731
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setenv("OPENAI_API_KEY", "chiave-fittizia")
    try:
        import openai
        monkeypatch.setattr(openai, "OpenAI", client)
    except ImportError:
        monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=client))
    return richieste


def eventi_sse(client, path: str = "/api/chat", **body) -> list[dict]:
    """POST a un endpoint SSE e restituisce gli eventi `data:` decodificati."""
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-cache"
    return [json.loads(riga[6:]) for riga in r.text.splitlines() if riga.startswith("data: ")]
