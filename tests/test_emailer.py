"""Test dell'invio email condiviso.

Nessun test tocca la rete: httpx viene sostituito. Mandare una email vera da una
suite di test significherebbe, prima o poi, mandarla a un cliente.
"""

import pytest

from sentira_core import emailer


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER_API_KEY", "re_finta")
    monkeypatch.setenv("EMAIL_FROM", "Test <test@esempio.it>")
    monkeypatch.delenv("EMAIL_DAILY_CAP", raising=False)
    emailer.usa_contatore(None)
    emailer._avvisato_senza_contatore = False


class RispostaFinta:
    def __init__(self, status=200, corpo=None, testo=""):
        self.status_code = status
        self._corpo = corpo or {"id": "email-123"}
        self.text = testo

    def json(self):
        return self._corpo


@pytest.fixture
def cattura(monkeypatch):
    """Intercetta la POST verso Resend e restituisce cosa sarebbe partito."""
    inviate = []

    def finta_post(url, json=None, headers=None, timeout=None):
        inviate.append({"url": url, "payload": json, "headers": headers})
        return RispostaFinta()

    monkeypatch.setattr(emailer.httpx, "post", finta_post)
    return inviate


def test_invio_riuscito(cattura):
    assert emailer.invia("a@x.it", "Oggetto", testo="ciao") == "email-123"
    assert cattura[0]["payload"]["to"] == ["a@x.it"]
    assert cattura[0]["payload"]["from"] == "Test <test@esempio.it>"


def test_destinatari_csv_diventano_lista(cattura):
    emailer.invia("a@x.it, b@y.it ,", "O", testo="c")
    assert cattura[0]["payload"]["to"] == ["a@x.it", "b@y.it"]


def test_senza_chiave_non_invia_e_non_esplode(monkeypatch, cattura):
    monkeypatch.delenv("EMAIL_PROVIDER_API_KEY")
    assert emailer.invia("a@x.it", "O", testo="c") is None
    assert cattura == []


def test_senza_mittente_non_invia(monkeypatch, cattura):
    """EMAIL_FROM vuoto è lo stato reale di un cliente non ancora verificato su
    Resend: deve degradare a "non invio", non far crashare l'applicazione."""
    monkeypatch.setenv("EMAIL_FROM", "")
    assert emailer.invia("a@x.it", "O", testo="c") is None
    assert cattura == []


def test_nessun_destinatario_non_invia(cattura):
    assert emailer.invia([], "O", testo="c") is None
    assert emailer.invia("  ,  ", "O", testo="c") is None
    assert cattura == []


def test_idempotency_key_troncata_a_256(cattura):
    emailer.invia("a@x.it", "O", testo="c", idempotency_key="k" * 400)
    assert len(cattura[0]["headers"]["Idempotency-Key"]) == 256


def test_errore_di_resend_solleva(monkeypatch):
    monkeypatch.setattr(emailer.httpx, "post",
                        lambda *a, **k: RispostaFinta(422, testo="dominio non verificato"))
    with pytest.raises(emailer.EmailError, match="422"):
        emailer.invia("a@x.it", "O", testo="c")


def test_errore_di_rete_solleva(monkeypatch):
    def esplode(*a, **k):
        raise emailer.httpx.ConnectError("rete assente")
    monkeypatch.setattr(emailer.httpx, "post", esplode)
    with pytest.raises(emailer.EmailError, match="rete"):
        emailer.invia("a@x.it", "O", testo="c")


def test_cap_giornaliero_blocca(monkeypatch, cattura):
    monkeypatch.setenv("EMAIL_DAILY_CAP", "2")
    conteggi = {}

    def contatore(chiave, incrementa):
        attuale = conteggi.get(chiave, 0)
        if incrementa:
            conteggi[chiave] = attuale + 1
        return attuale

    emailer.usa_contatore(contatore)
    emailer.invia("a@x.it", "1", testo="c")
    emailer.invia("a@x.it", "2", testo="c")
    with pytest.raises(emailer.EmailError, match="Cap giornaliero"):
        emailer.invia("a@x.it", "3", testo="c")
    assert len(cattura) == 2


def test_senza_contatore_il_cap_non_blocca(cattura):
    """Meglio inviare senza cap che non inviare per una dipendenza mancante —
    ma il modulo lo dice nei log una volta sola."""
    for i in range(60):
        emailer.invia("a@x.it", str(i), testo="c")
    assert len(cattura) == 60


def test_template_rende_le_variabili():
    assert emailer.rendi("Ciao {{nome}}", {"nome": "Mauro"}) == "Ciao Mauro"


def test_template_con_variabile_mancante_solleva():
    """StrictUndefined: meglio un errore qui che una email con un buco dentro."""
    with pytest.raises(emailer.EmailError):
        emailer.rendi("Ciao {{nome}}", {})


def test_testo_diventa_html_se_html_non_dato(cattura):
    emailer.invia("a@x.it", "O", testo="**grassetto**")
    assert "<strong>grassetto</strong>" in cattura[0]["payload"]["html"]
    assert cattura[0]["payload"]["text"] == "**grassetto**"


def test_firma_storica_con_parametri_per_nome(cattura):
    """I chiamanti esistenti passano `subject=` e `text=`, non `oggetto=`/`testo=`.

    Un semplice alias (`send_html_email = invia`) avrebbe mantenuto il nome
    della funzione ma cambiato i nomi dei parametri sotto i piedi a chi chiama,
    con un TypeError a runtime. Serve un wrapper vero.
    """
    emailer.send_html_email(to="a@x.it", subject="Oggetto", text="ciao",
                            idempotency_key="k", cc="c@x.it")
    payload = cattura[0]["payload"]
    assert payload["subject"] == "Oggetto"
    assert payload["text"] == "ciao"
    assert payload["cc"] == ["c@x.it"]


def test_render_template_firma_storica():
    assert emailer.render_template("Ciao {{n}}", {"n": "Mauro"}) == "Ciao Mauro"
