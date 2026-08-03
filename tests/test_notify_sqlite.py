"""Test delle notifiche e della configurazione SQLite."""

import os

import pytest
from sqlalchemy import Column, Integer, String, text
from sqlalchemy.orm import declarative_base

from sentira_core import notify
from sentira_core.sqlite import crea_motore, crea_sessione, percorso_db


# ── notify ──────────────────────────────────────────────────────────────────
@pytest.fixture
def catturate(monkeypatch):
    inviate = []
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    monkeypatch.setattr(notify.httpx, "post",
                        lambda url, json=None, timeout=None: inviate.append(json["content"]))
    return inviate


def test_allarme_job_fallito(catturate):
    notify.allarme_job("Lead Hunter", "scrape", "failed", 10, 0, "timeout")
    assert "🔴" in catturate[0] and "FALLITO" in catturate[0] and "timeout" in catturate[0]


def test_allarme_job_vuoto_e_distinto_dal_fallimento(catturate):
    """Un job che riceve dati e non ne produce non è un successo: ha quasi
    sempre un problema silenzioso a monte, e va segnalato diversamente."""
    notify.allarme_job("Lead Hunter", "enrich", "completed_empty", 10, 0)
    assert "🟡" in catturate[0]
    assert "SENZA RISULTATI" in catturate[0]


def test_messaggio_troncato_sotto_il_limite_discord(catturate):
    notify.allarme_job("P", "j", "failed", 1, 0, "x" * 5000)
    assert len(catturate[0]) <= notify.LIMITE_DISCORD


def test_senza_webhook_non_esplode(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    notify.manda("ciao")  # non deve sollevare


def test_errore_di_rete_non_propaga(monkeypatch):
    """Una notifica rotta non deve far fallire il job che la chiama: sarebbe il
    colmo che l'allarme causasse il guasto che deve segnalare."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")

    def esplode(*a, **k):
        raise notify.httpx.ConnectError("rete assente")

    monkeypatch.setattr(notify.httpx, "post", esplode)
    notify.manda("ciao")  # non deve sollevare


def test_riepilogo_vuoto_non_manda_nulla(catturate):
    notify.riepilogo("P", "Buongiorno", {"alta": 0, "bassa": 0})
    assert catturate == []


# ── sqlite ──────────────────────────────────────────────────────────────────
Base = declarative_base()


class Cosa(Base):
    __tablename__ = "cose"
    id = Column(Integer, primary_key=True)
    nome = Column(String)


def test_percorso_dentro_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "volume"))
    p = percorso_db("test.db")
    assert p == os.path.join(str(tmp_path / "volume"), "test.db")
    assert os.path.isdir(tmp_path / "volume")  # la cartella viene creata


def test_pragma_applicati(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    motore = crea_motore("p.db")
    with motore.connect() as c:
        assert c.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert c.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL


def test_sessione_scrive_e_rilegge(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    motore = crea_motore("s.db")
    Base.metadata.create_all(motore)
    Sessione = crea_sessione(motore)
    with Sessione() as s:
        s.add(Cosa(nome="prova"))
        s.commit()
    with Sessione() as s:
        assert s.query(Cosa).one().nome == "prova"
