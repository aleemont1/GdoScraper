# Guida all'Installazione

Questa guida spiega come installare il **GDO Supermarket Scraper** su Windows (tramite WSL), Linux e macOS, descrivendo i requisiti di sistema ed i passaggi di configurazione.

---

## 1. Requisiti di Sistema

Prima di procedere con l'installazione, assicurati di avere i seguenti componenti installati sul tuo sistema:

### A. Git (Obbligatorio)
È necessario avere **Git** installato per clonare il repository.
* **Linux / WSL**: `sudo apt install git`
* **macOS**: `brew install git`

> [!IMPORTANT]
> Il repository è privato (`github.com/aleemont1/gdoscraper`). Per poterlo clonare è necessario generare un **Personal Access Token (PAT)** di GitHub con i permessi di lettura per i repository privati (`repo` o `contents:read`).

### B. Python 3.10+
Il codice è ottimizzato e testato per le versioni recenti di Python (consigliato **Python 3.11** o superiore).
* **Linux / WSL / macOS**: Installa tramite il gestore di pacchetti di sistema.

### C. Tesseract OCR (Opzionale, richiesto per fallback OCR/IN'S)
Il driver per **IN'S Mercato** ed i meccanismi di fallback OCR offline utilizzano Tesseract per estrarre testi dalle immagini dei volantini.
* **Linux / WSL (Ubuntu/Debian)**:
  ```bash
  sudo apt update
  sudo apt install -y tesseract-ocr tesseract-ocr-ita
  ```
* **macOS (via Homebrew)**:
  ```bash
  brew install tesseract tesseract-lang
  ```

### D. Gestore di pacchetti `uv` (Consigliato)
Il progetto utilizza **`uv`**, un gestore di pacchetti Python estremamente rapido sviluppato da Astral.
* **Linux / WSL / macOS**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

---

## 2. Passaggi per l'Installazione

### A. Windows (Tramite WSL - Unica modalità supportata)

Per gli utenti Windows, **l'utilizzo di WSL (Windows Subsystem for Linux) è l'unica modalità di installazione supportata**. L'ambiente Linux WSL garantisce stabilità e facilità di installazione delle dipendenze grafiche e di Tesseract OCR.

1. **Installa WSL** (se non presente) aprendo PowerShell come amministratore ed eseguendo:
   ```powershell
   wsl --install
   ```
   *Nota: Di default verrà installata la distribuzione Ubuntu. Riavvia il computer se richiesto.*

2. **Apri la shell di WSL (Ubuntu)** ed installa i requisiti di sistema:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv git tesseract-ocr tesseract-ocr-ita curl
   ```

3. **Installa il gestore di pacchetti `uv`** all'interno di WSL:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.local/bin/env
   ```

4. **Clona la repository** (sostituisci `<IL_TUO_GITHUB_TOKEN>` con il tuo token PAT generato):
   ```bash
   git clone https://<IL_TUO_GITHUB_TOKEN>@github.com/aleemont1/gdoscraper.git
   cd gdoscraper
   ```

5. **Configura l'ambiente virtuale ed installa le dipendenze**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```

---

### B. Linux / macOS (Nativo)

1. **Clona il repository** utilizzando il proprio GitHub Token PAT per l'autenticazione:
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

---

## 3. Configurazione delle Variabili d'Ambiente

Il sistema supporta l'integrazione con modelli di intelligenza artificiale per l'audit visivo ed il fallback OCR (Gemini e Claude). Per configurare le chiavi API:

1. Crea un file nominato `.env` nella radice del progetto.
2. Aggiungi le seguenti chiavi:
   ```ini
   # API Keys per gli Audit ed i Fallback OCR (Facoltativo)
   GEMINI_API_KEY="la_tua_gemini_api_key_qui"
   ANTHROPIC_API_KEY="la_tua_anthropic_api_key_qui"
   ```

---

## 4. Verifica dell'Installazione

Per verificare che l'installazione sia andata a buon fine ed eseguire la suite di test unitari:

```bash
# Attiva l'ambiente virtuale se non è già attivo
source .venv/bin/activate

# Esegui i test unitari
pytest
```
Se tutti i test passano, il sistema è pronto per essere utilizzato!
