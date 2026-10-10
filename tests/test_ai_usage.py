"""Contratti condivisi: cache scontata, tracking isolato, errori AI propagati."""

from datetime import datetime
from functools import partial
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from sentira_core import ai_usage

Base = declarative_base()


class Consumo(Base):
    __tablename__ = "consumi"
    id = Column(Integer, primary_key=True)
    feature = Column(String)
    model = Column(String)
    prompt_tokens = Column(Integer)
    cached_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    cost_usd = Column(Float)
    quando = Column(DateTime)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield SimpleNamespace(get_session=sessionmaker(bind=engine), AiUsage=Consumo)
    engine.dispose()


def _cost_usd(model, prompt, cached, completion, cache_write=0):
    return ai_usage.cost_usd(ai_usage.PRICING[model], prompt, cached, completion, cache_write)


def test_cache_scontata_e_usage_assente(db):
    registra = partial(ai_usage.record, db=db, cost_usd=_cost_usd)
    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=500_000,
                            total_tokens=None,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=900_000))
    registra("chat", "gpt-5.6-luna", usage)
    registra("chat", "gpt-5.6-luna", None)
    with db.get_session() as sessione:
        riga = sessione.query(Consumo).one()
        # 100k input + 900k cached + 500k output: niente doppio addebito.
        assert riga.cost_usd == pytest.approx(0.638)
        assert riga.total_tokens == 1_500_000
        assert riga.cached_tokens == 900_000


def test_errore_database_non_perde_risposta_ai(db, monkeypatch, caplog):
    risposta = SimpleNamespace(choices=["risposta utile"], usage=SimpleNamespace(
        prompt_tokens=100, completion_tokens=20))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: risposta)))

    def guasto():
        raise RuntimeError("database indisponibile")

    monkeypatch.setattr(db, "get_session", guasto)
    registra = partial(ai_usage.record, db=db, cost_usd=_cost_usd)
    assert ai_usage.complete(client, "chat", record=registra,
                             model="gpt-5.6-luna", messages=[]) is risposta
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_errore_ai_risale_senza_addebitare(db):
    errore = RuntimeError("servizio AI indisponibile")

    def guasto(**kwargs):
        raise errore

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=guasto)))
    registra = partial(ai_usage.record, db=db, cost_usd=_cost_usd)
    with pytest.raises(RuntimeError) as sollevato:
        ai_usage.complete(client, "chat", record=registra,
                          model="gpt-5.6-luna", messages=[])
    assert sollevato.value is errore
    with db.get_session() as sessione:
        assert sessione.query(Consumo).count() == 0


def test_usage_stats_in_euro_con_colonna_data_a_scelta(db, monkeypatch):
    monkeypatch.setenv("AI_USD_TO_EUR", "0.5")
    def riga(quando, feature, usd):
        return Consumo(quando=quando, feature=feature, model="gpt-6-luna", cost_usd=usd,
                       prompt_tokens=10, completion_tokens=5, cached_tokens=2, total_tokens=15)
    with db.get_session() as s:
        s.add_all([riga(datetime(2026, 10, 3, 9), "chat", 2.0),
                   riga(datetime(2026, 10, 9, 9), "chat", 1.0),
                   riga(datetime(2026, 10, 9, 10), "extract", 1.0),
                   riga(datetime(2026, 8, 1, 9), "chat", 4.0),
                   riga(None, "chat", 8.0)])  # senza data: solo nei totali
        s.commit()

    r = ai_usage.usage_stats(db, ai_usage.PRICING, mesi=3, colonna_data="quando",
                             adesso=datetime(2026, 10, 10, 12))

    assert r["current"]["cost_eur"] == 2.0 and r["current"]["richieste"] == 3
    assert r["current"]["per_feature"]["chat"] == {"richieste": 2, "cost_eur": 1.5}
    # tre mesi, settembre vuoto a zero
    assert [(h["mese"], h["cost_eur"]) for h in r["history"]] == [
        ("2026-08", 2.0), ("2026-09", 0.0), ("2026-10", 2.0)]
    assert [d["giorno"] for d in r["daily"]] == list(range(1, 11))
    assert r["daily"][8]["cost_eur"] == 1.0
    assert r["totals"] == {"richieste": 5, "cost_eur": 8.0, "cost_usd": 16.0, "prompt_tokens": 50,
                           "completion_tokens": 25, "cached_tokens": 10, "dal": "2026-08-01"}
    assert r["pricing"]["gpt-6-luna"]["cache_write_per_1m"] == 0.125


def test_usage_stats_senza_righe(db):
    r = ai_usage.usage_stats(db, {}, colonna_data="quando", adesso=datetime(2026, 1, 15))
    assert r["totals"]["richieste"] == 0 and r["totals"]["dal"] is None
    assert [h["mese"] for h in r["history"]] == ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01"]
