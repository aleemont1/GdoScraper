#!/usr/bin/env python3
import os
import sys
import subprocess
import sqlite3
import re

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
    banner = f"""
{BLUE}{BOLD}   _   _  _ _____ ___   ___ ___  _____     _____ ___ 
  /_\ | \| |_   _|_ _| / __| _ \/ _ \ \   / / __| _ \\
 / _ \| .` | | |  | | | (_ |   / (_) \ \_/ /| _||   /
/_/ \_\_|\_| |_| |___| \___|_|_\\\\___/ \___/ |___|_|_\\
{CYAN}        -- GDO Supermarket Scraper: Interactive Control CLI --{RESET}
    """
    print(banner)

def run_command(cmd_list):
    print(f"\n{YELLOW}{BOLD}Executing:{RESET} {' '.join(cmd_list)}")
    print(f"{YELLOW}" + "-"*60 + f"{RESET}")
    try:
        # We run the command keeping stdin/stdout interactive
        subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n{RED}{BOLD}Error:{RESET} Command failed with exit code {e.returncode}")
    except KeyboardInterrupt:
        print(f"\n{RED}{BOLD}Execution interrupted by user.{RESET}")
    print(f"{YELLOW}" + "-"*60 + f"{RESET}")
    input(f"\nPress Enter to return to the main menu...")

def scrape_coop_menu():
    print(f"\n{GREEN}{BOLD}=== COOP SCRAPER SETTINGS ==={RESET}")
    store_id = input(f"Enter Coop Store ID [default: {CYAN}0315{RESET} for Cesena]: ").strip()
    if not store_id:
        store_id = "0315"
        
    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if not db_path:
        db_path = "storage/promotions.db"
        
    cmd = [sys.executable, "main.py", "--supermarket", "coop", "--store-id", store_id, "--db-path", db_path]
    run_command(cmd)

def scrape_conad_menu():
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
        cmd = [sys.executable, "main.py", "--supermarket", "conad", "--store-id", store_id]
    else:
        coords = input(f"Enter Coordinates [default: {CYAN}44.1396438,12.2464292{RESET} (Cesena)]: ").strip()
        if not coords:
            coords = "44.1396438,12.2464292"
            
        radius = input(f"Enter Search Radius in km [default: {CYAN}5{RESET}]: ").strip()
        if not radius:
            radius = "5"
            
        choose_store = input(f"Enable Interactive Store List Selector? [y/N]: ").strip().lower()
        
        cmd = [
            sys.executable, "main.py", 
            "--supermarket", "conad", 
            "--store-id", coords,
            "--radius", radius
        ]
        if choose_store == "y":
            cmd.append("--choose-store")
            
    # Optional limits
    max_flyers = input(f"Limit max flyer downloads? [Enter for no limit, or integer]: ").strip()
    if max_flyers.isdigit():
        cmd.extend(["--max-flyers", max_flyers])
        
    db_path = input(f"Enter SQLite DB path [default: {CYAN}storage/promotions.db{RESET}]: ").strip()
    if db_path:
        cmd.extend(["--db-path", db_path])
        
    run_command(cmd)

def launch_dashboard():
    print(f"\n{GREEN}{BOLD}=== LAUNCHING VISUAL SPA DASHBOARD ==={RESET}")
    print(f"{CYAN}Initializing dashboard server at http://localhost:8000 ...{RESET}")
    print(f"{YELLOW}Press Ctrl+C to terminate the dashboard server.{RESET}\n")
    try:
        subprocess.run([sys.executable, "dashboard.py"])
    except KeyboardInterrupt:
        print(f"\n{RED}Dashboard server terminated.{RESET}")
    input(f"\nPress Enter to return to main menu...")

def display_db_stats():
    print(f"\n{GREEN}{BOLD}=== SQLITE DATABASE ANALYTICS ==={RESET}")
    db_path = "storage/promotions.db"
    if not os.path.exists(db_path):
        print(f"{RED}Database not found at '{db_path}'. Run a scraper first to initialize it!{RESET}")
        input("\nPress Enter to return to main menu...")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Total promos count
        cursor.execute("SELECT count(*) FROM promotions")
        total_promos = cursor.fetchone()[0]
        
        # 2. Aggregates by supermarket & store ID
        cursor.execute("""
            SELECT supermarket, store_id, count(*), min(price), max(price) 
            FROM promotions 
            GROUP BY supermarket, store_id
            ORDER BY count(*) DESC
        """)
        rows = cursor.fetchall()
        
        # 3. Print stats
        print(f"Database File: {MAGENTA}{db_path}{RESET}")
        print(f"Total Promotion Offers Stored: {CYAN}{BOLD}{total_promos}{RESET}")
        print("\n" + "="*70)
        print(f"{BOLD}{'SUPERMARKET':15} | {'STORE ID':10} | {'OFFERS':10} | {'MIN PRICE':10} | {'MAX PRICE':10}{RESET}")
        print("-"*70)
        for row in rows:
            superm, store, count, min_pr, max_pr = row
            min_pr = f"{min_pr:.2f} €" if min_pr is not None else "N/A"
            max_pr = f"{max_pr:.2f} €" if max_pr is not None else "N/A"
            print(f"{superm:15} | {store:10} | {count:10d} | {min_pr:10} | {max_pr:10}")
        print("="*70)
        
        # 4. Show top categories
        cursor.execute("""
            SELECT category, count(*) 
            FROM promotions 
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category 
            ORDER BY count(*) DESC 
            LIMIT 5
        """)
        top_cats = cursor.fetchall()
        if top_cats:
            print(f"\n{BOLD}Top 5 Popular Scraped Categories:{RESET}")
            for cat, cnt in top_cats:
                print(f"  - {cat:20} : {cnt} offers")
                
        conn.close()
    except sqlite3.Error as e:
        print(f"{RED}SQLite Error while querying statistics: {e}{RESET}")
        
    input("\nPress Enter to return to main menu...")

def main_menu():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print_banner()
        print(f"{BOLD}Main Options Menu:{RESET}")
        print(f"  [{GREEN}1{RESET}] {BOLD}COOP{RESET}: Scrape API promotions")
        print(f"  [{GREEN}2{RESET}] {BOLD}CONAD{RESET}: Scrape PDF flyers (REST Discovery/Download)")
        print(f"  [{GREEN}3{RESET}] {BOLD}DASHBOARD{RESET}: Launch visual verification server SPA")
        print(f"  [{GREEN}4{RESET}] {BOLD}STATS{RESET}: Display SQLite database analytics")
        print(f"  [{RED}5{RESET}] {BOLD}EXIT{RESET}: Close control CLI")
        print()
        
        choice = input("Select an option [1-5]: ").strip()
        if choice == "1":
            scrape_coop_menu()
        elif choice == "2":
            scrape_conad_menu()
        elif choice == "3":
            launch_dashboard()
        elif choice == "4":
            display_db_stats()
        elif choice == "5":
            print(f"\n{CYAN}Thank you for using GDO Scraper. Goodbye!{RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{RED}Invalid choice! Press Enter to try again...{RESET}")
            input()

if __name__ == "__main__":
    main_menu()
