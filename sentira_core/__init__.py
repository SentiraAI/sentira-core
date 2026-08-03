"""sentira-core — il codice comune ai prodotti Sentira.

Qui vive solo ciò che era **identico** in più progetti e che sbagliare costa:
l'auth a password singola, l'invio email, le notifiche di guasto, la
configurazione di SQLite. Niente logica di business, niente schemi di dati,
niente che riguardi un cliente specifico.

    sentira_core.auth      auth a password singola con cookie firmato HMAC
    sentira_core.emailer   invio via Resend + template Jinja2 + cap giornaliero
    sentira_core.notify    notifiche operative su Discord
    sentira_core.sqlite    motore SQLite in WAL, configurato per FastAPI

La regola per aggiungere qualcosa qui: **deve già esistere identico in almeno
due progetti**. Codice messo qui "perché prima o poi servirà" diventa un vincolo
per tutti senza essere utile a nessuno.
"""

__version__ = "1.0.0"
