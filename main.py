import argparse
import sys
import os
from utils.logger import setup_logger
from storage.database import initialize_db, save_offers
from drivers.coop.coop_driver import CoopSupermarketDriver
from drivers.conad.conad_driver import ConadSupermarketDriver
from drivers.ins.ins_driver import INSSupermarketDriver
from drivers.dpiu.dpiu_driver import DpiuSupermarketDriver
from drivers.manual.manual_driver import ManualSupermarketDriver

# Zero-dependency local .env loader to support sandbox and CLI key sharing
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
        help="Supermarket chain to scrape (coop, conad, ins, dpiu, or manual)."
    )
    parser.add_argument(
        "--custom-supermarket",
        default="MANUAL",
        help="Custom supermarket name to use in 'manual' mode (default: MANUAL)."
    )
    parser.add_argument(
        "--use-gemini",
        action="store_true",
        help="Use Gemini 2.5 Flash API for OCR-based flyer scraping instead of local offline Tesseract."
    )
    parser.add_argument(
        "--use-claude",
        action="store_true",
        help="Use Anthropic Claude Haiku 4.5 API for OCR-based flyer scraping."
    )
    parser.add_argument(
        "--engine",
        choices=["AUTO", "TESSERACT", "GEMINI", "CLAUDE"],
        default="AUTO",
        help="Explicitly choose the parsing/OCR engine to use (default: AUTO)."
    )
    parser.add_argument(
        "--store-id",
        required=True,
        help=(
            "Specific store ID (e.g. '0315' for Coop Cesena, or '005635' for Conad, "
            "or coordinate string like '44.1396438,12.2464292' for Conad REST lookup)."
        )
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=5,
        help="Search radius in kilometers for coordinate-based store discovery (default: 5)."
    )
    parser.add_argument(
        "--choose-store",
        action="store_true",
        help="Enable interactive terminal selection menu when multiple stores are found within the search radius."
    )
    parser.add_argument(
        "--choose-flyer",
        action="store_true",
        help="Enable interactive terminal selection menu to choose which Coop flyer(s) to scrape."
    )
    parser.add_argument(
        "--max-flyers",
        type=int,
        default=None,
        help="Limit the maximum number of flyers downloaded and parsed in this run (default: no limit)."
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable multi-process parallel flyer parsing to exploit multi-core CPUs."
    )
    parser.add_argument(
        "--db-path",
        default="storage/promotions.db",
        help="Path to the SQLite database file (default: storage/promotions.db)."
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
        driver = CoopSupermarketDriver(
            radius=args.radius,
            choose_store=args.choose_store,
            choose_flyer=args.choose_flyer
        )
    elif args.supermarket == "conad":
        driver = ConadSupermarketDriver(
            max_flyers=args.max_flyers,
            radius=args.radius,
            choose_store=args.choose_store,
            choose_flyer=args.choose_flyer,
            parallel=args.parallel
        )
    elif args.supermarket == "ins":
        driver = INSSupermarketDriver(
            max_flyers=args.max_flyers,
            parallel=args.parallel,
            use_gemini=(engine == "GEMINI"),
            use_claude=(engine == "CLAUDE"),
            engine=engine
        )
    elif args.supermarket == "dpiu":
        driver = DpiuSupermarketDriver(
            max_flyers=args.max_flyers,
            radius=args.radius,
            choose_store=args.choose_store
        )
    elif args.supermarket == "manual":
        driver = ManualSupermarketDriver(
            supermarket_name=args.custom_supermarket,
            store_id=args.store_id,
            parallel=args.parallel,
            engine=engine
        )
        
    if not driver:
        logger.critical("Failed to instantiate a valid scraper driver strategy.")
        sys.exit(1)
        
    # 3. Execute ETL Scrape & Parsing
    logger.info(f"Running scraper strategy for: {args.supermarket.upper()} (Store: {args.store_id})")
    try:
        offers = driver.run_etl(args.store_id)
        if not offers:
            logger.warning("No promotions extracted or returned by the driver. Process completed with 0 listings.")
            sys.exit(0)
            
        logger.info(f"Extracted and validated {len(offers)} promotional items from raw source.")
        
        # 4. Persist to Database with UPSERT
        saved_count = save_offers(args.db_path, offers)
        logger.info(f"ETL pipeline finished successfully. Total records upserted: {saved_count}")
        
    except Exception as e:
        logger.critical(f"Critical error during ETL execution: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
