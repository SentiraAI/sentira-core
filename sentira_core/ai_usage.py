"""Consumo AI comune a lead-hunter-v2 e dropbox-agent.

Schema DB, scelta della tariffa e riepiloghi restano nelle applicazioni.
Il tracking non deve mai interrompere una chiamata AI riuscita.
"""

import json
import logging
from datetime import date, datetime, timezone

from . import env, serie

log = logging.getLogger("ai_usage")

# Il modello di default di tutti i prodotti: cambiarlo qui (e spostare il pin)
# è tutta la migrazione. I valori veri di produzione stanno in env.public.
MODELLO_DEFAULT = "gpt-6-luna"


def modello(variabile: str = "OPENAI_MODEL", default: str = MODELLO_DEFAULT) -> str:
    """Il modello configurato in `variabile`, o il default se manca o è vuota."""
    return env.valore(variabile, default)

# USD per 1M token (input, cached input, cache writes, output): tariffe
# identiche nei due consumer. Fonte: developers.openai.com/api/docs/pricing.
# Cache writes 0.0 = il modello non la fattura separatamente (tutti tranne
# gpt-6-luna, che la introduce con la generazione GPT-6).
PRICING = {
    "gpt-4o-mini": (0.15, 0.075, 0.0, 0.60),
    "gpt-5-mini": (0.25, 0.025, 0.0, 2.00),
    "gpt-5.6-luna": (0.20, 0.02, 0.0, 1.20),
    # ponytail: solo tariffa "short context" (≤272K token input). Oltre la
    # soglia gpt-6-luna raddoppia input/cached/cache-writes e l'output costa
    # 1.5x — non modellato: nessuna chiamata di questo codebase si avvicina
    # alla soglia (storico truncato, documenti singoli). Se mai servisse,
    # aggiungere una seconda tupla "long" e selezionarla su prompt_tokens.
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
}


def cost_usd(pricing: tuple[float, float, float, float], prompt_tokens: int,
             cached_tokens: int, completion_tokens: int,
             cache_write_tokens: int = 0) -> float:
    """I token cached sono già inclusi nel prompt: non si pagano due volte."""
    usd_in, usd_cached, usd_write, usd_out = pricing
    billable_input = max(prompt_tokens - cached_tokens, 0)
    return ((billable_input / 1_000_000) * usd_in
            + (cached_tokens / 1_000_000) * usd_cached
            + (cache_write_tokens / 1_000_000) * usd_write
            + (completion_tokens / 1_000_000) * usd_out)


def reasoning_kwargs(model: str, effort: str) -> dict:
    """I modelli gpt-5+/gpt-6+ sono reasoning model: accettano reasoning_effort,
    i precedenti (gpt-4o*) lo rifiutano con un 400.
    ponytail: prefissi elencati a mano (gpt-5, gpt-6), estendere alla prossima
    generazione quando arriva."""
    return {"reasoning_effort": effort} if model.startswith(("gpt-5", "gpt-6")) else {}


def record(feature: str, model: str, usage, *, db, cost_usd) -> None:
    """Registra tramite db.get_session/db.AiUsage e il tariffario del consumer."""
    if usage is None:
        return
    try:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = getattr(details, "cached_tokens", 0) or 0
        cache_write_tokens = getattr(details, "cache_write_tokens", 0) or 0
        cost = cost_usd(model, prompt_tokens, cached_tokens, completion_tokens, cache_write_tokens)
        with db.get_session() as s:
            s.add(db.AiUsage(feature=feature, model=model,
                             prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                             total_tokens=total_tokens, cached_tokens=cached_tokens, cost_usd=cost))
            s.commit()
    except Exception as e:  # noqa: BLE001 — il tracking non deve mai rompere l'AI
        log.warning("Registrazione consumo AI fallita (feature=%s): %s", feature, e)


def complete(client, feature: str, *, record, **kwargs):
    """Chiama OpenAI, registra il consumo e restituisce la risposta invariata.

    Gli errori della chiamata risalgono: nessun retry o quirk di modello qui.
    """
    resp = client.chat.completions.create(**kwargs)
    record(feature, kwargs.get("model", ""), getattr(resp, "usage", None))
    return resp


def chiama_tool(client, feature: str, *, record, tool: dict, **kwargs) -> dict | None:
    """Risposta strutturata con una tool forzata: il modello DEVE chiamare `tool`
    (forma OpenAI, {"type": "function", "function": {...}}). Restituisce gli
    argomenti, None se non l'ha chiamata; ValueError se il JSON è malformato o
    troncato. Gli errori della chiamata risalgono, come in `complete`.

    reasoning_effort "none" è obbligatorio: gpt-5.6-luna e gpt-6-luna su
    /v1/chat/completions accettano le function tool solo così, e il loro default
    non lo è; senza, ogni chiamata dà 400 "Function tools with reasoning_effort
    are not supported". Se un modello futuro rifiuta il parametro in un'altra
    forma, un solo nuovo tentativo senza: adattarsi alla risposta dell'API
    invecchia meglio di un elenco di modelli."""
    argomenti = dict(kwargs, tools=[tool], tool_choice={
        "type": "function", "function": {"name": tool["function"]["name"]}})
    argomenti.update(reasoning_kwargs(kwargs.get("model", ""), "none"))
    try:
        resp = complete(client, feature, record=record, **argomenti)
    except Exception as e:
        if (getattr(e, "status_code", None) != 400 or "reasoning_effort" not in str(e)
                or "reasoning_effort" not in argomenti):
            raise
        log.info("%s: %s non accetta reasoning_effort con le tool, riprovo senza",
                 feature, kwargs.get("model"))
        argomenti.pop("reasoning_effort")
        resp = complete(client, feature, record=record, **argomenti)
    chiamate = resp.choices[0].message.tool_calls
    if not chiamate:
        return None
    dati = json.loads(chiamate[0].function.arguments)
    if not isinstance(dati, dict):
        raise ValueError("argomenti della tool non sono un oggetto JSON")
    return dati


def leggi_json(resp) -> dict:
    """L'oggetto JSON di una risposta con response_format json_object.

    Tollera i recinti markdown e il testo attorno (si prende dalla prima `{`
    all'ultima `}`); ValueError se non c'è un oggetto valido."""
    testo = (resp.choices[0].message.content or "").strip()
    try:
        dati = json.loads(testo[testo.find("{"): testo.rfind("}") + 1])
    except ValueError:
        raise ValueError(f"risposta AI non in JSON: {testo[:200]}") from None
    if not isinstance(dati, dict):
        raise ValueError(f"risposta AI non in JSON: {testo[:200]}")
    return dati


def usage_stats(db, pricing: dict, *, mesi: int = 6, colonna_data: str = "ts",
                adesso: datetime | None = None) -> dict:
    """Consumo in euro per la pagina «Consumo AI»: mese corrente, storico di
    `mesi` mesi (vuoti a zero), trend giornaliero del mese, totali dall'inizio.

    `colonna_data` è il nome della colonna data di `db.AiUsage` (`ts` o
    `created_at`: ogni app ha la sua). Il cambio è `AI_USD_TO_EUR` (default 0.86).
    Tutto in Python su una query sola: il volume è di poche centinaia di righe
    al mese. ponytail: se un cliente arriva a milioni di righe, aggregare in SQL.
    """
    cambio = float(env.valore("AI_USD_TO_EUR", "0.86"))
    adesso = adesso or datetime.now(timezone.utc).replace(tzinfo=None)
    consumo = db.AiUsage
    with db.get_session() as s:
        righe = s.query(getattr(consumo, colonna_data), consumo.feature, consumo.model,
                        consumo.cost_usd, consumo.prompt_tokens, consumo.completion_tokens,
                        consumo.cached_tokens).all()

    inizio_mese = adesso.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    anno, mese0 = divmod(inizio_mese.year * 12 + inizio_mese.month - 1 - (mesi - 1), 12)
    storico = {m.strftime("%Y-%m"): [0.0, 0]
               for m in serie.periodi(date(anno, mese0 + 1, 1), inizio_mese, "mese")}
    giorni = {g: [0.0, 0] for g in range(1, adesso.day + 1)}
    per_feature: dict[str, list] = {}
    per_model: dict[str, list] = {}
    mese = [0.0, 0]
    totale = [0.0, 0, 0, 0, 0]  # usd, richieste, input, output, cached
    primo = None

    def somma(voce, usd):
        voce[0] += usd
        voce[1] += 1

    for ts, feature, model, usd, tok_in, tok_out, tok_cached in righe:
        usd = usd or 0.0
        somma(totale, usd)
        totale[2] += tok_in or 0
        totale[3] += tok_out or 0
        totale[4] += tok_cached or 0
        if not ts:
            continue
        primo = ts if primo is None else min(primo, ts)
        if ts.strftime("%Y-%m") in storico:
            somma(storico[ts.strftime("%Y-%m")], usd)
        if ts >= inizio_mese:
            somma(mese, usd)
            somma(giorni.setdefault(ts.day, [0.0, 0]), usd)
            somma(per_feature.setdefault(feature, [0.0, 0]), usd)
            somma(per_model.setdefault(model, [0.0, 0]), usd)

    def eur(usd):
        return round(usd * cambio, 4)

    def voci(d):
        return {k: {"richieste": v[1], "cost_eur": eur(v[0])} for k, v in d.items()}

    return {
        "current": {
            "mese": inizio_mese.strftime("%Y-%m"),
            "cost_eur": eur(mese[0]), "cost_usd": round(mese[0], 4), "richieste": mese[1],
            "per_feature": voci(per_feature), "per_model": voci(per_model),
        },
        "history": [{"mese": m, "cost_eur": eur(v[0]), "richieste": v[1]} for m, v in storico.items()],
        "daily": [{"giorno": g, "label": f"{g:02d}", "cost_eur": eur(v[0]), "richieste": v[1]}
                  for g, v in sorted(giorni.items())],
        "totals": {
            "richieste": totale[1], "cost_eur": eur(totale[0]), "cost_usd": round(totale[0], 4),
            "prompt_tokens": totale[2], "completion_tokens": totale[3], "cached_tokens": totale[4],
            "dal": primo.strftime("%Y-%m-%d") if primo else None,
        },
        "pricing": {m: {"input_per_1m": v[0], "cached_per_1m": v[1],
                        "cache_write_per_1m": v[2], "output_per_1m": v[3]}
                    for m, v in pricing.items()},
    }
