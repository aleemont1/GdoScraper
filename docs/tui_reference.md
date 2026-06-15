# Interfaccia TUI Interattiva (`run_interactive.py`)

Per facilitare l'utilizzo della pipeline senza dover ricordare i flag della CLI, il progetto include un pannello di controllo interattivo da terminale (TUI).

---

## 1. Avvio della TUI

Esegui lo script dalla cartella del progetto:

```bash
./run_interactive.py
```
*(In alternativa, se i permessi di esecuzione non sono impostati: `.venv/bin/python run_interactive.py`)*

---

## 2. Menu Principale e Funzionalità

All'avvio, la TUI presenta una schermata a colori con le seguenti opzioni numerate:

### `1) Scrape COOP (REST API)`
Avvia lo scraping per la catena Coop. Consente di selezionare il punto vendita tramite:
* Nome città (con geocodifica automatica)
* Coordinate GPS (`lat,lon`)
* Codice PDV diretto (es. `0315`)
* ID database Coop (es. `2560`)

### `2) Scrape CONAD (PDF/OCR)`
Consente di configurare ed avviare lo scraping di Conad:
* Inserimento della posizione (città o coordinate)
* Impostazione del raggio di ricerca dei negozi
* Limite volantini da elaborare
* Attivazione/disattivazione del multiprocessing parallelo

### `3) Start Visual verification Dashboard`
Avvia il server locale di visualizzazione e di audit visivo. Corrisponde ad eseguire `python dashboard.py` su porta 8000.

### `4) Run Database Diagnostic Report`
Interroga il database SQLite `storage/promotions.db` ed esegue un'analisi approfondita sui dati salvati:
* Numero totale di offerte nel database
* Suddivisione delle offerte per supermercato e punto vendita
* Classificazione dei prodotti per categoria merceologica
* Statistiche sui prezzi e percentuali di sconto medie
* Rilevamento di anomalie (es. prezzi non coerenti o record incompleti)

### `5) Developer & Cache Tools`
Fornisce strumenti di manutenzione per sviluppatori:
* **Reset Database**: Svuota completamente le tabelle del database SQLite.
* **Clear Images Cache**: Elimina tutti i file PNG dei prodotti ritagliati in `storage/images/`.
* **Clear PDF Cache**: Cancella i volantini memorizzati localmente in `downloads/`.
* **Run Parallel Performance Benchmark**: Esegue un benchmark comparativo per misurare i tempi di esecuzione del parsing dei PDF in modalità sequenziale contro la modalità parallela multi-processo.
