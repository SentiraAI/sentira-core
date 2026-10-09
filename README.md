# sentira-core

Il codice comune ai prodotti [Sentira](https://github.com/SentiraAI): auth a
password singola, invio email, notifiche operative, configurazione SQLite, consumo AI,
chat sui dati del cliente (backend Python + pagina React).

Qui vive **solo** ciò che era già identico in più progetti e che sbagliare costa.
Niente logica di business, niente schemi di dati, niente che riguardi un cliente.

```bash
pip install "sentira-core @ https://github.com/SentiraAI/sentira-core/archive/refs/tags/v7.tar.gz"
npm install https://github.com/SentiraAI/sentira-core/archive/refs/tags/v7.tar.gz   # frontend (web/)
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
schema dell'applicazione. Con una tabella chiave/valore (colonne `key`, `value`):

```python
emailer.usa_contatore_kv(db.get_session, db.SyncState)
```

Altrimenti `emailer.usa_contatore(fn)`, con `fn(chiave, incrementa) -> conteggio`.
Il giorno del cap è quello di Roma: si azzera a mezzanotte italiana, non UTC.

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
allinea_schema(engine, Base)         # colonne e indici nuovi su un DB esistente
```

`allinea_schema` è tutta la migrazione senza Alembic: confronta il modello col
DB e aggiunge le colonne e gli indici mancanti. Il default scalare del modello
diventa il `DEFAULT` SQL (le righe vecchie non restano NULL); una colonna NOT
NULL senza default resta fuori con un warning, perché SQLite non la sa aggiungere.

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

Il **modello di default** di tutti i prodotti è `ai_usage.MODELLO_DEFAULT`, e si
legge con `ai_usage.modello("OPENAI_MODEL_REASONING")` (o un'altra variabile):
cambiare modello a tutti è cambiare quella costante e spostare il pin.

**Risposte strutturate.** Due forme, ognuna con il suo binding `partial` come
`complete`:

```python
chiama_tool = partial(condiviso.chiama_tool, record=record)

args = chiama_tool(client, "extract", model=model, tool=_TOOL, messages=[...],
                   max_completion_tokens=3000)       # dict, o None se la tool non è stata chiamata
dati = condiviso.leggi_json(complete(client, "insights", model=model,
                            response_format={"type": "json_object"}, ...))
```

`chiama_tool` forza la tool e mette da sé `reasoning_effort="none"`: con i
modelli gpt-5.6/gpt-6 le function tool funzionano solo così, e ometterlo dà un
400 a ogni chiamata (è successo due volte, in due app). Se un modello futuro
rifiuta il parametro, riprova una volta senza. Un JSON malformato o troncato
solleva `ValueError`, come `leggi_json` quando la risposta non contiene un
oggetto. Budget, effort delle altre chiamate e prompt restano nell'app.

## `sentira_core.web`

Serve l'export statico di Next.js dalla stessa app FastAPI, da montare **per
ultimo** (è un catch-all):

```python
from sentira_core.web import monta_frontend
monta_frontend(app)                  # STATIC_DIR, default ./static
```

`/x` cerca `x`, `x.html`, `x/index.html`, poi `404.html`. Una `/api/...` che non
esiste risponde 404 JSON. Ogni percorso deve restare dentro la cartella: senza
quel controllo `/%2e%2e/data/app.db` scaricava il database.

`proteggi(app)`, subito dopo `FastAPI(...)`, mette su ogni risposta gli header
di sicurezza (CSP, HSTS, nosniff, niente iframe, COOP, `no-store` sulle `/api`)
e rifiuta le scritture che un browser dichiara partite da un'altra origine
(`Sec-Fetch-Site`): SameSite=Lax del cookie non ferma gli altri `*.sentira.tech`.

## `sentira_core.scheduler`

Un solo scheduler APScheduler per processo, sul fuso di Roma, spento con
`DISABLE_SCHEDULER=1`. L'app registra i job, il resto è qui:

```python
from sentira_core import scheduler

def _registra(s):
    s.add_job(scheduler.protetto("scrape", scrape.run), CronTrigger(hour=6), id="scrape")

scheduler.avvia(_registra, report=report)   # nel lifespan; report = crea_errorreport(...)
scheduler.ferma()
scheduler.prossime("automation-")           # {id: prossima esecuzione ISO}
```

`protetto(nome, fn)`: una sola esecuzione alla volta per nome, eccezione
loggata e mandata a errorreport, mai propagata allo scheduler.

## `sentira_core.tempo` e `sentira_core.env`

`tempo.oggi_roma()` è il giorno di Roma (il container gira in UTC: `date.today()`
cambiava giorno alle 2 di notte), `tempo.adesso_utc()` l'istante da scrivere
nelle colonne `DateTime`.

`env.valore/flag/intero(nome, default)` leggono una variabile togliendo il
commento in coda e le virgolette dei `.env` scritti a mano (`ORA=8  # ora`
faceva crashare `int()` all'avvio); il vuoto vale come assente.
`env.configura_logging()` usa `LOG_LEVEL`. Non per i segreti.

## `sentira_core.serie`

Il calendario delle dashboard, con i periodi vuoti a zero:

```python
from sentira_core import serie
serie.periodi(da, a, "settimana")            # [lunedì, lunedì, …], vuoti compresi
serie.per_periodo(date_, da, a, "mese")     # {primo del mese: n}, in ordine
serie.inizio(d, "settimana")                 # il lunedì di d
serie.conta(valori, top=8)                   # [{"nome", "n"}], la forma di chat.grafico
```

Passi: `giorno`, `settimana` (dal lunedì), `mese` (dal primo). Accetta `date` e
`datetime`. Query, etichette e forma dei punti restano nell'app.

## `sentira_core.rete`

Per scaricare da un URL che arriva da fuori (un banner, una landing, un link in
una email):

```python
from sentira_core import rete
p = rete.scarica(url, timeout=15, max_byte=5_000_000)   # p.url, p.tipo, p.contenuto, p.testo
rete.controlla(url)                                     # ValueError se non è pubblico
```

Ogni redirect è controllato **prima** di partire: un link verso
`169.254.169.254`, `127.0.0.1` o la rete dei container solleva `ValueError`
(SSRF). Il corpo si ferma a `max_byte`. Errori di rete e 4xx/5xx sono
`httpx.HTTPError`. Ridurre l'HTML a testo resta nell'app (BeautifulSoup non è
una dipendenza del core).

## `sentira_core.testing`

Per `tests/conftest.py` delle app: `isola_ambiente(prefisso, segreti=…, valori=…)`
prima di importare l'app (DATA_DIR temporanea, scheduler spento, segreti tolti,
`.env` locale ignorato), `db_in_memoria(modulo_db, dopo=seed)` come fixture,
`finto_openai(monkeypatch, risposte)` + `chunk`/`chiamata`/`eventi_sse` per la chat.

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

L'app la prepara come ogni altro pezzo di `web/` (sotto, «Frontend condiviso»).
Dipendenze in più per la chat: `react-markdown`, `remark-gfm`, `remark-breaks`.
Le classi della grafica (`accent-rail`, `led`, `tick-corners`…) stanno in
`stili.css`.

### Cambiare la chat in tutti i prodotti

1. Modifica qui (motore o `prompt_sistema` in Python, `web/chat` per la pagina),
   test con `.venv/bin/python -m pytest tests/ -q`.
2. Nuovo tag (`v9`, …) e versione in `pyproject.toml`, `package.json`, `__init__.py`.
3. In ogni app: il tag in `requirements.txt` e
   `npm install https://github.com/SentiraAI/sentira-core/archive/refs/tags/v9.tar.gz`
   in `frontend/`, poi test, build e deploy come sempre.

Le regole di business di un cliente restano nel suo `src/chat.py` (o nei file
`prompts/` di Lead Hunter): qui va solo ciò che vale per tutti.

## Frontend condiviso (`web/`)

Ciò che è uguale nei frontend Next.js dei prodotti, come sorgente TSX che l'app
compila. Nell'app restano i valori dei token (il colore del brand), il logo, le
voci di menu, l'intestazione e le decorazioni proprie.

| Export | Cosa |
|---|---|
| `sentira-core/api` | `createClient()`, `request()`, `getJson<T>()`, `postJson<T>()`, `useApi<T>(url)`, `ApiError`, `messaggio(e, fallback)`, `leggiSSE(res)`. 401 → `/login`, `detail` di FastAPI (anche la lista di Pydantic) come testo, pagine HTML e rete assente come messaggio leggibile |
| `sentira-core/formato` | `parseUtc` (il backend manda UTC senza offset), `dataRelativa`, `data(iso, stile)` (`breve`, `numerica`, `media`, `mediaOra`), `numero`, `euro`, `plurale`. Solo `Intl` |
| `sentira-core/motion` | `FadeIn`, `StaggerList`, `AnimatedNumber` (in formato italiano), `PageTransition` |
| `sentira-core/ui` | `cn`, `useIsMobile`, `EmptyState`, `ErrorState`, `LoadingState`, `KpiCard`, `Conferma` (al posto di `window.confirm`), `ChartTooltip`, `coloreSerie(i)`. Accanto, un file ciascuno, i componenti shadcn (`web/ui/button.tsx`…) |
| `sentira-core/auth` | `AuthGuard` (sblocca solo con `autenticato: true`), `esci()` |
| `sentira-core/layout` | `Providers`, `Login`, `ErrorPage`, `NotFound`, `ThemeToggle`, `MobileBottomNav`, `type NavItem`, `titoloSezione`, `useConteggio<T>(path)` |
| `sentira-core/chat` | la pagina chat (sopra) |
| `sentira-core/stili.css` | `@theme inline` (token → utility, comprese sidebar e grafici), `tw-animate-css`, `@layer base`, le classi usate dai componenti |

Nell'app, una volta:

- `next.config.ts`: `transpilePackages: ["sentira-core"]`.
- `globals.css`: `@import "tailwindcss";`, poi `@import "sentira-core/stili.css";` e
  `@source "../../node_modules/sentira-core/web";` (Tailwind non guarda in
  `node_modules`), poi i valori dei token in `:root` e `[data-theme="light"]`:
  l'elenco è in testa a `stili.css`.
- `tsconfig.json`, in `paths` prima di `"@/*"`:
  `"@/components/ui/*": ["./node_modules/sentira-core/web/ui/*"]`. Gli import
  `@/components/ui/button` restano com'erano e arrivano qui; `src/components/ui/`
  non esiste più. Funziona con il build di Next 16 (Turbopack).
- Dipendenze: le `peerDependencies` di `package.json`.

Le pagine di contorno diventano poche righe:

```tsx
// app/error.tsx
"use client";
import { ErrorPage } from "sentira-core/layout";
export default ErrorPage;

// app/login/page.tsx
<Login logo={<Logo size={48} className="mx-auto mb-4" />} titolo="Lead Hunter"
  sottotitolo="Accedi alla tua inbox lead" sfondo={<ParticlesCanvas />} />

// app/(protected)/layout.tsx
<AuthGuard><SidebarProvider><AppSidebar /> … <MobileBottomNav items={NAV_ITEMS} /></SidebarProvider></AuthGuard>
```

Dentro `web/`: import relativi (niente `@/`, che è dell'app), `"use client"` in
cima ai file con hook. Un componente shadcn nuovo si aggiunge in `web/ui/`, con
`./utils` al posto di `@/lib/utils`. Le varianti `data-horizontal:` delle versioni
più recenti di shadcn vanno verificate su `@base-ui/react` 1.6 prima di adottarle.
Arriva alle app con lo stesso giro della chat: nuovo tag, `npm install` del tarball.

## Sviluppo

```bash
python3 -m venv .venv && .venv/bin/pip install -e . pytest
.venv/bin/python -m pytest tests/ -q
```

I test non toccano mai la rete: `httpx` viene sostituito. Mandare una email vera
da una suite di test significa, prima o poi, mandarla a un cliente.

## Versioni

I progetti puntano a un tarball di tag (`v9`), mai a `main`: una modifica qui non deve
arrivare in produzione su tutti i clienti nello stesso istante.

La numerazione dei tag di distribuzione è distinta dalla versione Python:
`v4` corrisponde a `1.2.0`, `v5` a `1.3.0`, `v7` a `1.4.0` (chat), `v8` a `1.5.0`
(piattaforma: web, scheduler, tempo, env, testing, allinea_schema; frontend condiviso), `v9` a `1.6.0`
(risposte strutturate dell'AI, serie, rete), `v10` a `1.7.0` (sicurezza: `proteggi`,
template email in sandbox, HTML grezzo neutralizzato, limite globale ai login,
algoritmo JWT fisso, niente URL con segreti nei log, niente menzioni Discord).
Confronto, criteri di ammissione e passaggi di aggiornamento:
[migrazione v5](docs/migrazione-v5.md).

## Licenza

MIT.
