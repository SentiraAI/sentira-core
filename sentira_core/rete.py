"""Richieste HTTP verso URL che arrivano da fuori (banner, landing, link in una
email): solo verso indirizzi pubblici, ogni redirect controllato, corpo limitato.

Senza questo controllo un link che punta (o redirige) a 169.254.169.254, a
127.0.0.1 o alla rete dei container fa leggere al server ciò che non dovrebbe
(SSRF). Il controllo è per hop: un redirect intermedio verso la rete interna
viene fermato prima di partire, non solo scoperto all'arrivo.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

UA = "Mozilla/5.0 (compatible; SentiraBot/1.0)"


def controlla(url: str) -> None:
    """ValueError se `url` non è http(s) o se il suo host risolve, anche solo in
    parte, verso un indirizzo non pubblico (rete interna, loopback, metadata).
    ponytail: resta la finestra DNS rebinding fra questo controllo e la
    connessione; chiuderla vuol dire connettersi all'IP già verificato."""
    parsed = urlparse(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password):
        raise ValueError("destinazione HTTP non valida")
    try:
        indirizzi = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM)
    except OSError as e:
        raise ValueError("host non risolvibile") from e
    if not indirizzi or any(not ipaddress.ip_address(a[4][0]).is_global for a in indirizzi):
        raise ValueError("destinazione non pubblica")


@dataclass
class Scaricato:
    url: str          # dopo i redirect
    tipo: str         # content-type, senza parametri
    contenuto: bytes  # al massimo max_byte
    charset: str

    @property
    def testo(self) -> str:
        try:
            return self.contenuto.decode(self.charset, errors="replace")
        except LookupError:  # charset dichiarato che Python non conosce
            return self.contenuto.decode("utf-8", errors="replace")


def scarica(url: str, *, timeout: float = 15, max_byte: int = 5_000_000,
            user_agent: str = UA, max_redirect: int = 10) -> Scaricato:
    """Scarica `url` seguendo i redirect uno per uno, ognuno controllato.

    ValueError se una destinazione non è pubblica o i redirect sono troppi;
    httpx.HTTPError per rete e stati 4xx/5xx. Il corpo si ferma a `max_byte`:
    una pagina enorme o infinita non riempie la memoria."""
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout) as client:
        for _ in range(max_redirect + 1):
            controlla(url)
            with client.stream("GET", url) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = urljoin(str(r.url), r.headers["location"])
                    continue
                r.raise_for_status()
                corpo = bytearray()
                for pezzo in r.iter_bytes():
                    corpo += pezzo
                    if len(corpo) >= max_byte:
                        break
                return Scaricato(str(r.url),
                                 r.headers.get("content-type", "").split(";")[0].strip(),
                                 bytes(corpo[:max_byte]), r.charset_encoding or "utf-8")
    raise ValueError("troppi redirect")
