# sentira-core

Il codice comune ai prodotti [Sentira](https://github.com/SentiraAI): auth a
password singola, invio email, notifiche operative, configurazione SQLite, consumo AI,
chat sui dati del cliente (backend Python + pagina React).

Qui vive **solo** ciò che era già identico in più progetti e che sbagliare costa.
Niente logica di business, niente schemi di dati, niente che riguardi un cliente.

```bash
pip install "sentira-core @ https://github.com/SentiraAI/sentira-core/archive/refs/tags/v7.tar.gz"
npm install https://github.com/SentiraAI/sentira-core/archive/refs/tags/v7.tar.gz   # solo per la chat
```

## Perché esiste

`lead-hunter-v2` e `dropbox-agent` avevano `auth.py` identico al 95% (differivano
per tre costanti) ed `emailer.py` identico al 100% — differiva solo un commento.
Ogni correzione andava fatta due volte, e la seconda volta si dimenticava.

La regola per aggiungere qualcosa qui: **deve già esistere identico in almeno due
progetti**. Codice messo qui "perché prima o poi servirà" diventa un vincolo per
tutti senza essere utile a nessuno.

## `sentira_core.auth`

Password singola, cookie di sessione firmato HMAC, nessuno stato lato server.
Il segreto di firma è derivato dalla password: cambiare `DASHBOARD_PASSWORD`
invalida da sola tutte le sessioni esistenti.

```python
from sentira_core.auth import crea_auth

auth = crea_auth(nome_cookie="lh-session", giorni=30, ambito="lead-hunter")
app.include_router(auth.router)          # /api/auth/{login,logout,me}

@app.get("/api/dati", dependencies=[Depends(auth.require_auth)])
def dati(): ...
```

`ambito` entra nella derivazione del segreto: due prodotti con la stessa password
non accettano i reciproci cookie.

Variabili lette: `DASHBOARD_PASSWORD` (se manca, auth **disattivata** — solo
sviluppo, loggato come warning), `SESSION_SECRET` (opzionale, sostituisce la
password nella derivazione), `COOKIE_SECURE` (`1` di default).

Rate limit login: 5 tentativi al minuto per IP.

## `sentira_core.emailer`

Resend + template Jinja2 + `Idempotency-Key` + cap giornaliero.

```python
from sentira_core import emailer

emailer.invia("cliente@esempio.it", "Oggetto", testo="**Ciao**",
              idempotency_key="promemoria-2026-08-03-veicolo-42")
```

Il **contatore del cap** va iniettato, perché dove persisterlo dipende dallo
schema dell'applicazione:

```python
def _contatore(chiave, incrementa):
    with db.get_session() as s:
        riga = s.get(db.SyncState, chiave)
        attuale = int(riga.value) if riga and riga.value else 0
        if incrementa:
            if riga: riga.value = str(attuale + 1)
            else:    s.add(db.SyncState(key=chiave, value="1"))
            s.commit()
        return attuale

emailer.usa_contatore(_contatore)
```

Senza contatore il cap non viene applicato, e il modulo lo dice nei log una volta
sola: meglio inviare senza cap che non inviare per una dipendenza mancante.

Se `EMAIL_PROVIDER_API_KEY` o `EMAIL_FROM` mancano, `invia()` restituisce `None`
senza sollevare — un'applicazione con l'email non ancora configurata deve poter
girare lo stesso.

`send_html_email` e `render_template` restano come alias dei nomi precedenti.

## `sentira_core.notify`

Notifiche su Discord che **non sollevano mai**: sarebbe il colmo che l'allarme
causasse il guasto che deve segnalare.

```python
from sentira_core import notify

notify.allarme_job("Lead Hunter", "scrape", "completed_empty", entrati=10, usciti=0)
```

"Concluso senza risultati" è uno stato a sé, non un successo: un job che riceve
dati e non ne produce ha quasi sempre un problema silenzioso a monte.

## `sentira_core.errorreport`

Notifica su Discord (webhook dedicato, separato da `notify`) i 500 inaspettati
delle route FastAPI, deduplicati: il primo colpo manda un messaggio, i
successivi nella stessa finestra aggiornano lo stesso messaggio con un
contatore invece di spammarne uno nuovo.

```python
from sentira_core.errorreport import crea_errorreport

report = crea_errorreport(tenant="giallo")
app.middleware("http")(report.middleware)
```

Le `HTTPException` (comprese quelle sollevate a mano) non arrivano qui: sono
controllo di flusso, non bug, e Starlette le gestisce prima che risalgano al
middleware. Solo le eccezioni non gestite notificano.

Variabili lette: `DISCORD_WEBHOOK_URL_ERRORI` (vuota = solo log, nessun
invio), `ERROR_REPORT_DRY_RUN=1` (logga sempre, non manda mai — utile in
test/CI).

Deduplica in memoria (dict), finestra di 15 minuti: persa al riavvio e non
condivisa fra worker multipli. Basta a non spammare Discord, non è uno
storico — quello è il lavoro di GlitchTip quando arriverà.

## `sentira_core.sqlite`

Motore SQLite in WAL configurato per FastAPI. Le tabelle no: quelle sono di ogni
prodotto.

```python
from sentira_core.sqlite import crea_motore, crea_sessione

engine = crea_motore()               # dentro DATA_DIR, default ./data
Session = crea_sessione(engine)
Base.metadata.create_all(engine)
```

`DATA_DIR` in produzione deve puntare al volume persistente (`/app/data` su
Coolify). Se punta altrove, ogni redeploy ricrea il container e **il database
sparisce**.

PRAGMA applicati: `journal_mode=WAL` (letture concorrenti durante una scrittura),
`synchronous=NORMAL`, `foreign_keys=ON` (SQLite non le applica di default, e il
silenzio è la parte pericolosa), `busy_timeout=5000`.

## `sentira_core.ai_usage`

Formula USD con input cached, registrazione non bloccante e wrapper
`chat.completions.create`, estratti da Mauro e Rossella. Nessuna dipendenza
OpenAI aggiunta: il client viene passato dal chiamante.

```python
from functools import partial
from sentira_core import ai_usage as condiviso
from . import db

PRICING = condiviso.PRICING

def _cost_usd(model, prompt_tokens, cached_tokens, completion_tokens, cache_write_tokens=0):
    tariffa = PRICING.get(model, (0.25, 0.025, 0.0, 2.00))
    return condiviso.cost_usd(tariffa, prompt_tokens, cached_tokens, completion_tokens, cache_write_tokens)

record = partial(condiviso.record, db=db, cost_usd=_cost_usd)
complete = partial(condiviso.complete, record=record)
```

`db` espone `get_session()` e il modello `AiUsage` dell'applicazione.
I binding `partial` passano le dipendenze senza configurazione globale del core.
Schema, timestamp, fallback tariffario, riepiloghi HTTP e conversione EUR
restano nel consumer. `PRICING` contiene solo le tariffe (input, cached,
cache writes, output) identiche nei due progetti; eventuali estensioni vanno
in una copia locale.

## `sentira_core.chat`

La chat sui dati del cliente, uguale in ogni prodotto: agent loop OpenAI in
streaming SSE, validazione dei tool contro il loro schema, confine dei dati non
fidati, grafici costruiti dal database, storico, sessioni, consumo AI, e le regole
del prompt che valgono per tutti (sicurezza, verità dei numeri, formato, grafici,
domande di follow-up). L'applicazione porta **solo** i suoi strumenti e la parte
di prompt che parla del suo lavoro.

```python
from sentira_core import chat
from . import ai_usage, db

motore = chat.crea_chat(
    db=db, record=ai_usage.record,
    prompt=chat.prompt_sistema(
        identita="Ti chiami Sentira AI. Lavori per …", ambito="sul lavoro di …: …",
        rifiuto="Posso aiutarti solo su …", azioni="get_x consulta il DB; …",
        fonti="## Fonti\n- …: tool get_x.", dominio="## Regole di business\n- …"),
    strumenti=[chat.Strumento("get_x", "Cosa restituisce…", esegui=_get_x,
                              parametri={"testo": {"type": "string"}},
                              etichetta="Cerco nelle x…")],
    grafici={"x_per_mese": "X al mese"}, costruisci_grafico=_grafico,
    suggerimenti=["Quante x questo mese?"], titolo="Interroga …", descrizione="…")
app.include_router(motore.router, dependencies=protected)
```

Nel `db.py` dell'app: `ChatSession, ChatMessage = chat.modelli(Base)`, le due
tabelle sono le stesse ovunque. `esegui(args)` restituisce testo o un oggetto
JSON; `chat.grafico(titolo, dati, forma=…, serie=…, nota=…)` costruisce la
specifica che il frontend disegna. I numeri dei grafici li sceglie il database,
il modello sceglie solo **quale** grafico: un blocco grafico scritto dal modello
viene tolto dalla risposta.

Route: `POST /api/chat` (SSE), `GET /api/chat/config` (titolo, descrizione,
domande d'esempio), `GET|DELETE /api/chat/sessions`,
`GET|PATCH|DELETE /api/chat/sessions/{id}`. `motore.turno(messaggio)` fa girare
un turno senza HTTP (lo usa il confronto modelli). Il modello è
`OPENAI_MODEL_REASONING` (default `gpt-6-luna`) se l'app non passa `modello=`.

### La pagina (`web/chat`)

Stesso tag, lato frontend: la pagina completa (sessioni, conversazione, grafici)
come sorgente TSX, senza niente di specifico del cliente: i testi arrivano da
`/api/chat/config`.

```tsx
import { Chat } from "sentira-core/chat";
<Chat chiaveSessione="nomeprodotto_session_id" testata={<SidebarTrigger />} />
```

Nell'app, una volta: `transpilePackages: ["sentira-core"]` in `next.config.ts` e
`@source "../../node_modules/sentira-core/web";` in `globals.css` (Tailwind non
guarda in `node_modules`). Dipendenze attese dall'app: `react-markdown`,
`remark-gfm`, `remark-breaks`, `recharts`, `motion`, `lucide-react`, `sonner`.
La grafica usa i token e le classi del tema Sentira (`accent-rail`, `led`,
`tick-corners`…): un'app senza perde le decorazioni, non le funzioni.

### Cambiare la chat in tutti i prodotti

1. Modifica qui (motore o `prompt_sistema` in Python, `web/chat` per la pagina),
   test con `.venv/bin/python -m pytest tests/ -q`.
2. Nuovo tag (`v8`, …) e versione in `pyproject.toml`, `package.json`, `__init__.py`.
3. In ogni app: il tag in `requirements.txt` e
   `npm install https://github.com/SentiraAI/sentira-core/archive/refs/tags/v8.tar.gz`
   in `frontend/`, poi test, build e deploy come sempre.

Le regole di business di un cliente restano nel suo `src/chat.py` (o nei file
`prompts/` di Lead Hunter): qui va solo ciò che vale per tutti.

## Sviluppo

```bash
python3 -m venv .venv && .venv/bin/pip install -e . pytest
.venv/bin/python -m pytest tests/ -q
```

I test non toccano mai la rete: `httpx` viene sostituito. Mandare una email vera
da una suite di test significa, prima o poi, mandarla a un cliente.

## Versioni

I progetti puntano a un tarball di tag (`v7`), mai a `main`: una modifica qui non deve
arrivare in produzione su tutti i clienti nello stesso istante.

La numerazione dei tag di distribuzione è distinta dalla versione Python:
`v4` corrisponde a `1.2.0`, `v5` a `1.3.0`, `v7` a `1.4.0` (chat).
Confronto, criteri di ammissione e passaggi di aggiornamento:
[migrazione v5](docs/migrazione-v5.md).

## Licenza

MIT.
