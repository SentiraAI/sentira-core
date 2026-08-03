"""Motore SQLite in modalità WAL, configurato come serve a un'app FastAPI.

Le tabelle **non** stanno qui: ogni prodotto ha il suo schema, ed è giusto così.
Qui c'è solo la parte che era identica e che è facile sbagliare — il percorso
del file dentro il volume persistente, i PRAGMA, e il `check_same_thread` che
serve perché FastAPI serve le richieste da un thread pool.

    from sentira_core.sqlite import crea_motore, crea_sessione

    engine = crea_motore()                    # usa DATA_DIR, default ./data
    Session = crea_sessione(engine)
    Base.metadata.create_all(engine)
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

log = logging.getLogger("db")


def percorso_db(nome: str = "app.db") -> str:
    """Il file del database dentro DATA_DIR.

    In produzione DATA_DIR è il mount del volume persistente di Coolify
    (`/app/data`). Se punta altrove, ogni redeploy ricrea il container e **il
    database sparisce**: è il singolo errore più costoso di questo stack, ed è
    la ragione per cui questa funzione crea la cartella e logga dove scrive.
    """
    cartella = os.environ.get("DATA_DIR", "data")
    os.makedirs(cartella, exist_ok=True)
    return os.path.join(cartella, nome)


def crea_motore(nome: str = "app.db", echo: bool = False):
    percorso = percorso_db(nome)
    log.info("database: %s", os.path.abspath(percorso))
    motore = create_engine(
        f"sqlite:///{percorso}",
        echo=echo,
        # FastAPI serve le richieste sincrone da un thread pool: senza questo,
        # SQLite rifiuta la connessione riusata da un thread diverso.
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(motore, "connect")
    def _pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        # WAL: letture concorrenti mentre una scrittura è in corso. Senza,
        # lo scheduler che scrive blocca le richieste della dashboard.
        cur.execute("PRAGMA journal_mode=WAL")
        # NORMAL invece di FULL: con WAL è sicuro contro i crash del processo,
        # e toglie un fsync per transazione.
        cur.execute("PRAGMA synchronous=NORMAL")
        # Senza questo SQLite NON applica le foreign key. È spento di default
        # per retrocompatibilità, e il silenzio è la parte pericolosa.
        cur.execute("PRAGMA foreign_keys=ON")
        # Aspetta invece di fallire subito con "database is locked".
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return motore


def crea_sessione(motore):
    return sessionmaker(bind=motore, autoflush=False, expire_on_commit=False)
