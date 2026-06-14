# Codebase Audit Report: Supermarket Scraper Project

This report presents a thorough security, performance, and architectural audit of the GDO Supermarket Scraper codebase. It documents the critical bugs, architectural violations, language violations, and test suite deficiencies identified, along with their resolution details.

---

## Executive Summary

The supermarket scraper utilizes the **Strategy Pattern** to decouple different extraction engines (Coop, Conad, IN's, Dpiù) from the main execution pipeline. 
All identified findings have been successfully refactored and resolved in accordance with KISS, SRP, OOP, and strict language constraints. 

---

## Findings Overview & Resolution Status

| ID | Title | Component / File | Severity | Category | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BUG-01** | Non-Interactive EOFError Fallback Bug | [coop_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py) / [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py) | **High** | Logic / Bug | **RESOLVED** |
| **BUG-02** | Missing `isatty` Check in Dpiù Driver | [dpiu_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/dpiu/dpiu_driver.py) | **High** | Logic / Bug | **RESOLVED** |
| **ARCH-01** | SRP Violation: CLI Prompts in Scraper Strategies | `core/base_driver.py`, `drivers/coop/coop_driver.py`, `drivers/conad/conad_driver.py`, `drivers/dpiu/dpiu_driver.py` | **Medium** | Architecture | **RESOLVED** |
| **LANG-01** | Non-English Strings, Comments, and Schemas | [base_pdf_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_pdf_driver.py) | **Low** | Code Quality | **RESOLVED** |
| **TST-01** | Lack of Automated Pytest Suite | `tests/test_pipeline.py` | **Medium** | QA / Testing | **RESOLVED** |

---

## Detailed Findings, Refactoring, & Resolutions

### BUG-01: Non-Interactive EOFError Fallback Bug

* **File Location**: 
  - [coop_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py)
  - [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py)
* **Severity**: **High**
* **Resolution Status**: **RESOLVED**
* **Description**:
  When running the pipeline in non-interactive/headless environments, calls to `input()` would throw `EOFError`. The drivers caught this exception and defaulted to scraping **all** flyers, triggering massive unintended scraping loads.
* **Resolution Details**:
  All user interactive prompt logic has been completely removed from the driver strategy classes. The drivers now accept target parameters cleanly. The `main.py` entrypoint controls the interactive CLI prompt loops and resolves store/flyer lists prior to running the ETL driver. If stdin is not a TTY, `main.py` defaults to safe defaults without prompting.

---

### BUG-02: Missing `isatty` Check in Dpiù Driver

* **File Location**: [dpiu_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/dpiu/dpiu_driver.py)
* **Severity**: **High**
* **Resolution Status**: **RESOLVED**
* **Description**:
  The Dpiù driver called interactive console prompt selection methods directly without checking if standard input is a terminal, which caused immediate crashes in non-interactive/headless sessions.
* **Resolution Details**:
  The console prompting logic inside the Dpiù driver has been completely deleted. Store discovery is now exposed via the new `discover_stores` API, and store resolving occurs automatically to the closest match or selected entry.

---

### ARCH-01: SRP Violation: CLI Prompts in Scraper Strategies

* **File Location**: Multiple driver files and base classes.
* **Severity**: **Medium**
* **Resolution Status**: **RESOLVED**
* **Description**:
  Scraper strategy classes contained CLI console print and `input()` loops. A scraper driver should only be responsible for ETL data extraction, parsing, and normalization (Single Responsibility Principle). Mixing UI prompts with driver strategies reduced reusability, testability, and portability.
* **Resolution Details**:
  1. We added public store and flyer metadata discovery methods to the driver interface:
     - [discover_stores](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_driver.py#L74)
     - [discover_flyers](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_driver.py#L98)
  2. We refactored `main.py` to handle the interactive selection menus (using a new [prompt_selection](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/main.py#L31) helper) when `--choose-store` or `--choose-flyer` is requested.
  3. Drivers are now 100% free of CLI user input dependencies and are completely portable.

---

### LANG-01: Non-English Strings, Comments, and Schemas

* **File Location**: [base_pdf_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_pdf_driver.py)
* **Severity**: **Low**
* **Resolution Status**: **RESOLVED**
* **Description**:
  Pydantic field descriptions, docstrings, system prompts, and visual LLM prompt strings were written in Italian, violating the English-only codebase restriction.
* **Resolution Details**:
  Translated all Italian field descriptions in `ExtractedOffer`, Tesseract/Gemini/Claude system instructions, and OCR visual prompt instruction strings into English. The prompts instruct the visual models to extract details in Italian (matching the catalog documents), but the instruction strings themselves are written entirely in English.

---

### TST-01: Lack of Automated Pytest Suite

* **File Location**: [tests/test_pipeline.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/tests/test_pipeline.py)
* **Severity**: **Medium**
* **Resolution Status**: **RESOLVED**
* **Description**:
  The test files in the root directory were ad-hoc standalone scripts instead of a standard automated test suite.
* **Resolution Details**:
  Created a proper automated testing folder and implemented a comprehensive `pytest` suite in [tests/test_pipeline.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/tests/test_pipeline.py) to validate:
  - Pydantic models schema type-checking and validation.
  - SQLite database initializations, indices, and WAL configs.
  - SQLite UPSERT idempotency and data preservation.
  - Word parsing uppercase collapsing algorithms.
  - Fuzzy image managers reuse and standard produce mapping lookups.
  All tests pass successfully on the test suite: `PYTHONPATH=. pytest tests/test_pipeline.py`.
