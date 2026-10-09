"""«Oggi» e «adesso», uguali in ogni prodotto.

Il container gira in UTC: `date.today()` cambia giorno alle 2 di notte (ora
legale) o all'1 (ora solare) italiane, e tutto ciò che conta «per giorno» — il
cap delle email, i grafici per settimana, le scadenze di oggi — sbaglia di un
giorno in quella finestra. Il giorno giusto è quello di Roma.

Le colonne `DateTime` del database restano UTC naive: `adesso_utc()` è l'istante
da scrivere lì.

Sulle immagini slim serve `tzdata` (è fra le dipendenze di sentira-core):
senza, `ZoneInfo("Europe/Rome")` crasha all'avvio solo in produzione.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")


def oggi_roma() -> date:
    return datetime.now(FUSO).date()


def adesso_utc() -> datetime:
    """Istante corrente, UTC naive: coerente con le colonne `DateTime` del DB."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
