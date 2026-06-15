# Codebase Refactoring Plan: Supermarket Scraper Project

This document details the refactoring plan to fix critical bugs, remove duplicate code, and resolve cross-platform compatibility issues across the Supermarket Scraper codebase.

---

## 1. Audit Summary Table

| ID | Title | Component / File | Severity | Category | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BUG-03** | `ModuleNotFoundError` in manual uploads parser | [manual_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/manual/manual_driver.py#L33) | **Critical** | Import / Regression | **COMPLETED** |
| **ARCH-02** | Duplicate image processing block in base PDF driver | [base_pdf_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_pdf_driver.py#L446) | **Medium** | Code Quality / DRY | **COMPLETED** |
| **ARCH-03** | Duplicate REST API flyer discovery logic in Conad driver | [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py#L165) | **Medium** | Code Quality / DRY | **COMPLETED** |
| **ARCH-04** | Redundant `.env` loading loop inside HTTP `do_POST` | [dashboard.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/dashboard.py#L445) | **Low** | Redundancy | **COMPLETED** |
| **PORT-02** | Hardcoded Unix virtual environment Python paths | [dashboard.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/dashboard.py#L12) / [run_interactive.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/run_interactive.py#L22) | **Medium** | Cross-Platform Compatibility | **COMPLETED** |

---

## 2. Detailed Findings & Proposed Resolutions

### BUG-03: `ModuleNotFoundError` in manual uploads parser
* **Location**: [manual_driver.py:L33-L41](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/manual/manual_driver.py#L33-L41)
* **Severity**: **Critical**
* **Description**:
  During a previous layout segmenter consolidation, the specific file layout segmenters (`conad_layout_segmenter.py` and `ins_layout_segmenter.py`) were deleted. However, `ManualSupermarketDriver` still attempts to import `ConadLayoutSegmenter` and `InsLayoutSegmenter` from these non-existent modules, causing immediate crashes upon instantiating the manual driver or uploading a flyer in the dashboard.
* **Resolution**:
  Replace these imports with `BasePdfLayoutSegmenter` directly from `core.base_pdf_segmenter`. Update the constructors:
  - `self._conad_segmenter` will be initialized as `BasePdfLayoutSegmenter(gutter_min_width=6)`.
  - `self._ins_segmenter` will be initialized as `BasePdfLayoutSegmenter()`.

---

### ARCH-02: Duplicate image processing block in base PDF driver
* **Location**: [base_pdf_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/core/base_pdf_driver.py) (lines 446-483, 960-997, and 1217-1256)
* **Severity**: **Medium**
* **Description**:
  The code for resolving standard produce images, querying fuzzy reusable images from SQLite, calculating padding box coordinates, and cropping/trimming solid backgrounds is duplicated word-for-word three times (once in the Gemini visual parser, once in the Claude scanned fallback, and once in the Claude page auditor).
* **Resolution**:
  Extract the shared logic into a single private helper method:
  ```python
  def _extract_and_save_product_image(
      self, 
      name: str, 
      bbox: List[int], 
      pil_img: Any, 
      store_id: str, 
      offer_id: str
  ) -> Optional[str]:
  ```
  And replace all three duplicate code blocks with calls to this helper.

---

### ARCH-03: Duplicate REST API flyer discovery logic in Conad driver
* **Location**: [conad_driver.py](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/drivers/conad/conad_driver.py) (lines 165-212 and 240-278)
* **Severity**: **Medium**
* **Description**:
  The logic for requesting flyers from the Conad API, filtering out expired ones, checking title/name string blacklist tags (e.g. `manuale`, `conad pay`), mapping date validity formats, and generating lists of flyer dictionaries is duplicated across both `discover_flyers()` and `download_flyers()`.
* **Resolution**:
  Extract the retrieval and filtering logic into a private helper:
  ```python
  def _get_active_flyers(self, store_code: str) -> List[Dict[str, Any]]:
  ```
  And refactor both methods to call it.

---

### ARCH-04: Redundant `.env` loading loop inside HTTP `do_POST`
* **Location**: [dashboard.py:L445-L454](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/dashboard.py#L445-L454)
* **Severity**: **Low**
* **Description**:
  `dashboard.py` loads `.env` globally at the module level. However, inside `do_POST` (specifically under the `/api/upload` endpoint), the code runs the exact same `.env` loading loop again. Since these values are already in `os.environ`, this is redundant.
* **Resolution**:
  Remove the duplicate `.env` file reading loop from `do_POST`.

---

### PORT-02: Hardcoded Unix virtual environment Python paths
* **Location**: 
  - [dashboard.py:L12](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/dashboard.py#L12)
  - [run_interactive.py:L22](file:///home/aleemont/Projects/GdoScraper/supermarket_scraper/run_interactive.py#L22)
* **Severity**: **Medium**
* **Description**:
  Both files locate the virtual environment Python interpreter using a hardcoded Unix-style relative path (`.venv/bin/python`). On Windows platforms, the virtual environment executable is located at `.venv\Scripts\python.exe`. This causes self-healing re-execution checks and subprocess spawning to fall back to global interpreters, leading to environment mismatches and potential run-time failures on Windows.
* **Resolution**:
  Implement a cross-platform Python executable locator helper:
  ```python
  def get_venv_python():
      script_dir = os.path.dirname(os.path.abspath(__file__))
      # On Windows
      if sys.platform.startswith("win"):
          win_path = os.path.join(script_dir, ".venv", "Scripts", "python.exe")
          if os.path.exists(win_path):
              return win_path
      # On Unix/macOS
      unix_path = os.path.join(script_dir, ".venv", "bin", "python")
      if os.path.exists(unix_path):
          return unix_path
      return sys.executable
  ```
  Replace hardcoded paths with this cross-platform function.

---

## 3. Step-by-Step Refactoring Sequence

To minimize risk and ensure continuous test coverage:
1. **Step 1: Fix Virtualenv Path Resolving** - Update `dashboard.py` and `run_interactive.py` to support Windows venv paths.
2. **Step 2: Clean Up Redundancy in `dashboard.py`** - Remove the redundant `.env` loading loop.
3. **Step 3: Fix Critical Bug in `manual_driver.py`** - Replace missing segmenter imports with direct instantiation of `BasePdfLayoutSegmenter`.
4. **Step 4: Refactor Conad Driver Duplication** - Extract flyer lookup to `_get_active_flyers()`.
5. **Step 5: Refactor Base PDF Driver Image Duplication** - Extract the image extraction/processing blocks into `_extract_and_save_product_image()`.

---

## 4. Verification Strategy

1. **Syntax Checking**: Test each modified file individually for syntax correctness.
2. **Unit Tests**: Run `pytest tests/test_pipeline.py` to ensure that standard parsers and database engines suffer no regressions.
3. **E2E Manual Scrape Verification**:
   - Run the manual strategy using an uploaded PDF flyer via the dashboard UI or CLI to ensure `ManualSupermarketDriver` functions perfectly.
   - Run a Conad and Coop crawl via TUI (`run_interactive.py`) and dashboard UI to ensure API scraping and visual caching work.
