"""sentira-core — il codice comune ai prodotti Sentira.

Qui vive solo ciò che era **identico** in più progetti e che sbagliare costa:
l'auth a password singola, l'invio email, le notifiche di guasto, la
configurazione di SQLite, il tracking del consumo AI. Niente logica di business, niente schemi di dati,
niente che riguardi un cliente specifico.

    sentira_core.identita  identita' via Cloudflare Access: JWT + ruolo
    sentira_core.auth      auth a password singola con cookie firmato HMAC
    sentira_core.ai_usage  costo token, consumo non bloccante, risposte strutturate
    sentira_core.chat      chat sui dati: motore SSE, tool, grafici, regole del prompt
    sentira_core.web       frontend statico Next.js, protetto dal path traversal
    sentira_core.scheduler APScheduler: avvio, spegnimento, job protetti
    sentira_core.tempo     oggi/adesso sul fuso di Roma
    sentira_core.env       variabili d'ambiente tolleranti, logging
    sentira_core.serie     periodi con i vuoti a zero e conteggi per i grafici
    sentira_core.rete      download da URL esterni, solo verso indirizzi pubblici
    sentira_core.testing   aiuti per i test delle app

La regola per aggiungere qualcosa qui: **deve già esistere identico in almeno
due progetti**. Codice messo qui "perché prima o poi servirà" diventa un vincolo
per tutti senza essere utile a nessuno.
"""

__version__ = "1.8.0"
