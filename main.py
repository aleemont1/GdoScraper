import argparse
import sys
from utils.logger import setup_logger
from storage.database import initialize_db, save_offers
from drivers.coop.coop_driver import CoopSupermarketDriver
from drivers.conad.conad_driver import ConadSupermarketDriver

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
        choices=["coop", "conad"],
        required=True,
        help="Supermarket chain to scrape (coop or conad)."
    )
    parser.add_argument(
        "--store-id",
        required=True,
        help="Specific store ID (e.g. '0315' for Coop Cesena)."
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
        
    driver = None
    if args.supermarket == "coop":
        driver = CoopSupermarketDriver()
    elif args.supermarket == "conad":
        driver = ConadSupermarketDriver()
        
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
