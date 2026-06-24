# Guida all'Installazione

Questa guida ti accompagna nell'installazione del **GDO Supermarket Scraper**. 
Il metodo **fortemente consigliato** ed ufficiale è tramite **Docker**, che garantisce un ambiente pulito e ti evita di dover configurare Python, dipendenze grafiche o motori OCR complessi (come Tesseract) sul tuo sistema.

Se sei uno sviluppatore e desideri contribuire al codice sorgente, troverai le istruzioni per l'installazione manuale in fondo a questa pagina.

---

## 1. Installazione tramite Docker Desktop (Interfaccia Grafica)

Se preferisci usare il mouse e non vuoi toccare il terminale, questo è il metodo più rapido.

1. **Installa Docker Desktop** in base al tuo sistema operativo: [Windows](https://docs.docker.com/desktop/setup/install/windows-install/) | [macOS](https://docs.docker.com/desktop/setup/install/mac-install/) | [Linux](https://docs.docker.com/desktop/setup/install/linux/)
2. Apri Docker Desktop.
3. Nella barra di ricerca in alto, digita `aleemont/supermarket-scraper:latest` e clicca su **Pull** per scaricare l'immagine.
4. Vai nella scheda **Images** a sinistra, trova l'immagine appena scaricata e clicca il pulsante **"▶ Run"**.
5. Nella finestra che si apre, espandi la sezione **"Optional settings"** e compila:
   - **Container name:** `gdo-scraper` (o un nome a piacere).
   - **Ports:** scrivi `8000` sotto "Host port" (in corrispondenza di 8000/tcp).
   - **Volumes:** seleziona una cartella vuota dal tuo PC (es. una cartella `storage` sul Desktop) sotto "Host path", e scrivi ESATTAMENTE `/app/storage` sotto "Container path".
   - **Environment variables:** clicca il `+` per aggiungere:
     - `GEMINI_API_KEY` = *inserisci_la_tua_chiave* (facoltativo, per l'AI)
     - `ANTHROPIC_API_KEY` = *inserisci_la_tua_chiave* (facoltativo, per l'AI)
     - `PYTHONUNBUFFERED` = `1` (necessario per visualizzare correttamente i log)
     - *(Opzionale: Supabase)*: per usare il DB in cloud aggiungi `DB_ENGINE` = `supabase`, `SUPABASE_URL` = *tuo_url*, `SUPABASE_KEY` = *tua_chiave*.
6. Clicca **Run**.
7. Apri il browser all'indirizzo [http://localhost:8000](http://localhost:8000) e usa l'app!

---

## 2. Installazione tramite Docker CLI (Riga di Comando)

Se ami il terminale o vuoi automatizzare il processo, usa `docker-compose`.

1. Crea una cartella vuota sul tuo PC ed entraci con il terminale.
2. Crea un file chiamato `docker-compose.yml` e incollaci questo contenuto:
```yaml
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
3. Crea un file `.env` accanto al `docker-compose.yml` e compila le variabili:
```ini
GEMINI_API_KEY="la_tua_chiave_gemini"
ANTHROPIC_API_KEY="la_tua_chiave_claude"
CLAUDE_MODEL_NAME="claude-sonnet-4-6"
PYTHONUNBUFFERED=1

# Storage Engine (Opzionale: di default usa SQLite locale)
# DB_ENGINE="supabase"
# SUPABASE_URL="https://il-tuo-id.supabase.co"
# SUPABASE_KEY="la-tua-chiave-api-supabase"
```
4. **Avvia la Dashboard**: esegui `docker-compose up -d`. Visita http://localhost:8000.
5. **Avvia la TUI Interattiva**: esegui `docker-compose run --rm tui`.

---

## 3. Installazione Manuale / Sviluppatori (Sorgente)

L'installazione nativa/manuale è consigliata **solo** se vuoi modificare il codice sorgente del progetto.
*Per gli utenti Windows, l'utilizzo di WSL (Windows Subsystem for Linux) è l'unica modalità di installazione manuale supportata.*

### Prerequisiti
* **Git** per clonare il repository. (Richiede un Personal Access Token GitHub poiché il repo è privato).
* **Python 3.10+**.
* **Tesseract OCR** (facoltativo, per i fallback di OCR di alcuni volantini).
  - Ubuntu/WSL: `sudo apt install tesseract-ocr tesseract-ocr-ita`
  - macOS: `brew install tesseract tesseract-lang`
* **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Installazione

1. **Clona la repository**:
   ```bash
   git clone https://<IL_TUO_GITHUB_TOKEN>@github.com/aleemont1/gdoscraper.git
   cd gdoscraper
   ```

2. **Crea l'ambiente virtuale ed installa le dipendenze**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```

3. **Copia il file delle variabili d'ambiente**:
   ```bash
   cp .env.example .env
   # Modifica il .env con le tue chiavi API
   ```

4. **Avvia l'applicazione**:
   - Dashboard: `uv run python dashboard.py`
   - TUI: `uv run python run_interactive.py`
   - Test unitari: `uv run pytest`
