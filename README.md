# sentira-core

Il codice comune ai prodotti [Sentira](https://github.com/SentiraAI): auth a
password singola, invio email, notifiche operative, configurazione SQLite.

Qui vive **solo** ciò che era già identico in più progetti e che sbagliare costa.
Niente logica di business, niente schemi di dati, niente che riguardi un cliente.

```bash
pip install "sentira-core @ git+https://github.com/SentiraAI/sentira-core@v1"
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
notify.riepilogo("Lead Hunter", "Buongiorno", {"alta": 3, "media": 7})
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

## Sviluppo

```bash
python3 -m venv .venv && .venv/bin/pip install -e . pytest
.venv/bin/python -m pytest tests/ -q
```

I test non toccano mai la rete: `httpx` viene sostituito. Mandare una email vera
da una suite di test significa, prima o poi, mandarla a un cliente.

## Versioni

I progetti puntano a un tag (`@v1`), mai a `@main`: una modifica qui non deve
arrivare in produzione su tutti i clienti nello stesso istante.

## Licenza

MIT.
