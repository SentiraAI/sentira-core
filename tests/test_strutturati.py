"""Risposte strutturate dell'AI, serie temporali, download da URL esterni."""

from datetime import date, datetime
from types import SimpleNamespace

import httpx
import pytest

from sentira_core import ai_usage, rete, serie

TOOL = {"type": "function", "function": {"name": "salva", "parameters": {"type": "object"}}}


def _risposta(*, argomenti=None, testo=None):
    chiamate = ([SimpleNamespace(function=SimpleNamespace(name="salva", arguments=argomenti))]
                if argomenti is not None else None)
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(
        message=SimpleNamespace(tool_calls=chiamate, content=testo))])


class _Client:
    def __init__(self, *esiti):
        self.esiti, self.chiamate = list(esiti), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chiamate.append(kwargs)
        esito = self.esiti.pop(0)
        if isinstance(esito, Exception):
            raise esito
        return esito


def _nessun_record(*a):
    pass


def test_chiama_tool_forza_la_tool_con_effort_none():
    client = _Client(_risposta(argomenti='{"a": 1}'))
    args = ai_usage.chiama_tool(client, "f", record=_nessun_record, tool=TOOL,
                                model="gpt-6-luna", messages=[], max_completion_tokens=10)
    assert args == {"a": 1}
    k = client.chiamate[0]
    assert k["reasoning_effort"] == "none" and k["tools"] == [TOOL]
    assert k["tool_choice"] == {"type": "function", "function": {"name": "salva"}}
    assert k["max_completion_tokens"] == 10


def test_chiama_tool_modello_vecchio_senza_effort_e_nessuna_chiamata():
    client = _Client(_risposta())
    assert ai_usage.chiama_tool(client, "f", record=_nessun_record, tool=TOOL,
                                model="gpt-4o", messages=[]) is None
    assert "reasoning_effort" not in client.chiamate[0]


def test_chiama_tool_json_troncato_e_valueerror():
    client = _Client(_risposta(argomenti='{"a": '))
    with pytest.raises(ValueError):
        ai_usage.chiama_tool(client, "f", record=_nessun_record, tool=TOOL, model="gpt-6-luna")


class _Errore400(Exception):
    status_code = 400


def test_chiama_tool_riprova_una_volta_senza_effort():
    client = _Client(_Errore400("Function tools with reasoning_effort are not supported"),
                     _risposta(argomenti='{"ok": true}'))
    assert ai_usage.chiama_tool(client, "f", record=_nessun_record, tool=TOOL,
                                model="gpt-6-luna") == {"ok": True}
    assert "reasoning_effort" in client.chiamate[0]
    assert "reasoning_effort" not in client.chiamate[1]


def test_chiama_tool_altri_errori_risalgono_senza_retry():
    client = _Client(_Errore400("Rate limit reached"))
    with pytest.raises(_Errore400):
        ai_usage.chiama_tool(client, "f", record=_nessun_record, tool=TOOL, model="gpt-6-luna")
    assert len(client.chiamate) == 1


def test_leggi_json_tollera_recinti_e_rifiuta_il_resto():
    assert ai_usage.leggi_json(_risposta(testo='```json\n{"x": [1]}\n```')) == {"x": [1]}
    for testo in ("niente", "[1, 2]", "", None):
        with pytest.raises(ValueError):
            ai_usage.leggi_json(_risposta(testo=testo))


def test_periodi_con_i_vuoti_e_i_tre_passi():
    assert serie.periodi(date(2026, 1, 30), date(2026, 2, 2)) == [
        date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)]
    # dal lunedì della prima settimana a quello dell'ultima
    assert serie.periodi(date(2026, 10, 1), date(2026, 10, 14), "settimana") == [
        date(2026, 9, 28), date(2026, 10, 5), date(2026, 10, 12)]
    # fine gennaio: il +32 giorni non deve saltare febbraio
    assert serie.periodi(date(2026, 1, 31), date(2026, 3, 1), "mese") == [
        date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    assert serie.periodi(date(2026, 12, 15), date(2027, 1, 2), "mese") == [
        date(2026, 12, 1), date(2027, 1, 1)]
    assert serie.periodi(date(2026, 3, 2), date(2026, 3, 1)) == []


def test_per_periodo_accetta_datetime_e_ignora_none_e_fuori_intervallo():
    date_ = [datetime(2026, 10, 5, 23, 59), date(2026, 10, 11), None, date(2026, 9, 1)]
    assert serie.per_periodo(date_, date(2026, 10, 5), datetime(2026, 10, 19, 8),
                             "settimana") == {
        date(2026, 10, 5): 2, date(2026, 10, 12): 0, date(2026, 10, 19): 0}


def test_conta_dal_piu_frequente_senza_vuoti():
    assert serie.conta(["a", "b", "a", None, ""], top=1) == [{"nome": "a", "n": 2}]


def _getaddrinfo(ip):
    return lambda host, *a, **k: [(2, 1, 6, "", (ip, 80))]


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data/",
                                 "http://127.0.0.1:8080/", "http://10.0.1.5/"])
def test_controlla_rifiuta_la_rete_interna(url):
    with pytest.raises(ValueError, match="non pubblica"):
        rete.controlla(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.it/", "http://u:p@x.it/",
                                 "javascript:alert(1)"])
def test_controlla_rifiuta_schemi_e_credenziali(url):
    with pytest.raises(ValueError, match="non valida"):
        rete.controlla(url)


def test_controlla_accetta_un_indirizzo_pubblico():
    rete.controlla("https://8.8.8.8/")


def _finto_client(monkeypatch, gestore):
    vero = httpx.Client
    monkeypatch.setattr(rete.httpx, "Client",
                        lambda **k: vero(transport=httpx.MockTransport(gestore), **k))


def test_scarica_ferma_il_redirect_verso_la_rete_interna(monkeypatch):
    monkeypatch.setattr(rete.socket, "getaddrinfo", lambda host, *a, **k: [
        (2, 1, 6, "", ("127.0.0.1" if host == "127.0.0.1" else "8.8.8.8", 80))])
    visti = []

    def gestore(req):
        visti.append(str(req.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/privato"})
    _finto_client(monkeypatch, gestore)
    with pytest.raises(ValueError, match="non pubblica"):
        rete.scarica("https://shortener.example/x")
    assert visti == ["https://shortener.example/x"]  # il secondo hop non parte


def test_scarica_segue_i_redirect_e_limita_il_corpo(monkeypatch):
    monkeypatch.setattr(rete.socket, "getaddrinfo", _getaddrinfo("8.8.8.8"))

    def gestore(req):
        if req.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})
        return httpx.Response(200, headers={"content-type": "text/html; charset=iso-8859-1"},
                              content="perché".encode("latin-1") * 10)
    _finto_client(monkeypatch, gestore)
    p = rete.scarica("https://x.example/a", max_byte=8)
    assert p.url == "https://x.example/b"
    assert p.tipo == "text/html" and len(p.contenuto) == 8
    assert p.testo.startswith("perché")


def test_scarica_stato_di_errore_e_httperror(monkeypatch):
    monkeypatch.setattr(rete.socket, "getaddrinfo", _getaddrinfo("8.8.8.8"))
    _finto_client(monkeypatch, lambda req: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        rete.scarica("https://x.example/")


def test_scarica_troppi_redirect(monkeypatch):
    monkeypatch.setattr(rete.socket, "getaddrinfo", _getaddrinfo("8.8.8.8"))
    _finto_client(monkeypatch, lambda req: httpx.Response(302, headers={"location": "/giro"}))
    with pytest.raises(ValueError, match="troppi redirect"):
        rete.scarica("https://x.example/", max_redirect=2)

