"""Contratti dei moduli di piattaforma: frontend statico, schema, scheduler, env, tempo."""

import threading
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Column, Index, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import declarative_base

from sentira_core import ai_usage, emailer, env, scheduler, tempo
from sentira_core.sqlite import allinea_schema
from sentira_core.web import monta_frontend


# ── web.monta_frontend ──────────────────────────────────────────────────────
@pytest.fixture
def sito(tmp_path):
    static = tmp_path / "static"
    (static / "_next").mkdir(parents=True)
    (static / "index.html").write_text("indice")
    (static / "stats.html").write_text("statistiche")
    (static / "404.html").write_text("non trovata")
    (static / "_next" / "a.js").write_text("js")
    (static / "aziende").mkdir()
    (static / "aziende" / "index.html").write_text("aziende")
    (tmp_path / "app.db").write_text("SEGRETO")
    app = FastAPI()
    app.get("/api/health")(lambda: {"status": "ok"})
    monta_frontend(app, str(static))
    return TestClient(app)


@pytest.mark.parametrize("percorso,stato,corpo", [
    ("/", 200, "indice"), ("/stats", 200, "statistiche"), ("/aziende", 200, "aziende"),
    ("/_next/a.js", 200, "js"), ("/inesistente", 404, "non trovata"),
])
def test_frontend_risolve_le_pagine(sito, percorso, stato, corpo):
    r = sito.get(percorso)
    assert (r.status_code, r.text) == (stato, corpo)


@pytest.mark.parametrize("percorso", ["/%2e%2e/app.db", "/..%2fapp.db", "/%2e%2e%2fapp.db",
                                      "/stats/..%2f..%2fapp.db", "/%2e%2e/app", "/%00"])
def test_frontend_non_esce_dalla_cartella(sito, percorso):
    r = sito.get(percorso)
    assert r.status_code == 404 and "SEGRETO" not in r.text


def test_api_sconosciuta_risponde_json(sito):
    r = sito.get("/api/non-esiste")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    assert sito.get("/api/health").json() == {"status": "ok"}


def test_senza_export_non_monta_nulla(tmp_path):
    app = FastAPI()
    monta_frontend(app, str(tmp_path / "manca"))
    assert TestClient(app).get("/").status_code == 404


# ── sqlite.allinea_schema ───────────────────────────────────────────────────
def test_allinea_schema_aggiunge_colonne_e_indici(caplog):
    motore = create_engine("sqlite://")
    with motore.begin() as c:
        c.exec_driver_sql("CREATE TABLE cose (id INTEGER PRIMARY KEY)")
        c.exec_driver_sql("INSERT INTO cose (id) VALUES (1), (2)")

    Base = declarative_base()

    class Cosa(Base):
        __tablename__ = "cose"
        id = Column(Integer, primary_key=True)
        nome = Column(String)
        verificata = Column(Boolean, nullable=False, default=False)
        stato = Column(String, nullable=False, default="nuova")
        obbligatoria = Column(Integer, nullable=False)  # NOT NULL senza default: resta fuori
        doppione = Column(Integer, default=7)
        __table_args__ = (Index("ix_cose_nome", "nome"),
                          Index("ux_cose_doppione", "doppione", unique=True))  # due 7: fallisce

    fatte = allinea_schema(motore, Base)
    assert fatte == ["colonna cose.nome", "colonna cose.verificata", "colonna cose.stato",
                     "colonna cose.doppione", "indice ix_cose_nome"]
    assert "ux_cose_doppione non creato" in caplog.text
    with motore.connect() as c:
        assert c.execute(text("SELECT nome, verificata, stato, doppione FROM cose WHERE id = 1")
                         ).one() == (None, 0, "nuova", 7)
    assert "obbligatoria" not in {col["name"] for col in inspect(motore).get_columns("cose")}
    assert allinea_schema(motore, Base) == []  # idempotente


# ── scheduler ───────────────────────────────────────────────────────────────
def test_protetto_una_esecuzione_alla_volta_e_errori_segnalati():
    segnalati, dentro, libera = [], threading.Event(), threading.Event()

    class Report:
        def registra(self, exc, metodo, path):
            segnalati.append((type(exc).__name__, metodo, path))

    def lento():
        dentro.set()
        libera.wait(2)
        return "fatto"

    job = scheduler.protetto("lento", lento)
    t = threading.Thread(target=job)
    t.start()
    dentro.wait(2)
    assert job() is None          # il secondo click salta: il primo è ancora in corso
    libera.set()
    t.join()
    assert job() == "fatto"

    scheduler._report = Report()
    try:
        assert scheduler.protetto("rotto", lambda: 1 / 0)() is None
    finally:
        scheduler._report = None
    assert segnalati == [("ZeroDivisionError", "JOB", "rotto")]


def test_scheduler_spento_nei_test_e_acceso_altrimenti(monkeypatch):
    monkeypatch.setenv("DISABLE_SCHEDULER", "1")
    assert scheduler.avvia(lambda s: None) is None and scheduler.prossime() == {}
    monkeypatch.delenv("DISABLE_SCHEDULER")
    try:
        s = scheduler.avvia(lambda s: s.add_job(print, "interval", hours=1, id="automation-1"))
        s.add_job(print, "interval", hours=1, id="altro")
        assert list(scheduler.prossime("automation-")) == ["automation-1"]
        assert str(s.timezone) == "Europe/Rome"
    finally:
        scheduler.ferma()
    assert scheduler.attivo() is None


# ── env, tempo, modello, cap email ──────────────────────────────────────────
def test_env_toglie_commenti_e_virgolette(monkeypatch):
    monkeypatch.setenv("ORA", "8  # ora del reminder")
    monkeypatch.setenv("VUOTA", "")
    monkeypatch.setenv("SBAGLIATA", "otto")
    monkeypatch.setenv("SI", '"true"')
    assert env.intero("ORA", 6) == 8 and env.intero("SBAGLIATA", 6) == 6 and env.intero("MANCA", 6) == 6
    assert env.valore("VUOTA", "x") == "x" and env.flag("SI") and not env.flag("MANCA")


def test_modello_default_unico(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL_X", raising=False)
    assert ai_usage.modello("OPENAI_MODEL_X") == ai_usage.MODELLO_DEFAULT
    monkeypatch.setenv("OPENAI_MODEL_X", "gpt-7  # prova")
    assert ai_usage.modello("OPENAI_MODEL_X") == "gpt-7"


def test_oggi_e_quello_di_roma(monkeypatch):
    class Finto(datetime):
        @classmethod
        def now(cls, tz=None):  # 23:30 UTC del 31/12 = già 1° gennaio a Roma
            return datetime(2030, 12, 31, 23, 30, tzinfo=tempo.timezone.utc).astimezone(tz)

    monkeypatch.setattr(tempo, "datetime", Finto)
    assert tempo.oggi_roma() == date(2031, 1, 1)
    assert tempo.adesso_utc() == datetime(2030, 12, 31, 23, 30)


def test_cap_email_su_tabella_chiave_valore(monkeypatch):
    from sqlalchemy.orm import Session

    Base = declarative_base()

    class Stato(Base):
        __tablename__ = "sync_state"
        key = Column(String, primary_key=True)
        value = Column(String)

    motore = create_engine("sqlite://")
    Base.metadata.create_all(motore)
    monkeypatch.setenv("EMAIL_DAILY_CAP", "2")
    monkeypatch.setattr(emailer, "oggi_roma", lambda: date(2031, 1, 1))
    emailer.usa_contatore_kv(lambda: Session(motore), Stato)
    try:
        assert [emailer._sotto_il_cap() for _ in range(3)] == [True, True, False]
        with Session(motore) as s:
            assert s.get(Stato, "email_count_2031-01-01").value == "2"
    finally:
        emailer.usa_contatore(None)
