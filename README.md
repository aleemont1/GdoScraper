# Supermarket Scraper ETL Pipeline

## Project Overview
Progetto di ingegneria software finalizzato alla creazione di una pipeline ETL (Extract, Transform, Load) deterministica, modulare e scalabile per l'estrazione di dati promozionali dai volantini della Grande Distribuzione Organizzata (GDO) italiana.

## Goal
Estrarre, normalizzare e persistere in un database SQLite le offerte promozionali (prezzi, sconti, unità di misura) da diverse catene (Conad, Coop) provenienti da fonti eterogenee (REST API, file PDF).

## Project Structure
supermarket_scraper/
├── core/            # Domain models e interfacce astratte (Strategy Pattern)
├── drivers/         # Implementazioni concrete degli scraper (Conad, Coop)
├── storage/         # Layer di persistenza SQLite (con logica UPSERT)
├── utils/           # Logging e utility globali
└── downloads/       # Asset temporanei (PDF volantini)

## Technical Constraints & Decisions
- **Architettura:** OOP basata su Strategy Pattern e Chain of Responsibility.
- **Gestione Dipendenze:** `uv` (file `pyproject.toml`, `uv.lock`).
- **Persistenza:** SQLite con clausola UPSERT per garantire idempotenza dei dati.
- **Parsing PDF:** Strategia ibrida basata su `pdfplumber` (estrazione geometrica dei token) e parser semantici.
- **Stato del Progetto:** - Infrastruttura core e Database completate.
  - Driver Conad validato tramite PoC: il clustering spaziale identifica correttamente i blocchi.

## Past Strategies & Learnings
1. **Pypdf vs Pdfplumber:** Abbandonato `pypdf` a favore di `pdfplumber` per la gestione delle bounding box geometriche.
2. **Regex vs LLM:** - Tentato parsing via Regex: efficace per layout fissi, fragile al variare del layout.
   - Valutato LLM: approccio potente ma scartato per costi API in pipeline massive.
   - Prossimo passo: Ottimizzazione del parsing geometrico per gestire template variabili in modo deterministico.

## Rules for Antigravity (Assistant)
- **Modularity:** Ogni nuovo driver deve ereditare da `AbstractSupermarketDriver`.
- **Determinism:** Prediligere soluzioni deterministiche (codice Python) rispetto ad agenti autonomi per le task ripetitive di scraping.
- **Scalability:** Mantenere il database normalizzato e le query ottimizzate con indici.
- **Documentation:** Mantenere la documentazione tecnica nel codice in lingua inglese.

## Status
In fase di integrazione del primo driver ufficiale (drivers/conad_driver.py) basato sulla struttura core.
