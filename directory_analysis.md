# Codebase Audit Report: Supermarket Scraper Project

This report presents a thorough security, performance, and architectural audit of the supermarket scraper and visual verification dashboard codebase. It covers the core library, storage abstraction, supermarket drivers, utility managers, and CLI entry points.

---

## Executive Summary

The codebase implements a robust ETL structure using the **Strategy Pattern** to decouple supermarket-specific extraction engines from the core processing pipeline. However, several critical issues were discovered during the audit, including interactive prompt exceptions (EOFError) that cause unintended scraping of all flyers when running in non-interactive/headless environments, and SRP/KISS coupling where driver logic is mixed with console UI interactions.

---

## Findings Overview

| ID | Title | Component / File | Severity | Category |
| :--- | :--- | :--- | :--- | :--- |
| **INT-01** | Non-Interactive EOFError Fallback Bug | [coop_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py#L189-L207) / [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py#L215-L218) | **High** | Logic / Bug |
| **ARCH-02** | SRP Violation: CLI Console Interaction in Scraper Strategies | [coop_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py) / [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py) | **Medium** | Architecture |
| **DOC-01** | Missing / Incomplete Docstrings & Comments | Multiple Scraper Driver Files | **Low** | Code Quality |

---

## Detailed Findings & Recommendations

### INT-01: Non-Interactive EOFError Fallback Bug

* **File Location**: 
  - [coop_driver.py:L189-207](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py#L189-L207)
  - [conad_driver.py:L215-218](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py#L215-L218)
* **Severity**: **High**
* **Description**:
  When a user runs the pipeline in a non-interactive shell (such as a task runner, subagent context, or script pipeline), the `input()` function raises an `EOFError`. 
  In the current implementation, this exception is caught and falls back to selecting **all** flyers:
  ```python
  except (KeyboardInterrupt, EOFError):
      print("\nSelection interrupted. Defaulting to all flyers.")
      selected_leaflets = leaflets
      break
  ```
  This leads to unintended large scraping runs (e.g. fetching 1446 products across 6 leaflets instead of a targeted subset of ~150-400 products).

#### Recommended Solution
Check if the current session is running interactively using `sys.stdin.isatty()`. If it is non-interactive, log a warning and default to only the **first (featured)** flyer or abort execution, rather than silently defaulting to scraping all flyers.

---

### ARCH-02: SRP Violation: CLI Console Interaction in Scraper Strategies

* **File Location**: [coop_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/coop/coop_driver.py) / [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py)
* **Severity**: **Medium**
* **Description**:
  The driver strategies contain custom console print and `input()` loops. According to the Single Responsibility Principle (SRP) and the Strategy Pattern, a scraper driver should only be responsible for data extraction and parsing, not for handling user console interactions. Mixing UI code (stdin prompts) with ETL network strategies reduces code reuse, testability, and portability.

#### Recommended Solution
Abstract console prompt selection out of the driver classes. Standardize the select options via CLI parameters or high-level runner wrappers, and let the scraper strategy receive the user selections or targeted IDs directly as constructor or method arguments.

---

### DOC-01: Missing / Incomplete Docstrings & Comments

* **File Location**: Multiple Scraper Driver Files
* **Severity**: **Low**
* **Description**:
  Several methods and private parsing helpers lack English docstrings and comments. Some variables and comments in the parser use Italian terminology, which violates the strict requirement to use English exclusively.

#### Recommended Solution
Refactor all modified modules, classes, and functions to contain descriptive docstrings and comments in English.
