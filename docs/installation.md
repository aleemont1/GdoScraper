# Guida all'Installazione

Questa guida spiega come installare il **GDO Supermarket Scraper** su Windows, Linux e macOS, descrivendo i requisiti di sistema ed i passaggi di configurazione.

---

## 1. Requisiti di Sistema

Prima di procedere con l'installazione, assicurati di avere i seguenti componenti installati sul tuo sistema:

### A. Python 3.10+
Il codice è ottimizzato e testato per le versioni recenti di Python (consigliato **Python 3.11** o superiore).
* **Linux/macOS**: Installa tramite il gestore di pacchetti di sistema o scaricalo dal sito ufficiale.
* **Windows**: Assicurati di spuntare la casella **"Add python.exe to PATH"** durante l'installazione.

### B. Tesseract OCR (Opzionale, richiesto per fallback OCR/IN'S)
Il driver per **IN'S Mercato** ed i meccanismi di fallback OCR offline utilizzano Tesseract per estrarre testi dalle immagini dei volantini.
* **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt update
  sudo apt install -y tesseract-ocr tesseract-ocr-ita
  ```
* **macOS (via Homebrew)**:
  ```bash
  brew install tesseract tesseract-lang
  ```
* **Windows**:
  1. Scarica l'installer di Tesseract per Windows da [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
  2. Esegui l'installer ed installa i dati per la lingua italiana (`ita`).
  3. Aggiungi il percorso di installazione di Tesseract (es. `C:\Program Files\Tesseract-OCR`) alle variabili di ambiente del sistema (PATH).

### C. Gestore di pacchetti `uv` (Consigliato)
Il progetto utilizza **`uv`**, un gestore di pacchetti Python estremamente rapido sviluppato da Astral.
* **Linux/macOS**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
* **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

---

## 2. Passaggi per l'Installazione

### Linux / macOS
Apri il terminale ed esegui i seguenti comandi:

1. **Clona il repository**:
   ```bash
   git clone https://github.com/tuo-username/supermarket_scraper.git
   cd supermarket_scraper
   ```
2. **Crea l'ambiente virtuale ed installa le dipendenze**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```

### Windows (PowerShell)
Apri PowerShell nella directory del progetto ed esegui:

1. **Clona il repository**:
   ```powershell
   git clone https://github.com/tuo-username/supermarket_scraper.git
   cd supermarket_scraper
   ```
2. **Crea l'ambiente virtuale ed installa le dipendenze**:
   ```powershell
   uv venv
   .venv\Scripts\Activate.ps1
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
source .venv/bin/activate # Su Windows: .venv\Scripts\Activate.ps1

# Esegui i test unitari
pytest
```
Se tutti i test passano, il sistema è pronto per essere utilizzato!
