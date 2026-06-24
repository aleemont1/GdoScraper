"""
Main ETL Pipeline Orchestrator Entrypoint.

Parses command-line interface arguments, initializes database setups,
discovers stores and flyer lists, manages user console selection prompts,
and runs the scraping execution strategies.
"""

import argparse
import sys
import os
from typing import List, Any, Callable
from utils.logger import setup_logger
from storage.database import initialize_db, save_offers
from drivers.coop.coop_driver import CoopSupermarketDriver
from drivers.conad.conad_driver import ConadSupermarketDriver
from drivers.ins.ins_driver import INSSupermarketDriver
from drivers.dpiu.dpiu_driver import DpiuSupermarketDriver
from drivers.manual.manual_driver import ManualSupermarketDriver

# Load local environment variables if .env file exists
if os.path.exists(".env"):
    try:
        with open(".env") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("'\"")
    except Exception:
        pass


def prompt_selection(
    items: List[Any],
    display_func: Callable[[Any], str],
    prompt: str,
    default_idx: int = 0,
) -> Any:
    """
    Displays a list of items and prompts the user in the console for an index selection.

    Args:
        items: List of options to choose from.
        display_func: Callable to format each option to a string.
        prompt: Display message for the prompt.
        default_idx: Default index to use when input is empty or interrupted.

    Returns:
        The selected option.
    """
    if not items:
        raise ValueError("Cannot prompt selection from an empty list.")

    for idx, item in enumerate(items):
        print(f"  {idx + 1}) {display_func(item)}")

    while True:
        try:
            user_input = input(
                f"{prompt} [1-{len(items)}] (Enter to default to index {default_idx + 1}): "
            ).strip()
            if not user_input:
                return items[default_idx]

            val = int(user_input)
            if 1 <= val <= len(items):
                return items[val - 1]
            else:
                print(f"Please enter a number between 1 and {len(items)}.")
        except ValueError:
            print("Invalid input. Please enter a valid integer.")
        except (KeyboardInterrupt, EOFError):
            print(f"\nSelection interrupted. Defaulting to index {default_idx + 1}.")
            return items[default_idx]


def main() -> None:
    """
    Main orchestrator entrypoint for the supermarket promotional data ETL pipeline.
    Parses CLI arguments, initializes database connections, triggers scrapers,
    and persists normalized datasets.
    """
    parser = argparse.ArgumentParser(
        description="ETL pipeline tool for Italian GDO supermarket promotional offers."
    )
    parser.add_argument(
        "--supermarket",
        choices=["coop", "conad", "ins", "dpiu", "manual"],
        required=True,
        help="Supermarket chain to scrape (coop, conad, ins, dpiu, or manual).",
    )
    parser.add_argument(
        "--custom-supermarket",
        default="MANUAL",
        help="Custom supermarket name to use in 'manual' mode (default: MANUAL).",
    )
    parser.add_argument(
        "--use-gemini",
        action="store_true",
        help="Use Gemini 2.5 Flash API for OCR-based flyer scraping instead of local offline Tesseract.",
    )
    parser.add_argument(
        "--use-claude",
        action="store_true",
        help="Use Anthropic Claude Haiku 4.5 API for OCR-based flyer scraping.",
    )
    parser.add_argument(
        "--engine",
        choices=["AUTO", "TESSERACT", "GEMINI", "CLAUDE"],
        default="AUTO",
        help="Explicitly choose the parsing/OCR engine to use (default: AUTO).",
    )
    parser.add_argument(
        "--store-id",
        required=True,
        help=(
            "Specific store ID (e.g. '0315' for Coop Cesena, or '005635' for Conad, "
            "or coordinate string like '44.1396438,12.2464292' for Conad REST lookup)."
        ),
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=5,
        help="Search radius in kilometers for coordinate-based store discovery (default: 5).",
    )
    parser.add_argument(
        "--choose-store",
        action="store_true",
        help="Enable interactive terminal selection menu when multiple stores are found within the search radius.",
    )
    parser.add_argument(
        "--choose-flyer",
        action="store_true",
        help="Enable interactive terminal selection menu to choose which Coop/Conad flyer(s) to scrape.",
    )
    parser.add_argument(
        "--max-flyers",
        type=int,
        default=None,
        help="Limit the maximum number of flyers downloaded and parsed in this run (default: no limit).",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable multi-process parallel flyer parsing to exploit multi-core CPUs.",
    )
    parser.add_argument(
        "--db-path",
        default="storage/promotions.db",
        help="Path to the SQLite database file (default: storage/promotions.db).",
    )
    parser.add_argument(
        "--selected-flyer-ids",
        default=None,
        help="Comma-separated list of Coop flyer IDs to scrape directly (bypasses interactive prompt).",
    )
    parser.add_argument(
        "--selected-flyer-slugs",
        default=None,
        help="Comma-separated list of Conad flyer slugs to scrape directly (bypasses interactive prompt).",
    )

    args = parser.parse_args()
    logger = setup_logger("ETLPipeline")

    logger.info("Initializing supermarket promotions ETL process...")

    # 1. Initialize SQLite Database
    try:
        initialize_db(args.db_path)
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        sys.exit(1)

    # Resolve the OCR/parsing engine selection
    engine = args.engine.upper().strip()
    if args.use_gemini:
        engine = "GEMINI"
    elif args.use_claude:
        engine = "CLAUDE"

    driver = None
    if args.supermarket == "coop":
        selected_flyer_ids = (
            args.selected_flyer_ids.split(",") if args.selected_flyer_ids else None
        )
        driver = CoopSupermarketDriver(
            radius=args.radius,
            choose_store=False,
            choose_flyer=False,
            selected_flyer_ids=selected_flyer_ids,
        )
    elif args.supermarket == "conad":
        selected_flyer_slugs = (
            args.selected_flyer_slugs.split(",") if args.selected_flyer_slugs else None
        )
        driver = ConadSupermarketDriver(
            max_flyers=args.max_flyers,
            radius=args.radius,
            choose_store=False,
            choose_flyer=False,
            parallel=args.parallel,
            selected_flyer_slugs=selected_flyer_slugs,
            use_gemini=(engine == "GEMINI"),
            use_claude=(engine == "CLAUDE"),
            engine=engine,
        )
    elif args.supermarket == "ins":
        driver = INSSupermarketDriver(
            max_flyers=args.max_flyers,
            parallel=args.parallel,
            use_gemini=(engine == "GEMINI"),
            use_claude=(engine == "CLAUDE"),
            engine=engine,
        )
    elif args.supermarket == "dpiu":
        driver = DpiuSupermarketDriver(
            max_flyers=args.max_flyers, radius=args.radius, choose_store=False
        )
    elif args.supermarket == "manual":
        driver = ManualSupermarketDriver(
            supermarket_name=args.custom_supermarket,
            store_id=args.store_id,
            parallel=args.parallel,
            engine=engine,
        )

    if not driver:
        logger.critical("Failed to instantiate a valid scraper driver strategy.")
        sys.exit(1)

    # 2. Handle Interactive Prompts at CLI Level
    resolved_store_id = args.store_id

    if args.choose_store:
        if not sys.stdin.isatty():
            logger.warning(
                "Non-interactive terminal detected. Bypassing interactive store selection."
            )
            stores = driver.discover_stores(args.store_id)
            if stores:
                resolved_store_id = stores[0]["id"]
        else:
            logger.info(f"Discovering stores matching reference '{args.store_id}'...")
            stores = driver.discover_stores(args.store_id)
            if not stores:
                logger.critical("No stores found matching the targeting criteria.")
                sys.exit(1)
            elif len(stores) == 1:
                resolved_store_id = stores[0]["id"]
            else:
                print(f"\nDiscovered {len(stores)} stores matching '{args.store_id}':")
                selected_store = prompt_selection(
                    stores,
                    display_func=lambda s: (
                        f"{s.get('name')} - {s.get('address')}, {s.get('city')} "
                        f"[{s.get('distance'):.2f} km/m]"
                        if s.get("distance") is not None
                        else f"{s.get('name')} - {s.get('address')}, {s.get('city')}"
                    ),
                    prompt="Select a store",
                )
                resolved_store_id = selected_store["id"]

    if args.choose_flyer:
        flyers = driver.discover_flyers(resolved_store_id)
        if not flyers:
            logger.warning(
                f"No flyer catalogs discovered for store ID: {resolved_store_id}"
            )
        elif len(flyers) == 1:
            selected = [flyers[0]["id"]]
            if args.supermarket == "coop":
                driver.selected_flyer_ids = selected
            elif args.supermarket == "conad":
                driver.selected_flyer_slugs = selected
        elif not sys.stdin.isatty():
            logger.warning(
                "Non-interactive terminal detected. Defaulting to first flyer to prevent heavy scraping."
            )
            selected = [flyers[0]["id"]]
            if args.supermarket == "coop":
                driver.selected_flyer_ids = selected
            elif args.supermarket == "conad":
                driver.selected_flyer_slugs = selected
        else:
            print("\nAvailable promotional flyers:")
            for idx, flyer in enumerate(flyers):
                featured_str = " (Featured)" if flyer.get("featured") else ""
                print(
                    f"  {idx + 1}) {flyer.get('title')}{featured_str} [Validity: {flyer.get('validity')}]"
                )

            while True:
                try:
                    user_input = input(
                        "Select flyer(s) to scrape (comma-separated indices, e.g. 1,3 or 'all', default: all): "
                    ).strip()
                    if not user_input or user_input.lower() == "all":
                        selected = [f["id"] for f in flyers]
                        break
                    indices = [
                        int(i.strip())
                        for i in user_input.split(",")
                        if i.strip().isdigit()
                    ]
                    valid_indices = [i - 1 for i in indices if 0 <= i - 1 < len(flyers)]
                    if valid_indices:
                        selected = [flyers[i]["id"] for i in valid_indices]
                        break
                    else:
                        print("Invalid selection. Please try again.")
                except ValueError:
                    print("Invalid input format. Use numbers separated by commas.")
                except (KeyboardInterrupt, EOFError):
                    print("\nSelection interrupted. Defaulting to first flyer.")
                    selected = [flyers[0]["id"]]
                    break

            if args.supermarket == "coop":
                driver.selected_flyer_ids = selected
            elif args.supermarket == "conad":
                driver.selected_flyer_slugs = selected

    # 3. Execute ETL Scrape & Parsing
    logger.info(
        f"Running scraper strategy for: {args.supermarket.upper()} (Store: {resolved_store_id})"
    )
    try:
        offers = driver.run_etl(resolved_store_id)
        if not offers:
            logger.warning(
                "No promotions extracted or returned by the driver. Process completed with 0 listings."
            )
            sys.exit(0)

        logger.info(
            f"Extracted and validated {len(offers)} promotional items from raw source."
        )

        # 4. Persist to Database with UPSERT
        saved_count = save_offers(args.db_path, offers)
        logger.info(
            f"ETL pipeline finished successfully. Total records upserted: {saved_count}"
        )

    except Exception as e:
        logger.critical(f"Critical error during ETL execution: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
