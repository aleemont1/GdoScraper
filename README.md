# GDO Supermarket Scraper: Pipeline ETL & Visual Parsing

GDO Scraper è una pipeline ETL (Extract, Transform, Load) modulare, deterministica e ad alta precisione in Python progettata per l'estrazione, la normalizzazione e la persistenza di dati promozionali (prodotti, brand, prezzi, sconti, validità) da catene della Grande Distribuzione Organizzata (GDO) italiana.

Il sistema gestisce l'estrazione dati sia da API REST dinamiche (**Coop**, **Dpiù**) sia tramite visual parsing avanzato di volantini PDF geometrici (**Conad**, **IN'S**), esportando i record in un database SQLite centralizzato e salvando i ritagli delle immagini dei prodotti ripuliti da sovrapposizioni testuali.


Per consultare le guide dettagliate, visita la directory `docs/`:
* [Guida all'Installazione Avanzata](docs/installation.md)
* [Architettura del Sistema e Algoritmi](docs/architecture.md)
* [Guida ai Comandi CLI](docs/cli_reference.md)
* [Guida all'Interfaccia TUI](docs/tui_reference.md)
* [Guida alla Dashboard Web](docs/dashboard_reference.md)

---

## 1. Architettura e Flusso Dati

La pipeline è strutturata secondo lo **Strategy Pattern**, disaccoppiando la definizione dei driver di scraping dall'orchestratore principale:

```
                  AbstractSupermarketDriver [core/base_driver.py]
                                 ▲
                ┌────────────────┴────────────────┐
                │                                 │
 AbstractPdfFlyerDriver                AbstractApiSupermarketDriver
[core/base_pdf_driver.py]               [core/base_driver.py]
        ▲                                         ▲
        ├──────────────────────┐                  ├──────────────────────┐
        │                      │                  │                      │
ConadSupermarketDriver   INSSupermarketDriver  CoopSupermarketDriver  DpiuSupermarketDriver
```

### Componenti Principali:
* **`BasePdfLayoutSegmenter` (`core/base_pdf_segmenter.py`)**: Algoritmo di segmentazione spaziale basato sulla proiezione dell'istogramma dei caratteri sull'asse X per identificare le colonne di testo primarie. Esegue uno splitting verticale (Y-splitting) all'interno di ciascuna colonna isolata con un filtro gutter verticale (minimo 4pt) ed effettua il pairing logico tra i blocchi descrittivi e i rispettivi prezzi.
* **`AbstractPdfFlyerDriver` (`core/base_pdf_driver.py`)**: Gestisce il flusso di parsing dei PDF geometrici, il caching locale dei file scaricati per evitare richieste ridondanti e l'algoritmo di visual cropping.
* **Ritaglio Visivo Bounding-Box (`conad_driver.py` / `ins_driver.py`)**: Individua gli oggetti raster nativi (`page.images`) all'interno del PDF che ricadono nella bounding box geometrica della cella del prodotto, ritagliando l'immagine raster originale per isolare l'illustrazione del prodotto ed escludere etichette e scritte. Include un fallback automatico a griglia snappata uniforme in assenza di raster.
* **Multiprocessing a livello di Flyer**: Sfrutta un `ProcessPoolExecutor` per parallelizzare il parsing di molteplici volantini PDF su core CPU indipendenti, ottimizzando i compiti CPU-bound di text extraction e rendering grafico.
* **UPSERT Idempotente (`storage/database.py`)**: Il database SQLite impone un vincolo di unicità composto `PRIMARY KEY (supermarket, store_id, offer_id)`, garantendo l'assoluta idempotenza dei dati inseriti.

---

## 2. Installazione tramite Docker (Metodo Consigliato)

Per garantire un'installazione riproducibile, senza conflitti e funzionante su qualsiasi computer, consigliamo caldamente di utilizzare **Docker**. In questo modo non dovrai installare Python o gestire dipendenze di sistema complesse come Tesseract o librerie PDF.

### 2.1 Requisiti Preliminari

1. **Installa Docker e Docker Desktop** in base al tuo sistema operativo:
   - [Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
   - [macOS](https://docs.docker.com/desktop/setup/install/mac-install/)
   - [Linux](https://docs.docker.com/desktop/setup/install/linux/) (o semplicemente il motore Docker tramite le [istruzioni ufficiali](https://docs.docker.com/engine/install/))
2. **Crea un account gratuito su Docker Hub**: Registrati su [hub.docker.com](https://hub.docker.com/).
3. **Fai il login dal terminale**: Apri un terminale (o il prompt dei comandi) ed esegui il login con le tue credenziali:
   ```bash
   docker login
   ```

### 2.2 Avvio Rapido dell'Applicazione

Non è necessario clonare l'intero codice sorgente! Ti basterà creare una cartella vuota sul tuo computer e, al suo interno, creare un file chiamato `docker-compose.yml` copiandoci questo contenuto:

```yaml
version: '3.8'

services:
  dashboard:
    image: aleemont/supermarket-scraper:latest
    container_name: gdo_scraper_dashboard
    ports:
      - "8000:8000"
    volumes:
      - ./storage:/app/storage
    env_file:
      - .env
    restart: unless-stopped

  scraper:
    image: aleemont/supermarket-scraper:latest
    container_name: gdo_scraper_cli
    volumes:
      - ./storage:/app/storage
    env_file:
      - .env
    profiles:
      - cli

  tui:
    image: aleemont/supermarket-scraper:latest
    container_name: gdo_scraper_tui
    volumes:
      - ./storage:/app/storage
    env_file:
      - .env
    stdin_open: true
    tty: true
    command: python run_interactive.py
    profiles:
      - cli
```

### 2.3 Configurazione Ambiente (`.env`)
Nel progetto è presente un file modello chiamato `.env.example` con le istruzioni dettagliate.
Copia/rinomina questo file in `.env` e compila le variabili interne con le tue chiavi API (se desideri attivare le funzioni di Intelligenza Artificiale). 

Se stai usando Docker senza aver clonato l'intero progetto, crea un file `.env` vicino al tuo `docker-compose.yml` e copiacci dentro questo scheletro:
```ini
# API Key per i modelli AI (Opzionale)
GEMINI_API_KEY="la_tua_chiave_gemini"
ANTHROPIC_API_KEY="la_tua_chiave_claude"

# Scelta del modello Claude (rimuovi il commento da quello desiderato)
#CLAUDE_MODEL_NAME="claude-haiku-4-5"
CLAUDE_MODEL_NAME="claude-sonnet-4-6"
#CLAUDE_MODEL_NAME="claude-opus-4-8"
```

### 2.4 Comandi di Avvio

Una volta posizionato col terminale all'interno della cartella dove hai salvato i due file, puoi lanciare il progetto a piacimento:

* **Avvia la Dashboard Web in background**: 
  ```bash
  docker-compose up -d
  ```
  La dashboard sarà visibile dal tuo browser all'indirizzo [http://localhost:8000](http://localhost:8000).

* **Avvia l'Interfaccia Testuale Interattiva (TUI)**:
  ```bash
  docker-compose run --rm tui
  ```

* **Esegui uno scraping manuale da riga di comando (CLI)**:
  ```bash
  docker-compose run --rm scraper python main.py --supermarket coop --store-id 0315
  ```

Tutti i dati processati, il database locale SQLite (`promotions.db`) e le immagini dei prodotti verranno salvati in modo permanente all'interno di una cartella `storage/` creata in automatico sul tuo computer.

> **Sei uno sviluppatore e vuoi lavorare sul codice sorgente in locale?**  
> Consulta la [Guida all'Installazione Avanzata (Sorgente)](docs/installation.md) per istruzioni su Linux, macOS o Windows (tramite WSL) usando Git e `uv`.

---

## 3. Script di Controllo Interattivo TUI (`run_interactive.py`)

È presente un controller interattivo da terminale per facilitare i test e la configurazione rapida dei parametri senza dover inserire comandi complessi:

```bash
./run_interactive.py
```
*(Su Windows: `.venv\Scripts\python run_interactive.py`)*

<!-- Sostituire questo placeholder con uno screenshot della schermata principale della TUI (run_interactive.py) in esecuzione nel terminale -->
![TUI Control Panel Placeholder](docs/images/tui_screenshot.png)

### Funzionalità della TUI:
1. **Scraping Coop**: Avvio guidato per scaricare le offerte tramite API REST (es. inserendo la città o il codice negozio `0315`).
2. **Scraping Conad**: Configurazione semplificata di GPS, raggio di ricerca, limiti dei volantini e parallelismo.
3. **Avvio Dashboard**: Esecuzione del server web per l'interfaccia di visualizzazione SPA.
4. **Analisi Database**: Genera report dettagliati sulle offerte salvate con statistiche e anomalie rilevate.
5. **Developer Tools**: Reset del DB, pulizia delle cache (immagini/PDF) ed esecuzione di benchmark di velocità (sequenziale vs parallelo).

---

## 4. Riferimento CLI (`main.py`)

La pipeline può essere eseguita direttamente da riga di comando tramite `main.py`:

```bash
.venv/bin/python main.py --supermarket [coop|conad|ins|dpiu] --store-id [store_id|coords] [options]
```

### Parametri Principali:
* `--supermarket`: Catena target (`coop`, `conad`, `ins`, `dpiu`, `manual`).
* `--store-id`: Codice punto vendita (es. `0315` Coop, `005635` Conad) o coordinate GPS `lat,lon` (es. `44.1396,12.2464`).
* `--radius`: Raggio di ricerca in km (default `5`).
* `--parallel`: Abilita il multiprocessing per il parsing dei volantini PDF.
* `--engine`: Motore di elaborazione PDF/OCR (`AUTO`, `GEMINI`, `CLAUDE`, `LOCAL`).

#### Esempio: Scraping Conad via GPS in Multiprocessing
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396,12.2464" --parallel
```

---

## 5. Visual Verification Dashboard (`dashboard.py`)

La dashboard web ti permette di visionare l'esito dello scraping, i log di esecuzione in tempo reale e di eseguire audit di qualità sui dati:

```bash
.venv/bin/python dashboard.py
```
* **URL Locale**: [http://localhost:8000](http://localhost:8000)

<!-- Sostituire questo placeholder con uno screenshot della dashboard principale (http://localhost:8000) mostrando la mappa dei negozi, la selezione volantini e la console dei log -->
![Dashboard Principal Interface Placeholder](docs/images/dashboard_main.png)

<!-- Sostituire questo placeholder con uno screenshot del pannello di audit inferiore della dashboard, evidenziando il funzionamento dello zoom ad alta risoluzione al passaggio del mouse sopra un prodotto ritagliato -->
![Dashboard Audit Grid & Zoom Placeholder](docs/images/dashboard_audit.png)

---

## 6. Generazione Automatica della Documentazione

Il progetto include uno script per generare automaticamente la documentazione tecnica delle API in formato HTML (estraendo i docstrings delle classi e dei metodi tramite **`pdoc`**):

```bash
# Esegui lo script di generazione
./docs/generate.sh
```
La documentazione HTML verrà creata nella cartella `docs/api/`. Puoi visualizzarla aprendo il file `docs/api/index.html` in qualunque browser.
