"""Consumo AI comune a lead-hunter-v2 e dropbox-agent.

Schema DB, scelta della tariffa e riepiloghi restano nelle applicazioni.
Il tracking non deve mai interrompere una chiamata AI riuscita.
"""

import logging

log = logging.getLogger("ai_usage")

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
