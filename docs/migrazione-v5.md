# Migrazione v4 → v5

`v5` distribuisce il pacchetto Python `sentira-core==1.3.0` (prima: `1.2.0`).
Preparazione locale: pubblicazione del tag e deploy dei consumer sono operazioni
separate, non implicite nell'aggiornamento dei file.

## Confronto e regola di ammissione

Confronto del checkout del 7 settembre 2026: Mauro `src/ai_usage.py` ha 110
righe, Rossella 221. **Entrambi hanno già cached token e prezzi a tre colonne**;
la descrizione di Mauro senza cached si riferisce a uno stato precedente.

| Componente | Mauro | Rossella | Destinazione v5 |
|---|---|---|---|
| Calcolo USD | Input non cached + cached + output | Stessa formula | `sentira_core.ai_usage.cost_usd` |
| `record` | Estrazione usage, scrittura DB, errore non bloccante | Identico | Core, DB e scelta tariffa iniettati |
| `complete` | Chiamata, registrazione, risposta invariata | Identico | Core, callback `record` iniettata |
| Tariffe comuni | 4o-mini, 5-mini, 5.6-luna | Stessi tre modelli e valori | `sentira_core.ai_usage.PRICING` |
| Tariffe aggiuntive | 4o, 5.4-mini | Assenti | Copia estesa locale Mauro |
| Modello non elencato | `(2.50, 1.25, 10.00)` | `(0.25, 0.025, 2.00)` | Fallback locali invariati |
| Snapshot datati | Rimuove suffisso data prima del lookup | Lookup esatto | Normalizzazione locale Mauro |
| Timestamp DB | `created_at` | `ts` | Schemi locali invariati |
| Riepilogo | Ultimi N × 30 giorni, USD e token | Mese corrente, EUR, storico, trend, lifetime | API locali invariate |
| Pricing HTTP | Non esposto dal summary | Tre colonne in `/api/usage/stats` | Endpoint locale Rossella |

Si promuove l'intersezione già condivisa, non l'unione delle funzionalità.
Nessun riepilogo EUR aggiunto artificialmente a Mauro per giustificarne la
presenza nel core. Nessun tracking aggiunto a StudioGiallo: aggiorna soltanto
la dipendenza e verifica la compatibilità delle API core già usate.

## API e adattatori

Il core espone:

- `cost_usd(pricing, prompt_tokens, cached_tokens, completion_tokens)`: `pricing`
  è la terna USD per milione. I cached sono un sottoinsieme del prompt.
- `record(feature, model, usage, *, db, cost_usd)`: `db` espone `get_session()`
  e `AiUsage`; la callback costo sceglie la tariffa secondo la politica dell'app.
  `usage=None` non scrive; errori di tracking vengono loggati senza propagazione.
- `complete(client, feature, *, record, **kwargs)`: chiama il provider, registra
  e restituisce la risposta originale. Gli errori del provider risalgono.

I due `src/ai_usage.py` conservano solo la politica locale e i riepiloghi;
`functools.partial` lega `record` e `complete` alle dipendenze applicative.
I chiamanti mantengono le firme locali. Il core non importa OpenAI, non crea
client e non possiede schemi, router, variabili ambiente o stato configurabile.

Rossella streaming costruiva usage con `cached_tokens` al livello principale,
ma il tracker legge `prompt_tokens_details.cached_tokens`. L'adattatore chat
ora usa il formato atteso: la regressione esercita due chiamate in un turno
SSE e verifica il costo scontato nel DB. Nessun formato speciale aggiunto al core.

## Valutazione `_complete()` / `_model_kwargs()`

**Non promossi.** In Mauro `_model_kwargs()` esclude `temperature` sui `gpt-5`,
raddoppia il budget output e imposta effort `medium`. `_complete()` ritenta
una sola volta senza effort esclusivamente dopo un `BadRequestError` che
menziona `reasoning_effort`, se il parametro era stato inviato. Gli altri
errori risalgono; non si registra una chiamata fallita.

Rossella ha `reasoning_kwargs(model, effort)`, che aggiunge solo l'effort
richiesto dal chiamante: niente budget raddoppiato, niente stesso retry.
StudioGiallo non ha questi helper. Somiglianza non equivale a codice identico
in almeno due progetti: i quirk restano in `lead-hunter-v2/src/ai.py`.

## Aggiornamento dei tre consumer

Diff identico in ciascun `requirements.txt`:

```diff
-sentira-core @ https://github.com/SentiraAI/sentira-core/archive/refs/tags/v4.tar.gz
+sentira-core @ https://github.com/SentiraAI/sentira-core/archive/refs/tags/v5.tar.gz
```

Percorsi, relativi al workspace Sentira:

- `clienti/Mauro/lead-hunter-v2/requirements.txt`
- `clienti/Rossella/dropbox-agent/requirements.txt`
- `clienti/StudioGiallo/studio-agent/requirements.txt`

Nessuna migrazione DB, nessun ricalcolo delle righe storiche, nessun cambio
alle tariffe o ad `AI_USD_TO_EUR`. I costi già salvati restano tali, compresi
quelli dello streaming precedente alla correzione. Il vincolo Python resta
`>=3.10`; nessuna dipendenza nuova.

Rispetto a `v4`, il ramo core conteneva già la rimozione di `notify.riepilogo`
(commit `1772889`): Discord resta per gli alert operativi. Nessuno dei tre
consumer lo chiama; non reintrodurre l'API rimossa.

Ordine di pubblicazione: prima rendere disponibile `v5` nel repository core,
poi distribuire i consumer con `sentira deploy <cliente>`. Non deployare
requirements che puntano al tag finché il tarball GitHub non è disponibile.
Non spostare i tag `v1`–`v4`. Il ritorno a `v4` richiede anche il rollback degli
adattatori Mauro/Rossella: cambiare solo requirements causerebbe un import
fallito di `sentira_core.ai_usage`.

## Verifica

Prima del tag: installare il tarball candidato non-editable negli ambienti
di test e lanciare `python -m pytest tests/ -q` per core e tutti e tre i
consumer. Non sostituire la nuova libreria con mock o con `PYTHONPATH`.
I test core coprono sconto cached, usage assente, risposta AI preservata con
DB indisponibile ed errore provider senza addebito. I test consumer verificano
le rispettive politiche e integrazioni; la regressione streaming deve fallire
prima della correzione e passare dopo.
