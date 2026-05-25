# GDO Supermarket Scraper: Pipeline ETL & Visual Parsing

GDO Scraper è una pipeline ETL (Extract, Transform, Load) modulare e deterministica in Python per l'estrazione, la normalizzazione e la persistenza di dati promozionali (prodotti, brand, prezzi, sconti, validità) da catene della Grande Distribuzione Organizzata (GDO) italiana.

Il sistema gestisce l'estrazione dati sia da API REST dinamiche (**Coop**) sia tramite visual parsing di volantini PDF geometrici (**Conad**), esportando i record in un database SQLite centralizzato e salvando i ritagli delle immagini dei prodotti ripuliti da sovrapposizioni testuali.

---

## 1. Architettura e Flusso Dati

La pipeline è strutturata secondo lo **Strategy Pattern**, disaccoppiando la definizione dei driver di scraping dall'orchestratore principale:

```
                  AbstractSupermarketDriver [core/base_driver.py]
                             ▲
                             │
                  AbstractPdfFlyerDriver [core/base_pdf_driver.py]
                             ▲
                             │
                  ConadSupermarketDriver [drivers/conad/conad_driver.py]
```

### Componenti Principali:
- **`BasePdfLayoutSegmenter` (`core/base_pdf_segmenter.py`)**: Algoritmo di segmentazione spaziale basato sulla proiezione dell'istogramma dei caratteri sull'asse X per identificare le colonne di testo primarie. Esegue un Y-splitting all'interno di ciascuna colonna isolata con un filtro gutter verticale (minimo 4pt) ed effettua il pairing logico tra i blocchi descrittivi e i rispettivi prezzi.
- **`AbstractPdfFlyerDriver` (`core/base_pdf_driver.py`)**: Gestisce il flusso di parsing dei PDF geometrici, il caching locale dei file scaricati per evitare richieste ridondanti e l'algoritmo di visual cropping.
- **Ritaglio Visivo Bounding-Box (`conad_driver.py`)**: Individua gli oggetti raster nativi (`page.images`) all'interno del PDF che ricadono nella bounding box geometrica della cella del prodotto, ritagliando l'immagine raster originale per isolare l'illustrazione del prodotto ed escludere etichette e scritte. Include un fallback automatico a griglia snappata uniforme in assenza di raster.
- **Multiprocessing a livello di Flyer**: Sfrutta un `ProcessPoolExecutor` per parallelizzare il parsing di molteplici volantini PDF su core CPU indipendenti, ottimizzando i compiti CPU-bound di text extraction e rendering grafico.
- **UPSERT Idempotente (`storage/database.py`)**: Il database SQLite impone un vincolo di unicità composto `PRIMARY KEY (supermarket, store_id, offer_id)`, garantendo l'assoluta idempotenza dei dati inseriti.

---

## 2. Requisiti e Installazione

Il progetto utilizza **`uv`** come package manager per garantire la riproducibilità delle dipendenze:

1. **Creare l'ambiente virtuale e sincronizzare le dipendenze**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```
2. **Struttura delle Directory Locali**:
   - `downloads/conad/`: cache locale per i file PDF scaricati.
   - `storage/promotions.db`: database SQLite centralizzato.
   - `storage/images/`: archivio dei ritagli PNG dei prodotti.
   - `storage/missed_products.log`: log di audit per i blocchi saltati in fase di parsing semantico.

---

## 3. Script di Controllo Interattivo (`run_interactive.py`)

È presente un controller interattivo da terminale per facilitare i test e la configurazione rapida dei parametri:

```bash
./run_interactive.py
```
*(In alternativa: `.venv/bin/python run_interactive.py`)*

### Funzionalità disponibili:
1. **Scraping Coop**: Avvio assistito tramite inserimento del codice punto vendita (es. `0315`).
2. **Scraping Conad**: Configurazione guidata dei parametri di ricerca REST (coordinate GPS, raggio di ricerca, limite volantini e attivazione del multiprocessing parallelo).
3. **Avvio Dashboard**: Esecuzione del server web per l'interfaccia di visualizzazione SPA.
4. **Analisi Database**: Interroga il database SQLite e stampa un report dettagliato con i conteggi, le fasce di prezzo ed i trend delle categorie estratte.
5. **Developer Tools**: Utility per il reset dei database, la pulizia della cache delle immagini o dei PDF e l'esecuzione di benchmark comparativi (sequenziale vs parallelo).

---

## 4. Riferimento CLI (`main.py`)

La pipeline può essere eseguita direttamente da riga di comando tramite `main.py`:

```bash
.venv/bin/python main.py --supermarket [coop|conad] --store-id [store_id|coords] [options]
```

### Parametri Supportati:
| Argomento | Tipo | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| `--supermarket` | `str` | *(Richiesto)* | Catena target da elaborare (`coop` o `conad`). |
| `--store-id` | `str` | *(Richiesto)* | ID del punto vendita (es. `0315` Coop), `anacanId` (es. `005635` Conad) o **coordinate GPS** `lat,lon` (es. `44.1396438,12.2464292`). |
| `--radius` | `int` | `5` | Raggio di ricerca in km per la geolocalizzazione dei punti vendita Conad. |
| `--choose-store` | `flag` | `False` | Attiva una scelta interattiva da console se vengono rilevati più punti vendita nel raggio indicato. |
| `--max-flyers` | `int` | `None` | Limita il numero massimo di volantini Conad da scaricare ed elaborare. |
| `--parallel` | `flag` | `False` | Abilita il parsing parallelo multi-processo a livello di volantino PDF. |
| `--db-path` | `str` | `storage/promotions.db` | Percorso assoluto o relativo del database SQLite. |

---

### Esempi di Utilizzo CLI:

#### 1. Scraping API Coop Cesena
```bash
.venv/bin/python main.py --supermarket coop --store-id "0315"
```

#### 2. Scraping Conad Cesena via GPS (Auto-Download e Multiprocessing abilitato)
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396438,12.2464292" --parallel
```
* **Comportamento**: Risolve le coordinate sul punto vendita `005635`, scarica i volantini attivi ignorando manuali e guide promozionali escluse, avvia il parsing in multiprocessing parallelo, esegue il visual crop ed effettua l'upsert delle offerte.

#### 3. Scraping Conad con Scelta Interattiva del Punto Vendita (Raggio 10km)
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396438,12.2464292" --radius 10 --choose-store
```

---

## 5. Visual Verification Dashboard (`dashboard.py`)

Per effettuare l'audit visivo e verificare l'accuratezza dell'estrazione geometrica e dei crop delle immagini:

```bash
.venv/bin/python dashboard.py
```
- **Porta di ascolto locale**: [http://localhost:8000](http://localhost:8000).
- Offre filtri per catena, punto vendita, ricerca testuale dei prodotti ed un'ispezione ad alta definizione tramite zoom al passaggio del mouse sopra i crop PNG salvati in `storage/images/`.
