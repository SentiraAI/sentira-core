"""Le difese comuni: se una di queste si spegne, si spegne in tutti i prodotti."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentira_core import emailer
from sentira_core.auth import TENTATIVI_MAX_TOTALI, crea_auth
from sentira_core.web import proteggi


def _app():
    app = FastAPI()
    proteggi(app)

    @app.post("/api/x")
    def x():
        return {"ok": True}

    return TestClient(app)


def test_scrittura_da_altra_origine_rifiutata():
    c = _app()
    assert c.post("/api/x", headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert c.post("/api/x", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert c.post("/api/x", headers={"sec-fetch-site": "same-origin"}).status_code == 200
    assert c.post("/api/x").status_code == 200  # non browser


def test_header_di_sicurezza_presenti():
    r = _app().post("/api/x")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_template_in_sandbox():
    import pytest
    with pytest.raises(emailer.EmailError):
        emailer.rendi("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})


def test_html_grezzo_escapato_nell_email():
    assert "<script>" not in emailer._testo_in_html("ciao <script>x</script> **ok**")
    assert "<strong>ok</strong>" in emailer._testo_in_html("**ok**")
    assert "<blockquote>" in emailer._testo_in_html("> citazione")


def test_limite_globale_di_login(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "segreta")
    monkeypatch.setenv("COOKIE_SECURE", "0")
    auth = crea_auth(nome_cookie="s", giorni=1, ambito="t")
    app = FastAPI()
    app.include_router(auth.router)
    c = TestClient(app)
    codici = [c.post("/api/auth/login", json={"password": "no"},
                     headers={"cf-connecting-ip": f"10.0.0.{i}"}).status_code
              for i in range(TENTATIVI_MAX_TOTALI + 1)]
    assert codici[-1] == 429
    assert len(auth.tentativi) <= 2 + TENTATIVI_MAX_TOTALI
