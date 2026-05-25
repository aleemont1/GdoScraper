# GDO Supermarket Scraper: Terminal Control Center & ETL Pipeline

GDO Scraper è una pipeline ETL (Extract, Transform, Load) deterministica, modulare e ad alta precisione progettata per automatizzare la ricerca, il download, il parsing geometrico e il ritaglio visivo delle offerte promozionali delle catene di supermercati della Grande Distribuzione Organizzata (GDO) italiana.

Il sistema estrae dati semantici (prodotti, brand, prezzi, sconti) sia da API REST dinamiche (**Coop**) sia da volantini PDF fisici (**Conad**), salvando i record in un database SQLite centralizzato ed esportando immagini dei prodotti ritagliate al millimetro e prive di scritte.

---

## 1. Architettura & Tecnologie Chiave

- **Core Generalizzato (`AbstractPdfFlyerDriver`)**: Gestisce il caricamento pigro dei PDF, il caching locale anti-spreco di banda, il log di qualità per i prodotti saltati e la routine visiva di ritaglio.
- **Ritaglio Visivo Ibrido Prodotto-Centrico**:
  1. Identifica il livello raster nativo (`page.images`) all'interno di ciascuna cella geometrica.
  2. Ritaglia l'immagine raster nativa eliminando scritte sovrapposte, tag di prezzo e sfondi spuri.
  3. Applica un fallback deterministico a griglia snappata se non ci sono raster in zona.
- **Clustering Spaziale a Colonne (`BasePdfLayoutSegmenter`)**: Esegue proiezioni verticali per isolare le colonne di testo escludendo intestazioni e piè di pagina, per poi accoppiare i blocchi descrizione/prezzo.
- **Idempotenza Database (UPSERT SQL)**: La chiave primaria composta `(supermarket, store_id, offer_id)` garantisce la totale idempotenza dei dati in esecuzioni ripetute.

---

## 2. Installazione & Configurazione Rapida

Il progetto gestisce le dipendenze in modo estremamente veloce tramite **`uv`**:

1. **Inizializza l'ambiente virtuale e installa le dipendenze**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```
2. **Directory Struttura Creata Automaticamente**:
   - `downloads/conad/`: memorizza i PDF dei volantini scaricati dalla rete.
   - `storage/promotions.db`: database SQLite centralizzato.
   - `storage/images/`: raccoglie tutti i ritagli PNG perfetti dei prodotti.
   - `storage/missed_products.log`: log per il controllo qualità.

---

## 3. Terminale Interattivo CLI Control Center (`run_interactive.py`)

Per evitare di digitare comandi lunghi e complessi, abbiamo creato un **Terminale Interattivo TUI** colorato con menu guidati:

### Avvio rapido:
```bash
./run_interactive.py
```
*(Se non eseguibile, lancia con: `.venv/bin/python run_interactive.py`)*

### Cosa puoi fare dall'interfaccia interattiva:
1. **Scraper COOP**: Avvia lo scaricamento automatico tramite API inserendo solo il codice del punto vendita.
2. **Scraper CONAD**: Scegli tra inserimento diretto dell'ID negozio (`anacanId`) o digitazione delle coordinate GPS. Consente di inserire raggio di ricerca, attivare il menu di scelta interattivo e impostare un limite al numero di volantini da scaricare.
3. **Avvio Dashboard**: Lancia il server web locale della SPA di controllo visivo.
4. **Database Analytics**: Mostra in tempo reale statistiche dettagliate delle tabelle (offerte totali, record per negozio, fasce di prezzo e categorie più rilevanti).

---

## 4. Riferimento Completo Comandi CLI (`main.py`)

Se preferisci lanciare la pipeline da riga di comando o integrarla in un cronjob, puoi usare direttamente `main.py` con i seguenti parametri:

### Parametri CLI:
| Opzione | Tipo | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| `--supermarket` | `coop` o `conad` | *(Richiesto)* | Catena di supermercati da raschiare. |
| `--store-id` | `string` | *(Richiesto)* | ID negozio (es. `0315` Coop), `anacanId` (es. `005635` Conad) o **Coordinate GPS** `lat,lon` (es. `44.1396438,12.2464292`). |
| `--radius` | `int` | `5` | Raggio di ricerca in chilometri per la geolocalizzazione automatica del negozio Conad. |
| `--choose-store` | `flag` | `False` | Se abilitato con coordinate, mostra un menu di scelta console tra tutti i punti vendita trovati. |
| `--max-flyers` | `int` | `None` | Cappa il numero massimo di volantini da scaricare e processare (es. `1` per evitare bulk massicci). |
| `--db-path` | `string` | `storage/promotions.db` | Percorso del database SQLite di destinazione. |

---

### Esempi Pratici di Esecuzione CLI:

#### A. Scrape di Coop Cesena (API REST pura)
```bash
.venv/bin/python main.py --supermarket coop --store-id "0315"
```

#### B. Scrape di Conad Cesena via Coordinate (Auto-Download del volantino più vicino, max 1 volantino)
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396438,12.2464292" --max-flyers 1
```
* **Risultato**: Individua il Conad City di Viale Gaspare Finali 28 (`005635`), scarica l'ultimo volantino attivo, estrae le offerte e le associa al negozio `005635` nel database.

#### C. Scrape di Conad Interattivo (Raggio di ricerca 15km con scelta del negozio da menu)
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396438,12.2464292" --radius 15 --choose-store
```
* **Risultato**: Visualizza una lista numerata dei punti vendita entro 15km, attende la tua digitazione da terminale, scarica i volantini associati a quel punto vendita e procede con l'ETL.

#### D. Scrape di Conad tramite ID Punto Vendita Diretto
```bash
.venv/bin/python main.py --supermarket conad --store-id "005635" --max-flyers 1
```

---

## 5. Visualizzazione & Controllo Qualità SPA (`dashboard.py`)

Dopo aver popolato il database, puoi analizzare visivamente i ritagli ed i dati estratti tramite la SPA integrata:

```bash
.venv/bin/python dashboard.py
```
- Server locale avviato all'indirizzo: **[http://localhost:8000](http://localhost:8000)**.
- **Caratteristiche Premium**: Glassmorphism, caricamento lazy, zoom dinamico al passaggio del mouse sopra i ritagli dei prodotti per ispezionarne l'accuratezza al 100%, filtri istantanei per insegna e negozio.
- **Log di Controllo Qualità (`storage/missed_products.log`)**: Se un blocco contiene parole chiave di prezzo ma non viene convalidato, viene salvato qui con le coordinate della pagina per consentire un audit rapido del parser semantico.
