"""Contratti condivisi: cache scontata, tracking isolato, errori AI propagati."""

from functools import partial
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Float, Integer, String, create_engine
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


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield SimpleNamespace(get_session=sessionmaker(bind=engine), AiUsage=Consumo)
    engine.dispose()


def _cost_usd(model, prompt, cached, completion):
    return ai_usage.cost_usd(ai_usage.PRICING[model], prompt, cached, completion)


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
