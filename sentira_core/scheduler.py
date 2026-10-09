"""Scheduler dei job in background (APScheduler 3, BackgroundScheduler).

Un solo scheduler per processo, sul fuso di Roma. L'app decide solo quali job
registrare; accensione, spegnimento, `DISABLE_SCHEDULER` e la protezione dei
job stanno qui.

    from sentira_core import scheduler

    def _registra(s):
        s.add_job(scheduler.protetto("scrape", scrape.run), CronTrigger(hour=6), id="scrape")

    scheduler.avvia(_registra, report=report)   # nel lifespan
    scheduler.ferma()

`protetto(nome, fn)` fa tre cose che ogni job deve fare e che si dimenticavano:
una sola esecuzione alla volta per nome (il click «esegui ora» durante il giro
schedulato non ne fa partire un secondo), eccezione loggata e mandata a
errorreport, mai propagata allo scheduler.
"""

from __future__ import annotations

import functools
import logging
import threading
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from . import env
from .tempo import FUSO

log = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None
_report = None
_lock: dict[str, threading.Lock] = {}


def avvia(registra: Callable[[BackgroundScheduler], None] | None = None, *,
          report=None) -> BackgroundScheduler | None:
    """Accende lo scheduler (una volta) e chiama `registra(s)`. Con
    DISABLE_SCHEDULER=1 (test) non fa nulla e restituisce None."""
    global _scheduler, _report
    if env.flag("DISABLE_SCHEDULER"):
        log.info("Scheduler disabilitato (DISABLE_SCHEDULER=1)")
        return None
    _report = report
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone=FUSO.key)
        _scheduler.start()
    if registra:
        registra(_scheduler)
    log.info("Scheduler avviato: %d job attivi", len(_scheduler.get_jobs()))
    return _scheduler


def attivo() -> BackgroundScheduler | None:
    return _scheduler


def ferma() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def prossime(prefisso: str = "") -> dict[str, str]:
    """{id del job: prossima esecuzione ISO} dei job il cui id inizia per `prefisso`."""
    if _scheduler is None:
        return {}
    return {j.id: j.next_run_time.isoformat() for j in _scheduler.get_jobs()
            if j.id.startswith(prefisso) and j.next_run_time}


def protetto(nome: str, fn: Callable) -> Callable:
    lock = _lock.setdefault(nome, threading.Lock())

    @functools.wraps(fn)
    def esegui(*args, **kwargs):
        if not lock.acquire(blocking=False):
            log.warning("job %s già in corso: questa esecuzione salta", nome)
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — un job non deve fermare lo scheduler
            log.exception("job %s fallito", nome)
            if _report is not None:
                _report.registra(exc, "JOB", nome)
            return None
        finally:
            lock.release()

    return esegui
