# Riferimento della CLI (`main.py`)

La pipeline principale del progetto viene eseguita da terminale tramite l'entrypoint `main.py`. Questo documento fornisce la spiegazione di tutte le opzioni, i flag ed i comandi supportati.

---

## 1. Comando di Base

Per eseguire la pipeline, posizionati nella cartella del progetto ed esegui `main.py` all'interno dell'ambiente virtuale:

```bash
.venv/bin/python main.py --supermarket [conad|coop|ins|dpiu] --store-id [valore] [opzioni]
```

---

## 2. Elenco dei Parametri della CLI

| Flag / Opzione | Tipo | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| **`--supermarket`** | `str` | *(Richiesto)* | Catena target da elaborare (`coop`, `conad`, `ins`, `dpiu`, `manual`). |
| **`--store-id`** | `str` | *(Richiesto)* | Identificatore del punto vendita. Può essere:<br>- Un codice numerico (es. `0315` Coop, `005635` Conad)<br>- Coordinate GPS formato `lat,lon` (es. `44.1396,12.2464`) |
| **`--radius`** | `int` | `5` | Raggio di ricerca espresso in km per localizzare i negozi tramite coordinate GPS (utilizzato da Conad e Coop). |
| **`--choose-store`** | `flag` | `False` | Se specificato, apre un menu interattivo da terminale per selezionare il punto vendita esatto qualora ne venissero trovati molteplici. |
| **`--max-flyers`** | `int` | `None` | Limita il numero massimo di volantini Conad o IN'S da elaborare in questa esecuzione. |
| **`--parallel`** | `flag` | `False` | Abilita il multiprocessing per elaborare contemporaneamente più volantini su diversi core CPU. |
| **`--db-path`** | `str` | `storage/promotions.db` | Percorso personalizzato del database SQLite per salvare le offerte estratte. |
| **`--engine`** | `str` | `AUTO` | Definisce il motore di elaborazione da utilizzare per i volantini PDF (`AUTO`, `GEMINI`, `CLAUDE`, `LOCAL`). |
| **`--selected-flyer-ids`** | `str` | `None` | Lista di ID volantino Coop separati da virgola per filtrare l'estrazione. |
| **`--selected-flyer-slugs`** | `str` | `None` | Lista di slug volantino Conad separati da virgola per filtrare l'estrazione. |

---

## 3. Esempi di Utilizzo Avanzato

### A. Estrazione API Coop (Tutte le promozioni attive)
Esegue lo scraping completo del negozio Coop di Cesena identificato dal codice `0315`:
```bash
.venv/bin/python main.py --supermarket coop --store-id "0315"
```

### B. Estrazione Conad via Coordinate GPS con Multiprocessing
Cerca il punto vendita Conad più vicino alle coordinate geografiche specificate, scarica i volantini attivi, ed elabora i file PDF in parallelo sfruttando i core della CPU:
```bash
.venv/bin/python main.py --supermarket conad --store-id "44.1396,12.2464" --parallel
```

### C. Estrazione IN'S Mercato con Motore AI Claude Fallback
Avvia il parsing del volantino IN'S Mercato. Se le pagine contengono immagini scansionate non leggibili geometricamente, interroga Claude Sonnet per estrarre visivamente le offerte:
```bash
.venv/bin/python main.py --supermarket ins --store-id "Cesena" --engine CLAUDE
```
*(Nota: Assicurati di avere configurato `ANTHROPIC_API_KEY` nel file `.env`)*
