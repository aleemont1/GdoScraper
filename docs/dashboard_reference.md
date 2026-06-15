# Dashboard di Verifica Visiva (`dashboard.py`)

La **Visual Verification Dashboard** è un'applicazione web SPA (Single Page Application) leggera sviluppata in Vanilla JavaScript, HTML5 e CSS3 che permette di verificare visivamente i risultati dell'estrazione dei dati e controllare i log di esecuzione in tempo reale.

---

## 1. Avvio del Server della Dashboard

Puoi avviare la dashboard tramite il menu della TUI oppure direttamente da riga di comando:

```bash
.venv/bin/python dashboard.py
```
Il server si avvia in ascolto all'indirizzo locale: **[http://localhost:8000](http://localhost:8000)**.

---

## 2. Flusso di Lavoro ed Interfaccia Utente

L'interfaccia è suddivisa in tre sezioni principali:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          DASHBOARD HEADER (Filtri)                       │
├────────────────────────────────────────┬─────────────────────────────────┤
│                                        │                                 │
│          PANNELLO DI ESTRAZIONE        │       MONITOR DI ESECUZIONE     │
│       - Selezione Supermercato         │       - Console Log Terminale   │
│       - Ricerca Negozi                 │       - Stato del Processo      │
│       - Selezione Volantini            │                                 │
│                                        │                                 │
├────────────────────────────────────────┴─────────────────────────────────┤
│                                                                          │
│                       GRIGLIA DI AUDIT DELLE OFFERTE                     │
│                       - Schede Prodotto Normalizzate                     │
│                       - Immagini Crop con Zoom Ispezione                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### A. Pannello di Estrazione (Wizard)
1. **Selezione Catena**: Scegli tra Coop, Conad, IN'S, Dpiù o Caricamento Manuale.
2. **Ricerca Store**: Inserisci una città o delle coordinate geografiche per scoprire i punti vendita nel raggio d'azione.
3. **Selezione Volantini**:
   - Per Conad e Coop, compare l'elenco dei volantini attivi rilevati.
   - Ogni volantino presenta un tasto di anteprima (**👁**) che consente di visualizzare il PDF originale o la pagina web promozionale in una nuova scheda.
   - Puoi selezionare uno o più volantini tramite checkbox.

### B. Console Log Terminale (Esecuzione in Background)
* Quando clicchi su **"Avvia Estrazione"**, il backend lancia la pipeline di scraping in un sottoprocesso in background.
* La console del terminale mostra i messaggi di log in tempo reale.
* La console è **scrollabile** e la sua altezza si adatta dinamicamente a quella del pannello opzioni, mantenendo l'interfaccia simmetrica ed ordinata.

### C. Griglia di Audit delle Offerte
* Visualizza tutte le promozioni salvate nel database SQLite.
* Per ciascun prodotto estratto, mostra il nome, il prezzo, la percentuale di sconto, la validità dell'offerta e l'immagine ritagliata.
* **Zoom Ispezione**: Passando il cursore del mouse sopra l'immagine del prodotto, viene mostrato un ingrandimento dettagliato ad alta definizione per verificare la qualità del visual crop.
