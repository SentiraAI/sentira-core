"""Motore SQLite in modalità WAL, configurato come serve a un'app FastAPI.

Le tabelle **non** stanno qui: ogni prodotto ha il suo schema, ed è giusto così.
Qui c'è solo la parte che era identica e che è facile sbagliare — il percorso
del file dentro il volume persistente, i PRAGMA, e il `check_same_thread` che
serve perché FastAPI serve le richieste da un thread pool.

    from sentira_core.sqlite import crea_motore, crea_sessione

    engine = crea_motore()                    # usa DATA_DIR, default ./data
    Session = crea_sessione(engine)
    Base.metadata.create_all(engine)
    allinea_schema(engine, Base)              # colonne e indici nuovi su un DB esistente
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine, event, inspect
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


def _default_sql(col) -> str | None:
    d = col.default
    if d is None or not d.is_scalar:
        return None
    if isinstance(d.arg, bool):
        return str(int(d.arg))
    if isinstance(d.arg, (int, float)):
        return f"{d.arg:g}"
    if isinstance(d.arg, str):
        return "'" + d.arg.replace("'", "''") + "'"
    return None


def allinea_schema(motore, Base) -> list[str]:
    """Aggiunge alle tabelle esistenti le colonne e gli indici che il modello ha
    e il DB no. `create_all` crea solo le tabelle mancanti; senza Alembic,
    questa è tutta la migrazione. Le colonne si ricavano dal modello, non da
    un elenco a mano (che si era dimenticato una colonna, e ogni query su
    quella tabella falliva).

    Il default scalare del modello diventa il DEFAULT SQL, così le righe
    vecchie partono da quel valore invece che da NULL. Una colonna NOT NULL
    senza default SQLite non la può aggiungere: resta fuori, con un warning.
    Restituisce le modifiche fatte, una stringa ciascuna.
    """
    fatte: list[str] = []
    insp = inspect(motore)
    esistenti = set(insp.get_table_names())
    q = motore.dialect.identifier_preparer.quote
    with motore.begin() as conn:
        for tabella in Base.metadata.sorted_tables:
            if tabella.name not in esistenti:
                continue
            presenti = {c["name"] for c in insp.get_columns(tabella.name)}
            for col in tabella.columns:
                if col.name in presenti:
                    continue
                default = _default_sql(col)
                if not col.nullable and default is None:
                    log.warning("colonna %s.%s non aggiunta: NOT NULL senza default, "
                                "serve una migrazione a mano", tabella.name, col.name)
                    continue
                ddl = col.type.compile(dialect=motore.dialect)
                if default is not None:
                    ddl += f"{'' if col.nullable else ' NOT NULL'} DEFAULT {default}"
                conn.exec_driver_sql(f"ALTER TABLE {q(tabella.name)} ADD COLUMN {q(col.name)} {ddl}")
                fatte.append(f"colonna {tabella.name}.{col.name}")
    # Un indice per transazione, e mai fatale: uno UNIQUE su dati con doppioni
    # fallisce, e l'app deve partire lo stesso (il warning dice cosa ripulire).
    for tabella in Base.metadata.sorted_tables:
        if tabella.name not in esistenti:
            continue
        presenti = {i["name"] for i in insp.get_indexes(tabella.name)}
        for indice in tabella.indexes:
            if indice.name in presenti:
                continue
            try:
                with motore.begin() as conn:
                    indice.create(conn, checkfirst=True)
                fatte.append(f"indice {indice.name}")
            except Exception as exc:  # noqa: BLE001
                log.warning("indice %s non creato: %s", indice.name, exc)
    for voce in fatte:
        log.info("schema allineato: %s", voce)
    return fatte
