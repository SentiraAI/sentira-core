"""Serie temporali per dashboard e grafici: i periodi di un intervallo con i
vuoti a zero, e i conteggi nella forma dei grafici della chat.

Query, chiavi e forma dei punti restano nelle app: qui solo il calendario.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Literal

Passo = Literal["giorno", "settimana", "mese"]


def _giorno(d: date) -> date:
    # un datetime è anche un date, ma i due non si confrontano fra loro
    return d.date() if isinstance(d, datetime) else d


def inizio(d: date, passo: Passo = "giorno") -> date:
    """L'inizio del periodo che contiene `d`: il giorno stesso, il lunedì o il primo del mese."""
    d = _giorno(d)
    if passo == "settimana":
        return d - timedelta(days=d.weekday())
    if passo == "mese":
        return d.replace(day=1)
    return d


def periodi(da: date, a: date, passo: Passo = "giorno") -> list[date]:
    """Gli inizi di tutti i periodi da quello che contiene `da` a quello che
    contiene `a`, compresi e in ordine: anche quelli senza dati."""
    p, fine, out = inizio(da, passo), _giorno(a), []
    while p <= fine:
        out.append(p)
        if passo == "mese":
            p = (p + timedelta(days=32)).replace(day=1)
        else:
            p += timedelta(days=7 if passo == "settimana" else 1)
    return out


def per_periodo(date_: Iterable[date | None], da: date, a: date,
                passo: Passo = "giorno") -> dict[date, int]:
    """Quante date cadono in ogni periodo fra `da` e `a`, vuoti a zero e in
    ordine. Le date fuori dall'intervallo e i None non si contano."""
    conta = Counter(inizio(d, passo) for d in date_ if d)
    return {p: conta[p] for p in periodi(da, a, passo)}


def conta(valori: Iterable, top: int | None = None) -> list[dict]:
    """[{"nome", "n"}] dal più frequente, vuoti esclusi: la forma che
    `chat.grafico` si aspetta."""
    frequenze = Counter(v for v in valori if v not in (None, ""))
    return [{"nome": k, "n": n} for k, n in frequenze.most_common(top)]
