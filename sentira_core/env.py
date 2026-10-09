"""Lettura delle variabili d'ambiente, tollerante con i `.env` scritti a mano.

Un `.env` locale ha spesso commenti in coda (`REMINDER_ORA=8  # ora`) e
python-dotenv li lascia nel valore: `int("8  # ora")` faceva crashare l'app
all'avvio. Qui il commento e le virgolette si tolgono, e il vuoto vale come
assente. Non usare per i segreti: una password può contenere ` #`.
"""

from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("env")

_COMMENTO = re.compile(r"\s+#.*$")
_VERI = {"1", "true", "yes", "si", "sì", "on"}


def valore(nome: str, default: str = "") -> str:
    v = os.environ.get(nome)
    if v is None:
        return default
    v = _COMMENTO.sub("", v).strip().strip("\"'")
    return v or default


def flag(nome: str, default: bool = False) -> bool:
    v = valore(nome).lower()
    return v in _VERI if v else default


def intero(nome: str, default: int) -> int:
    v = valore(nome)
    try:
        return int(v) if v else default
    except ValueError:
        log.warning("%s=%r non è un intero: uso %d", nome, v, default)
        return default


def configura_logging() -> None:
    """`logging.basicConfig` col livello di LOG_LEVEL (default INFO)."""
    livello = valore("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=livello if isinstance(logging.getLevelName(livello), int) else "INFO")
    # httpx e httpcore loggano a INFO l'URL intero di ogni richiesta: chiavi in
    # query string e token nei path dei webhook finirebbero nei log di Coolify.
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)
