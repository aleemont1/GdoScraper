#!/usr/bin/env python3
import os
import sys
import time
import shutil
import subprocess

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

def get_python_executable():
    """Returns the path to the current virtual environment python executable or fallback to sys.executable."""
    # Try Unix path
    venv_py = os.path.join(".venv", "bin", "python")
    
    # Try Windows path
    import sys
    if sys.platform.startswith("win"):
        win_path = os.path.join(".venv", "Scripts", "python.exe")
        if os.path.exists(win_path):
            venv_py = win_path
            
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

PYTHON_EXE = get_python_executable()

# ANSI Color Codes for premium visual TUI
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    """Prints the GDO Supermarket Scraper CLI banner."""
    banner = fr"""
{BLUE}{BOLD}   _   _  _ _____ ___   ___ ___  _____     _____ ___ 
  /_\ | \| |_   _|_ _| / __| _ \/ _ \ \   / / __| _ \\
 / _ \| .` | | |  | | | (_ |   / (_) \ \_/ /| _||   /
/_/ \_\_|\_| |_| |___| \___|_|_\\___/ \___/ |___|_|_\\
{CYAN}        -- GDO Supermarket Scraper: Interactive Control CLI --{RESET}
    """
    print(banner)

def run_command(cmd_list, capture_time=False):
    """Executes a subprocess command while tracking execution time."""
    print(f"\n{YELLOW}{BOLD}Executing:{RESET} {' '.join(cmd_list)}")
    print(f"{YELLOW}" + "-"*60 + f"{RESET}")
    start_time = time.time()
    try:
        # We run the command keeping stdin/stdout interactive
        subprocess.run(cmd_list, check=True)
        elapsed = time.time() - start_time
        if capture_time:
            print(f"\n{GREEN}{BOLD}Execution completed successfully in {elapsed:.2f} seconds!{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"\n{RED}{BOLD}Error:{RESET} Command failed with exit code {e.returncode}")
    except KeyboardInterrupt:
        print(f"\n{RED}{BOLD}Execution interrupted by user.{RESET}")
    print(f"{YELLOW}" + "-"*60 + f"{RESET}")
    input(f"\nPress Enter to continue...")

def scrape_coop_menu():
    """Interactively configures and triggers the Coop scraper."""
    print(f"\n{GREEN}{BOLD}=== COOP SCRAPER SETTINGS ==={RESET}")
    print("Select Store Location Targeting Mode:")
    print(f"  {CYAN}1{RESET}) Use City Name (Automatic Geocoding & Store Discovery)")
    print(f"  {CYAN}2{RESET}) Use GPS Coordinates (Store Discovery)")
    print(f"  {CYAN}3{RESET}) Use Direct Store Code (e.g. 0315)")
    print(f"  {CYAN}4{RESET}) Use Direct Coop Database Store ID (e.g. 2560)")
    
    mode = input("Select mode [1-4, default: 1]: ").strip()
    if mode == "2":
        store_id = input(f"Enter GPS Coordinates [default: {CYAN}44.1396438,12.2464292{RESET} (Cesena)]: ").strip()
        if not store_id:
            store_id = "44.1396438,12.2464292"
    elif mode == "3":
        store_id = input(f"Enter Coop Store Code (e.g. {CYAN}0315{RESET}): ").strip()
        if not store_id:
            store_id = "0315"
    elif mode == "4":
        store_id = input(f"Enter Coop Database ID (e.g. {CYAN}2560{RESET}): ").strip()
        if not store_id:
            store_id = "2560"
    else:
        store_id = input(f"Enter City Name [default: {CYAN}Cesena{RESET}]: ").strip()
        if not store_id:
            store_id = "Cesena"

    cmd = [
        PYTHON_EXE, "main.py",
        "--supermarket", "coop",
        "--store-id", store_id
    ]

    # Ask if coordinates/city mode was selected
    if mode in ("", "1", "2"):
        radius = input(f"Enter Search Radius in km [default: {CYAN}15{RESET}]: ").strip()
        if not radius:
            radius = "15"
        cmd.extend(["--radius", radius])

        choose_store = input(f"Enable Interactive Store List Selector? [y/N]: ").strip().lower()
        if choose_store == "y":
            cmd.append("--choose-store")

    choose_flyer = input(f"Enable Interactive Flyer Selector? [y/N]: ").strip().lower()
    if choose_flyer == "y":
        cmd.append("--choose-flyer")

    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])

    run_command(cmd, capture_time=True)

def scrape_conad_menu():
    """Interactively configures and triggers the Conad scraper."""
    print(f"\n{GREEN}{BOLD}=== CONAD SCRAPER SETTINGS ==={RESET}")
    print("Select Store Targeting Mode:")
    print(f"  {CYAN}1{RESET}) Use GPS Coordinates (API Store Lookup & Download)")
    print(f"  {CYAN}2{RESET}) Use Direct Store ID (anacanId)")
    
    mode = input("Select mode [1-2, default: 1]: ").strip()
    if mode == "2":
        store_id = input(f"Enter Conad Store ID (anacanId, e.g. {CYAN}005635{RESET}): ").strip()
        if not store_id:
            print(f"{RED}Invalid Store ID. Returning to menu.{RESET}")
            return
        cmd = [PYTHON_EXE, "main.py", "--supermarket", "conad", "--store-id", store_id]
    else:
        coords = input(f"Enter Coordinates [default: {CYAN}44.1396438,12.2464292{RESET} (Cesena)]: ").strip()
        if not coords:
            coords = "44.1396438,12.2464292"
            
        radius = input(f"Enter Search Radius in km [default: {CYAN}5{RESET}]: ").strip()
        if not radius:
            radius = "5"
            
        choose_store = input(f"Enable Interactive Store List Selector? [y/N]: ").strip().lower()
        
        cmd = [
            PYTHON_EXE, "main.py", 
            "--supermarket", "conad", 
            "--store-id", coords,
            "--radius", radius
        ]
        if choose_store == "y":
            cmd.append("--choose-store")
            
    choose_flyer = input(f"Enable Interactive Flyer Selector? [y/N]: ").strip().lower()
    if choose_flyer == "y":
        cmd.append("--choose-flyer")

    # Multiprocessing parallel parsing choice
    parallel = input(f"Enable multi-process parallel flyer parsing? [y/N]: ").strip().lower()
    if parallel == "y":
        cmd.append("--parallel")

    # Optional limits
    max_flyers = input(f"Limit max flyer downloads? [Enter for no limit, or integer]: ").strip()
    if max_flyers.isdigit():
        cmd.extend(["--max-flyers", max_flyers])
        
    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])
        
    run_command(cmd, capture_time=True)

def scrape_ins_menu():
    """Interactively configures and triggers the IN's Mercato scraper."""
    print(f"\n{GREEN}{BOLD}=== IN'S MERCATO SCRAPER SETTINGS ==={RESET}")
    print("Select Store Location Targeting Mode:")
    print(f"  {CYAN}1{RESET}) Use GPS Coordinates (Dynamic Discovery & Download)")
    print(f"  {CYAN}2{RESET}) Use Direct Store/Region Code (e.g. E-Campagna-OF)")
    
    mode = input("Select mode [1-2, default: 1]: ").strip()
    if mode == "2":
        store_id = input(f"Enter IN's Store Code [default: {CYAN}E-Campagna-OF{RESET}]: ").strip()
        if not store_id:
            store_id = "E-Campagna-OF"
    else:
        store_id = input(f"Enter GPS Coordinates [default: {CYAN}44.1396438,12.2464292{RESET} (Cesena)]: ").strip()
        if not store_id:
            store_id = "44.1396438,12.2464292"

    cmd = [
        PYTHON_EXE, "main.py",
        "--supermarket", "ins",
        "--store-id", store_id
    ]

    # Choice of Parsing / OCR Engine
    print("Select Parsing/OCR Engine:")
    print(f"  {CYAN}1{RESET}) Auto-Detect (Offline OCR / Vector Grid)")
    print(f"  {CYAN}2{RESET}) Offline Tesseract OCR (Scanned Fallback)")
    print(f"  {CYAN}3{RESET}) Gemini 2.5 Flash API (Structured Multimodal)")
    print(f"  {CYAN}4{RESET}) Claude Haiku 4.5 API (Structured Multimodal)")
    engine_choice = input("Select engine [1-4, default: 1]: ").strip()
    if engine_choice == "2":
        cmd.extend(["--engine", "TESSERACT"])
    elif engine_choice == "3":
        cmd.extend(["--engine", "GEMINI"])
    elif engine_choice == "4":
        cmd.extend(["--engine", "CLAUDE"])
    else:
        cmd.extend(["--engine", "AUTO"])

    # Multiprocessing parallel parsing choice
    parallel = input(f"Enable multi-process parallel flyer parsing? [y/N]: ").strip().lower()
    if parallel == "y":
        cmd.append("--parallel")

    # Optional limits
    max_flyers = input(f"Limit max flyer downloads? [Enter for no limit, or integer]: ").strip()
    if max_flyers.isdigit():
        cmd.extend(["--max-flyers", max_flyers])
        
    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])
        
    run_command(cmd, capture_time=True)

def scrape_dpiu_menu():
    """Interactively configures and triggers the Dpiù scraper."""
    print(f"\n{GREEN}{BOLD}=== DPIÙ SCRAPER SETTINGS ==={RESET}")
    print("Select Store Location Targeting Mode:")
    print(f"  {CYAN}1{RESET}) Use City Name (Automatic Geocoding & Store Discovery)")
    print(f"  {CYAN}2{RESET}) Use GPS Coordinates (Store Discovery)")
    print(f"  {CYAN}3{RESET}) Use Direct Store Alias (e.g. d-cesena)")
    
    mode = input("Select mode [1-3, default: 1]: ").strip()
    if mode == "2":
        store_id = input(f"Enter GPS Coordinates [default: {CYAN}44.1396438,12.2464292{RESET} (Cesena)]: ").strip()
        if not store_id:
            store_id = "44.1396438,12.2464292"
    elif mode == "3":
        store_id = input(f"Enter Dpiù Store Alias [default: {CYAN}d-cesena{RESET}]: ").strip()
        if not store_id:
            store_id = "d-cesena"
    else:
        store_id = input(f"Enter City Name [default: {CYAN}Cesena{RESET}]: ").strip()
        if not store_id:
            store_id = "Cesena"

    cmd = [
        PYTHON_EXE, "main.py",
        "--supermarket", "dpiu",
        "--store-id", store_id
    ]

    # Ask if coordinates/city mode was selected
    if mode in ("", "1", "2"):
        radius = input(f"Enter Search Radius in km [default: {CYAN}15{RESET}]: ").strip()
        if not radius:
            radius = "15"
        cmd.extend(["--radius", radius])

        choose_store = input(f"Enable Interactive Store List Selector? [y/N]: ").strip().lower()
        if choose_store == "y":
            cmd.append("--choose-store")

    # Optional limits
    max_flyers = input(f"Limit max flyer downloads? [Enter for no limit, or integer]: ").strip()
    if max_flyers.isdigit():
        cmd.extend(["--max-flyers", max_flyers])
        
    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])
        
    run_command(cmd, capture_time=True)

def scrape_manual_menu():
    """Interactively configures and triggers the manual flyer parser."""
    print(f"\n{GREEN}{BOLD}=== MANUAL FLYER SCRAPER SETTINGS ==={RESET}")
    print("Scrapes a manual PDF flyer located in downloads/uploaded/ or specified by file path.")
    
    file_ref = input("Enter PDF file name/path (e.g. flyer.pdf): ").strip()
    if not file_ref:
        print(f"{RED}No file reference provided. Returning to menu.{RESET}")
        time.sleep(1.5)
        return

    supermarket_name = input("Enter supermarket name [default: MANUAL]: ").strip()
    if not supermarket_name:
        supermarket_name = "MANUAL"

    store_id = input("Enter store ID for tagging [default: MANUAL_STORE]: ").strip()
    if not store_id:
        store_id = "MANUAL_STORE"

    cmd = [
        PYTHON_EXE, "main.py",
        "--supermarket", "manual",
        "--store-id", file_ref,
        "--custom-supermarket", supermarket_name
    ]

    # Choice of Parsing / OCR Engine
    print("\nSelect Parsing/OCR Engine:")
    print(f"  {CYAN}1{RESET}) Auto-Detect (Offline OCR / Vector Grid)")
    print(f"  {CYAN}2{RESET}) Offline Tesseract OCR (Scanned Fallback)")
    print(f"  {CYAN}3{RESET}) Gemini 2.5 Flash API (Structured Multimodal)")
    print(f"  {CYAN}4{RESET}) Claude Haiku 4.5 API (Structured Multimodal)")
    engine_choice = input("Select engine [1-4, default: 1]: ").strip()
    if engine_choice == "2":
        cmd.extend(["--engine", "TESSERACT"])
    elif engine_choice == "3":
        cmd.extend(["--engine", "GEMINI"])
    elif engine_choice == "4":
        cmd.extend(["--engine", "CLAUDE"])
    else:
        cmd.extend(["--engine", "AUTO"])

    # Multiprocessing parallel parsing choice
    parallel = input(f"Enable multi-process parallel flyer parsing? [y/N]: ").strip().lower()
    if parallel == "y":
        cmd.append("--parallel")

    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])

    run_command(cmd, capture_time=True)

def launch_dashboard():
    """Launches the visual verification SPA web dashboard server."""
    print(f"\n{GREEN}{BOLD}=== LAUNCHING VISUAL SPA DASHBOARD ==={RESET}")
    print(f"{CYAN}Initializing dashboard server at http://localhost:8000 ...{RESET}")
    print(f"{YELLOW}Press Ctrl+C to terminate the dashboard server.{RESET}\n")
    try:
        subprocess.run([PYTHON_EXE, "dashboard.py"])
    except KeyboardInterrupt:
        print(f"\n{RED}Dashboard server terminated.{RESET}")
    input(f"\nPress Enter to return to main menu...")

def display_db_stats():
    """Queries and displays analytics from the active database storage engine."""
    print(f"\n{GREEN}{BOLD}=== DATABASE ANALYTICS ==={RESET}")
    
    from storage.database import get_storage
    storage = get_storage()
    engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
    
    if engine != "supabase":
        db_path = getattr(storage, "db_path", "storage/promotions.db")
        if not os.path.exists(db_path):
            print(f"{RED}Database not found at '{db_path}'. Run a scraper first to initialize it!{RESET}")
            input("\nPress Enter to return to main menu...")
            return
        
    try:
        breakdown = storage.get_stats()
        total_promos = sum(b.get("total_offers", 0) for b in breakdown)
        
        # In-memory category count estimation from offers list
        offers = storage.get_offers()
        category_counts = {}
        for o in offers:
            cat = o.get("category")
            if cat and cat.strip():
                category_counts[cat] = category_counts.get(cat, 0) + 1
        top_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        if engine == "supabase":
            url = getattr(storage, "url", "Supabase")
            print(f"Database: {MAGENTA}{url} (Supabase){RESET}")
        else:
            db_path = getattr(storage, "db_path", "storage/promotions.db")
            print(f"Database File: {MAGENTA}{db_path}{RESET}")
            
        print(f"Total Promotion Offers Stored: {CYAN}{BOLD}{total_promos}{RESET}")
        print("\n" + "="*70)
        print(f"{BOLD}{'SUPERMARKET':15} | {'STORE ID':10} | {'OFFERS':10} | {'MIN PRICE':10} | {'MAX PRICE':10}{RESET}")
        print("-"*70)
        for row in breakdown:
            superm = row.get("supermarket", "N/A")
            store = row.get("store_id", "N/A")
            count = row.get("total_offers", 0)
            min_pr = row.get("min_price")
            max_pr = row.get("max_price")
            min_pr_str = f"{min_pr:.2f} €" if min_pr is not None else "N/A"
            max_pr_str = f"{max_pr:.2f} €" if max_pr is not None else "N/A"
            print(f"{superm:15} | {store:10} | {count:10d} | {min_pr_str:10} | {max_pr_str:10}")
        print("="*70)
        
        if top_cats:
            print(f"\n{BOLD}Top 5 Popular Scraped Categories:{RESET}")
            for cat, cnt in top_cats:
                print(f"  - {cat:20} : {cnt} offers")
                
    except Exception as e:
        print(f"{RED}Error while querying database statistics: {e}{RESET}")
        
    input("\nPress Enter to return to main menu...")

def dev_tools_menu():
    """Developer maintenance tools and benchmarks."""
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print(f"\n{RED}{BOLD}=== DEVELOPER TOOLS & benchmark utilities ==={RESET}")
        print("Select a developer option:")
        print(f"  [{CYAN}1{RESET}] Clear SQLite Database (reset promotions.db)")
        print(f"  [{CYAN}2{RESET}] Clear Cropped Images (delete all cached product PNGs)")
        print(f"  [{CYAN}3{RESET}] Clear Downloaded Conad & IN's PDF Flyer Cache")
        print(f"  [{RED}4{RESET}] {BOLD}FULL STORAGE WIPE{RESET} (Reset DB, Images, and PDFs)")
        print("-"*65)
        print(f"  [{GREEN}5{RESET}] {BOLD}Benchmark{RESET}: Run Conad Scrape (All Flyers) - {BOLD}Sequential Mode{RESET}")
        print(f"  [{GREEN}6{RESET}] {BOLD}Benchmark{RESET}: Run Conad Scrape (All Flyers) - {BOLD}Parallel Mode{RESET}")
        print(f"  [{GREEN}7{RESET}] {BOLD}Preset{RESET}: Run Full Cesena Scrape (Coop + Conad + IN's + Dpiù)")
        print("-"*65)
        print(f"  [{YELLOW}8{RESET}] Return to Main Menu")
        print()
        
        choice = input("Select developer option [1-8]: ").strip()
        
        if choice == "1":
            from storage.database import get_storage
            storage = get_storage()
            engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
            if engine == "supabase":
                confirm = input(f"{RED}{BOLD}WARNING: Clear all records from Supabase promotions table? [y/N]: {RESET}").strip().lower()
                if confirm == "y":
                    if storage.clear_all():
                        print(f"\n{GREEN}Supabase database cleared successfully!{RESET}")
                    else:
                        print(f"\n{RED}Failed to clear Supabase database.{RESET}")
            else:
                db_path = getattr(storage, "db_path", "storage/promotions.db")
                if os.path.exists(db_path):
                    os.remove(db_path)
                    print(f"\n{GREEN}Database '{db_path}' cleared successfully!{RESET}")
                else:
                    print(f"\n{YELLOW}Database '{db_path}' does not exist.{RESET}")
            time.sleep(1.5)
            
        elif choice == "2":
            img_dir = "storage/images"
            if os.path.exists(img_dir):
                shutil.rmtree(img_dir)
                os.makedirs(img_dir, exist_ok=True)
                print(f"\n{GREEN}All cropped images inside '{img_dir}/' deleted!{RESET}")
            else:
                print(f"\n{YELLOW}Images directory '{img_dir}' does not exist.{RESET}")
            time.sleep(1.5)
            
        elif choice == "3":
            for pdf_dir in ["downloads/conad", "downloads/ins"]:
                if os.path.exists(pdf_dir):
                    shutil.rmtree(pdf_dir)
                    os.makedirs(pdf_dir, exist_ok=True)
            print(f"\n{GREEN}Downloaded Conad and IN's PDF flyers cleared!{RESET}")
            time.sleep(1.5)
            
        elif choice == "4":
            confirm = input(f"{RED}{BOLD}WARNING: This will wipe ALL databases, downloaded PDFs, and cropped images! Proceed? [y/N]: {RESET}").strip().lower()
            if confirm == "y":
                from storage.database import get_storage
                storage = get_storage()
                engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
                if engine == "supabase":
                    storage.clear_all()
                    print(f"\n{GREEN}Supabase promotions table cleared!{RESET}")
                
                for path in ["storage/promotions.db", "storage/images", "downloads/conad", "downloads/ins"]:
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                            if "images" in path:
                                os.makedirs("storage/images", exist_ok=True)
                            elif "conad" in path:
                                os.makedirs("downloads/conad", exist_ok=True)
                            elif "ins" in path:
                                os.makedirs("downloads/ins", exist_ok=True)
                        else:
                            os.remove(path)
                print(f"\n{GREEN}{BOLD}FULL WIPE COMPLETED SUCCESSFULLY!{RESET}")
            else:
                print("\nWipe cancelled.")
            time.sleep(1.5)
            
        elif choice == "5":
            print(f"\n{YELLOW}Starting Sequential Benchmark (Scraping all local Conad PDFs)...{RESET}")
            cmd = [PYTHON_EXE, "main.py", "--supermarket", "conad", "--store-id", "all"]
            run_command(cmd, capture_time=True)
            
        elif choice == "6":
            print(f"\n{YELLOW}Starting Multiprocess Parallel Benchmark (Scraping all local Conad PDFs)...{RESET}")
            cmd = [PYTHON_EXE, "main.py", "--supermarket", "conad", "--store-id", "all", "--parallel"]
            run_command(cmd, capture_time=True)
            
        elif choice == "7":
            print(f"\n{YELLOW}Running Full Cesena Scrape Preset...{RESET}")
            # First, Coop Scrape
            print(f"\n{CYAN}Part 1: Scraping Coop Cesena promotions...{RESET}")
            subprocess.run([PYTHON_EXE, "main.py", "--supermarket", "coop", "--store-id", "0315"])
            
            # Second, Conad Scrape in Parallel
            print(f"\n{CYAN}Part 2: Scraping Conad Cesena flyers in parallel...{RESET}")
            subprocess.run([PYTHON_EXE, "main.py", "--supermarket", "conad", "--store-id", "44.1396438,12.2464292", "--parallel"])
            
            # Third, IN's Scrape
            print(f"\n{CYAN}Part 3: Scraping IN's Cesena flyers offline...{RESET}")
            subprocess.run([PYTHON_EXE, "main.py", "--supermarket", "ins", "--store-id", "44.1396438,12.2464292"])
            
            # Fourth, Dpiù Scrape
            print(f"\n{CYAN}Part 4: Scraping Dpiù Cesena promotions...{RESET}")
            cmd = [
                PYTHON_EXE, "main.py",
                "--supermarket", "dpiu",
                "--store-id", "44.1396438,12.2464292",
                "--radius", "15"
            ]
            run_command(cmd, capture_time=True)
            
        elif choice == "8":
            return
        else:
            print(f"\n{RED}Invalid choice! Press Enter to try again...{RESET}")
            input()


def get_running_pids(script_name: str) -> list:
    """Finds all python PIDs running a specific script name, excluding the current process."""
    try:
        output = subprocess.check_output(["pgrep", "-f", script_name], text=True)
        pids = []
        my_pid = os.getpid()
        for line in output.split("\n"):
            line = line.strip()
            if line and line.isdigit():
                pid = int(line)
                if pid != my_pid:
                    # Double check it is actually a python process running the target script
                    try:
                        with open(f"/proc/{pid}/cmdline", "rb") as f:
                            cmdline = f.read().decode("utf-8", errors="ignore")
                        # cmdline uses null bytes to separate args in /proc
                        cmd_args = cmdline.split("\x00")
                        has_python = any("python" in arg for arg in cmd_args)
                        has_script = any(script_name in arg for arg in cmd_args)
                        if has_python and has_script:
                            pids.append(pid)
                    except Exception:
                        pass
        return pids
    except subprocess.CalledProcessError:
        return []


def kill_processes(script_name: str) -> int:
    """Terminates all processes running a specific script. Returns the count of terminated processes."""
    import signal
    pids = get_running_pids(script_name)
    if not pids:
        return 0
        
    # Send SIGTERM first
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
            
    # Wait up to 2 seconds for graceful shutdown
    start = time.time()
    while time.time() - start < 2.0:
        still_running = get_running_pids(script_name)
        if not still_running:
            break
        time.sleep(0.2)
        
    # Force kill any remaining processes
    remaining = get_running_pids(script_name)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
            
    return len(pids)


def shutdown_all_processes(silent=False):
    """Finds and terminates all active dashboard and scraper processes."""
    if not silent:
        print(f"\n{RED}{BOLD}=== SHUTTING DOWN PROCESSES ==={RESET}")
    
    scrapers_killed = kill_processes("main.py")
    if not silent:
        if scrapers_killed > 0:
            print(f"{GREEN}Terminated {scrapers_killed} running scraper processes.{RESET}")
        else:
            print(f"No running scrapers found.")
            
    dashboards_killed = kill_processes("dashboard.py")
    if not silent:
        if dashboards_killed > 0:
            print(f"{GREEN}Terminated {dashboards_killed} running dashboard server processes.{RESET}")
        else:
            print(f"No running dashboard server found.")
            
    if not silent:
        print(f"\n{GREEN}{BOLD}Shutdown sequence completed.{RESET}")
        input("\nPress Enter to continue...")


def hard_reload_system():
    """Shuts down all processes, starts a fresh background dashboard, and reboots the interactive CLI."""
    print(f"\n{RED}{BOLD}=== HARD RELOADING SYSTEM ==={RESET}")
    print("Initiating full shutdown of all processes...")
    
    # 1. Terminate everything
    shutdown_all_processes(silent=True)
    
    # 2. Launch dashboard.py in background
    print("Restarting dashboard server in background...")
    log_dir = "storage/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "dashboard_reboot.log")
    try:
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n--- REBOOT SYSTEM START {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_file.flush()
        
        # Start background server
        subprocess.Popen(
            [PYTHON_EXE, "dashboard.py"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True
        )
        print(f"{GREEN}Dashboard server launched (logs at {log_path}).{RESET}")
    except Exception as e:
        print(f"{RED}Failed to restart dashboard: {e}{RESET}")
        
    print(f"\n{GREEN}{BOLD}Rebooting interactive control CLI...{RESET}")
    time.sleep(1.5)
    
    # 3. Re-execute TUI cleanly
    os.execv(PYTHON_EXE, [PYTHON_EXE, "run_interactive.py"])


def main_menu():
    """Renders the main menu interface loop for the GDO Scraper CLI."""
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print_banner()
        print(f"{BOLD}Main Options Menu:{RESET}")
        print(f"  [{GREEN}1{RESET}] {BOLD}COOP{RESET}: Scrape API promotions")
        print(f"  [{GREEN}2{RESET}] {BOLD}CONAD{RESET}: Scrape PDF flyers (REST Discovery/Download/Parallel)")
        print(f"  [{GREEN}3{RESET}] {BOLD}IN'S{RESET}: Scrape PDF flyers (BeautifulSoup Crawler/Dual-Engine OCR)")
        print(f"  [{GREEN}4{RESET}] {BOLD}DPIÙ{RESET}: Scrape API promotions (REST Dynamic OAuth2)")
        print(f"  [{GREEN}5{RESET}] {BOLD}MANUAL{RESET}: Scrape a manually uploaded PDF flyer")
        print(f"  [{GREEN}6{RESET}] {BOLD}DASHBOARD{RESET}: Launch visual verification server SPA")
        print(f"  [{GREEN}7{RESET}] {BOLD}STATS{RESET}: Display database analytics")
        print(f"  [{RED}8{RESET}] {BOLD}DEV TOOLS{RESET}: Developer utilities & benchmark presets")
        print(f"  [{RED}9{RESET}] {BOLD}SHUTDOWN{RESET}: Kill all scraper & dashboard processes")
        print(f"  [{RED}10{RESET}] {BOLD}HARD RELOAD{RESET}: Shutdown everything and reboot the TUI")
        print(f"  [{RED}11{RESET}] {BOLD}EXIT{RESET}: Close control CLI")
        print()
        
        choice = input("Select an option [1-11]: ").strip()
        if choice == "1":
            scrape_coop_menu()
        elif choice == "2":
            scrape_conad_menu()
        elif choice == "3":
            scrape_ins_menu()
        elif choice == "4":
            scrape_dpiu_menu()
        elif choice == "5":
            scrape_manual_menu()
        elif choice == "6":
            launch_dashboard()
        elif choice == "7":
            display_db_stats()
        elif choice == "8":
            dev_tools_menu()
        elif choice == "9":
            shutdown_all_processes()
        elif choice == "10":
            hard_reload_system()
        elif choice == "11":
            print(f"\n{CYAN}Thank you for using GDO Scraper. Goodbye!{RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{RED}Invalid choice! Press Enter to try again...{RESET}")
            input()

if __name__ == "__main__":
    main_menu()
