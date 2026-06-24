import os
import sys
import subprocess


# Self-healing virtualenv re-execution
def _ensure_virtualenv():
    """
    Guarantees the dashboard server and its manual upload parsers run inside
    the project's virtual environment (.venv) where all GDO scraping libraries are installed.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Try Unix-like path first
    venv_python = os.path.join(script_dir, ".venv", "bin", "python")

    # Try Windows path
    if sys.platform.startswith("win"):
        win_path = os.path.join(script_dir, ".venv", "Scripts", "python.exe")
        if os.path.exists(win_path):
            venv_python = win_path

    # If the local venv python exists and we are not already running on it, re-execute
    if os.path.exists(venv_python) and os.path.abspath(
        sys.executable
    ) != os.path.abspath(venv_python):
        print(f"\n[Dashboard] 🔄 Running on global Python ({sys.executable}).")
        print(
            f"[Dashboard] 🚀 Self-healing: Re-executing inside the uv virtual environment ({venv_python})...\n"
        )

        cmd = [venv_python] + sys.argv
        try:
            # Replace current process image cleanly on Unix-like systems
            os.execv(venv_python, cmd)
        except Exception:
            # Fallback subprocess call if execv fails
            sys.exit(subprocess.call(cmd))


_ensure_virtualenv()

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

import http.server  # noqa: E402
import socketserver  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
import uuid  # noqa: E402
from typing import Dict, Any, Optional  # noqa: E402
from email.parser import BytesParser  # noqa: E402

PORT = 8000
DB_PATH = "storage/promotions.db"

# Background ETL task tracker
ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}
ACTIVE_TASKS_LOCK = threading.Lock()


def get_driver_by_name(supermarket: str, radius: int = 15) -> Optional[Any]:
    """Helper to retrieve a concrete driver strategy instance by name."""
    if supermarket == "coop":
        from drivers.coop.coop_driver import CoopSupermarketDriver

        return CoopSupermarketDriver(radius=radius)
    elif supermarket == "conad":
        from drivers.conad.conad_driver import ConadSupermarketDriver

        return ConadSupermarketDriver(radius=radius)
    elif supermarket == "ins":
        from drivers.ins.ins_driver import INSSupermarketDriver

        return INSSupermarketDriver()
    elif supermarket == "dpiu":
        from drivers.dpiu.dpiu_driver import DpiuSupermarketDriver

        return DpiuSupermarketDriver(radius=radius)
    return None


class DashboardHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP Request Handler serving static SPA dashboard assets and exposing API
    endpoints for searching stores, listing flyers, starting and monitoring scrapers.
    """

    def do_GET(self) -> None:
        """Handles GET requests for static files and REST API endpoints."""
        # 1. Route: Fetch promotions from SQLite
        if self.path == "/api/offers":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            response_data = []
            engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
            if engine != "supabase" and not os.path.exists(DB_PATH):
                response_data = {
                    "error": "Database not initialized. Please run main.py first."
                }
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
                return

            try:
                from db_engine.database import get_storage

                storage = get_storage(DB_PATH)
                response_data = storage.get_offers()
            except Exception as e:
                response_data = {"error": f"Database query error: {e}"}
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # 2. Route: Database aggregate statistics
        elif self.path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            response_data = {}
            engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
            if engine != "supabase" and not os.path.exists(DB_PATH):
                response_data = {"error": "Database not initialized"}
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
                return

            try:
                from db_engine.database import get_storage

                storage = get_storage(DB_PATH)
                breakdown = storage.get_stats()
                total_offers = sum(b.get("total_offers", 0) for b in breakdown)
                total_chains = len(set(b.get("supermarket") for b in breakdown))

                response_data = {
                    "total_offers": total_offers,
                    "total_chains": total_chains,
                    "breakdown": breakdown,
                }
            except Exception as e:
                response_data = {"error": f"Database stats error: {e}"}
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # 3. Route: Search supermarket store locations
        elif self.path.startswith("/api/search-stores"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            import urllib.parse

            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)

            supermarket = params.get("supermarket", [""])[0].lower()
            q = params.get("q", [""])[0].strip()
            radius = int(params.get("radius", ["15"])[0])

            if not supermarket or not q:
                self.wfile.write(
                    json.dumps(
                        {"error": "Missing supermarket or search query parameter 'q'"}
                    ).encode("utf-8")
                )
                return

            try:
                driver = get_driver_by_name(supermarket, radius=radius)
                if not driver:
                    self.wfile.write(
                        json.dumps(
                            {"error": f"Unknown supermarket: {supermarket}"}
                        ).encode("utf-8")
                    )
                    return
                stores_list = driver.discover_stores(q)
                self.wfile.write(json.dumps(stores_list).encode("utf-8"))
            except Exception as e:
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to search store locations: {e}"}
                    ).encode("utf-8")
                )
            return

        # 4. Route: Fetch active flyers list for store
        elif self.path.startswith("/api/get-flyers"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            import urllib.parse

            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)

            supermarket = params.get("supermarket", [""])[0].lower()
            store_id = params.get("store_id", [""])[0].strip()

            if not supermarket or not store_id:
                self.wfile.write(
                    json.dumps(
                        {"error": "Missing supermarket or store_id parameter"}
                    ).encode("utf-8")
                )
                return

            try:
                driver = get_driver_by_name(supermarket)
                if not driver:
                    self.wfile.write(
                        json.dumps(
                            {"error": f"Unknown supermarket: {supermarket}"}
                        ).encode("utf-8")
                    )
                    return
                flyers_list = driver.discover_flyers(store_id)
                self.wfile.write(json.dumps(flyers_list).encode("utf-8"))
            except Exception as e:
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to retrieve flyers list: {e}"}
                    ).encode("utf-8")
                )
            return

        # 5. Route: Get active scrape logs
        elif self.path.startswith("/api/scrape/logs"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            import urllib.parse

            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)

            task_id = params.get("task_id", [""])[0].strip()
            if not task_id:
                self.wfile.write(
                    json.dumps({"error": "Missing task_id parameter"}).encode("utf-8")
                )
                return

            status = "unknown"
            log_content = ""

            task = None
            with ACTIVE_TASKS_LOCK:
                task = ACTIVE_TASKS.get(task_id)

            if task:
                process = task["process"]
                poll = process.poll()
                if poll is None:
                    status = "running"
                elif poll == 0:
                    status = "completed"
                    task["log_file"].close()
                    with ACTIVE_TASKS_LOCK:
                        ACTIVE_TASKS.pop(task_id, None)
                else:
                    status = "failed"
                    task["log_file"].close()
                    with ACTIVE_TASKS_LOCK:
                        ACTIVE_TASKS.pop(task_id, None)
                log_path = task["log_path"]
            else:
                log_path = f"storage/logs/{task_id}.log"
                if os.path.exists(log_path):
                    status = "completed"
                else:
                    self.wfile.write(
                        json.dumps(
                            {"error": f"No logs found for session: {task_id}"}
                        ).encode("utf-8")
                    )
                    return

            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_content = f.read()
            except Exception as e:
                log_content = f"[SYSTEM] Failed to read log file contents: {e}"

            self.wfile.write(
                json.dumps({"status": status, "logs": log_content}).encode("utf-8")
            )
            return

        # 6. Route: Serve static product crops and images securely from local storage
        elif self.path.startswith("/storage/") or self.path.startswith("/assets/"):
            import urllib.parse

            decoded_path = urllib.parse.unquote(self.path)
            file_rel_path = decoded_path.lstrip("/")

            base_dir_name = "storage" if self.path.startswith("/storage/") else "assets"
            base_dir_abs = os.path.abspath(base_dir_name)
            requested_path_abs = os.path.abspath(file_rel_path)

            if (
                (
                    requested_path_abs == base_dir_abs
                    or requested_path_abs.startswith(base_dir_abs + os.sep)
                )
                and os.path.exists(requested_path_abs)
                and os.path.isfile(requested_path_abs)
            ):
                self.send_response(200)
                if requested_path_abs.endswith(".png"):
                    self.send_header("Content-type", "image/png")
                elif requested_path_abs.endswith((".jpg", ".jpeg")):
                    self.send_header("Content-type", "image/jpeg")
                else:
                    self.send_header("Content-type", "application/octet-stream")
                self.end_headers()

                with open(requested_path_abs, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Image not found")
            return

        # 7. Route: Serve dashboard static assets securely (preventing traversal attacks)
        elif self.path in ("/", "/index.html", "/dashboard") or self.path.startswith(
            "/dashboard/"
        ):
            path_part = self.path.lstrip("/")
            if not path_part or path_part == "dashboard":
                path_part = "dashboard/index.html"
            elif path_part == "index.html":
                path_part = "dashboard/index.html"

            dashboard_dir_abs = os.path.abspath("dashboard")
            requested_path_abs = os.path.abspath(path_part)

            if (
                (
                    requested_path_abs == dashboard_dir_abs
                    or requested_path_abs.startswith(dashboard_dir_abs + os.sep)
                )
                and os.path.exists(requested_path_abs)
                and os.path.isfile(requested_path_abs)
            ):
                self.send_response(200)
                if requested_path_abs.endswith(".html"):
                    self.send_header("Content-type", "text/html; charset=utf-8")
                elif requested_path_abs.endswith(".css"):
                    self.send_header("Content-type", "text/css; charset=utf-8")
                elif requested_path_abs.endswith(".js"):
                    self.send_header(
                        "Content-type", "application/javascript; charset=utf-8"
                    )
                elif requested_path_abs.endswith(".png"):
                    self.send_header("Content-type", "image/png")
                elif requested_path_abs.endswith(".ico"):
                    self.send_header("Content-type", "image/x-icon")
                else:
                    self.send_header("Content-type", "application/octet-stream")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()

                with open(requested_path_abs, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Static dashboard asset not found")
            return

        # 8. Route: Redirect /docs or /docs/ to /docs/api/index.html to preserve relative paths
        elif self.path.split("?")[0] in ("/docs", "/docs/"):
            self.send_response(302)
            self.send_header("Location", "/docs/api/index.html")
            self.end_headers()
            return

        # 9. Route: Serve generated documentation static assets securely (preventing traversal attacks)
        elif self.path.startswith("/docs/"):
            import urllib.parse

            decoded_path = urllib.parse.unquote(self.path)
            # Remove query parameters from path_part for finding the file
            path_part = decoded_path.split("?")[0].lstrip("/")

            docs_dir_abs = os.path.abspath("docs")
            requested_path_abs = os.path.abspath(path_part)

            # If requesting a directory, serve its index.html
            if os.path.isdir(requested_path_abs):
                requested_path_abs = os.path.join(requested_path_abs, "index.html")

            if (
                (
                    requested_path_abs == docs_dir_abs
                    or requested_path_abs.startswith(docs_dir_abs + os.sep)
                )
                and os.path.exists(requested_path_abs)
                and os.path.isfile(requested_path_abs)
            ):
                self.send_response(200)
                if requested_path_abs.endswith(".html"):
                    self.send_header("Content-type", "text/html; charset=utf-8")
                elif requested_path_abs.endswith(".css"):
                    self.send_header("Content-type", "text/css; charset=utf-8")
                elif requested_path_abs.endswith(".js"):
                    self.send_header(
                        "Content-type", "application/javascript; charset=utf-8"
                    )
                elif requested_path_abs.endswith(".png"):
                    self.send_header("Content-type", "image/png")
                elif requested_path_abs.endswith((".jpg", ".jpeg")):
                    self.send_header("Content-type", "image/jpeg")
                else:
                    self.send_header("Content-type", "application/octet-stream")
                self.end_headers()

                with open(requested_path_abs, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Document not found")
            return

        else:
            # Fallback 404 for unmapped static routes
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

    def do_POST(self) -> None:
        """Handles POST requests for scraping executions and manual flyer uploads."""
        # 1. Route: Manual PDF flyer upload and parse
        if self.path == "/api/upload":
            content_type = self.headers.get("Content-Type")
            if not content_type or "multipart/form-data" not in content_type:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": "Content-Type must be multipart/form-data"}
                    ).encode("utf-8")
                )
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                msg = BytesParser().parsebytes(
                    b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
                )

                supermarket = "MANUAL"
                store_id = "MANUAL_STORE"
                engine = "AUTO"
                pdf_content = None
                pdf_filename = "manual_flyer.pdf"

                if msg.is_multipart():
                    for part in msg.get_payload():
                        name = part.get_param("name", header="content-disposition")
                        if name == "supermarket":
                            supermarket = part.get_payload(decode=True).decode().strip()
                        elif name == "store_id":
                            store_id = part.get_payload(decode=True).decode().strip()
                        elif name == "engine":
                            engine = (
                                part.get_payload(decode=True).decode().strip().upper()
                            )
                        elif name == "use_gemini":
                            val = part.get_payload(decode=True).decode().strip().lower()
                            if val == "true":
                                engine = "GEMINI"
                        elif name == "use_claude":
                            val = part.get_payload(decode=True).decode().strip().lower()
                            if val == "true":
                                engine = "CLAUDE"
                        elif name == "file":
                            pdf_filename = part.get_filename() or "manual_flyer.pdf"
                            pdf_content = part.get_payload(decode=True)

                if not pdf_content:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({"error": "No PDF flyer content uploaded"}).encode(
                            "utf-8"
                        )
                    )
                    return

                os.makedirs("downloads/uploaded", exist_ok=True)
                clean_filename = "".join(
                    c for c in pdf_filename if c.isalnum() or c in (".", "_", "-")
                ).strip()
                if not clean_filename:
                    clean_filename = "manual_flyer.pdf"
                if not clean_filename.endswith(".pdf"):
                    clean_filename += ".pdf"

                file_path = os.path.join("downloads/uploaded", clean_filename)
                with open(file_path, "wb") as f:
                    f.write(pdf_content)

                from drivers.manual.manual_driver import ManualSupermarketDriver
                from db_engine.database import save_offers

                driver = ManualSupermarketDriver(
                    supermarket_name=supermarket, store_id=store_id, engine=engine
                )
                offers = driver.run_etl(file_path)

                if offers:
                    saved_count = save_offers(DB_PATH, offers)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    response = {
                        "success": True,
                        "message": f"Successfully parsed manual PDF '{pdf_filename}'!",
                        "supermarket": supermarket,
                        "store_id": store_id,
                        "offers_count": len(offers),
                        "saved_count": saved_count,
                    }
                    self.wfile.write(json.dumps(response).encode("utf-8"))
                else:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "success": False,
                                "error": "No promotional offers could be parsed from the PDF circular. Make sure the file format matches standard layouts.",
                            }
                        ).encode("utf-8")
                    )
            except Exception as e:
                import traceback

                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "success": False,
                            "error": f"Scraper visual execution failed: {e}",
                        }
                    ).encode("utf-8")
                )
            return

        # 2. Route: Start dynamic automated scraping task
        elif self.path == "/api/scrape/execute":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                supermarket = payload.get("supermarket", "").strip().lower()
                store_id = payload.get("store_id", "").strip()
                flyer_ids = payload.get("flyer_ids", [])
                radius = int(payload.get("radius", 15))
                db_path = payload.get("db_path", "storage/promotions.db").strip()
                parallel = bool(payload.get("parallel", False))
                engine = payload.get("engine", "AUTO").strip().upper()

                if not supermarket or not store_id:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({"error": "Missing supermarket or store_id"}).encode(
                            "utf-8"
                        )
                    )
                    return

                task_id = str(uuid.uuid4().hex)
                os.makedirs("storage/logs", exist_ok=True)
                log_path = f"storage/logs/{task_id}.log"

                if supermarket == "coop" and store_id.isdigit():
                    from drivers.coop.coop_driver import CoopSupermarketDriver

                    driver = CoopSupermarketDriver()
                    driver._fetch_csrf_token()
                    resolved_code, _ = driver._resolve_store_details_by_db_id(
                        int(store_id)
                    )
                    if resolved_code:
                        store_id = resolved_code

                cmd = [
                    sys.executable,
                    "main.py",
                    "--supermarket",
                    supermarket,
                    "--store-id",
                    store_id,
                    "--radius",
                    str(radius),
                    "--db-path",
                    db_path,
                    "--engine",
                    engine,
                ]
                if parallel:
                    cmd.append("--parallel")

                if supermarket == "coop" and flyer_ids:
                    cmd.extend(["--selected-flyer-ids", ",".join(flyer_ids)])
                elif supermarket == "conad" and flyer_ids:
                    cmd.extend(["--selected-flyer-slugs", ",".join(flyer_ids)])

                # Execute background subprocess, redirecting output to log file
                log_file = open(log_path, "w", encoding="utf-8")
                log_file.write(f"[SYSTEM] Spawning subprocess: {' '.join(cmd)}\n")
                log_file.flush()

                process = subprocess.Popen(
                    cmd, stdout=log_file, stderr=subprocess.STDOUT, text=True
                )

                with ACTIVE_TASKS_LOCK:
                    ACTIVE_TASKS[task_id] = {
                        "process": process,
                        "log_file": log_file,
                        "log_path": log_path,
                        "supermarket": supermarket,
                        "store_id": store_id,
                    }

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"success": True, "task_id": task_id}).encode("utf-8")
                )

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to spawn scraper subprocess: {e}"}
                    ).encode("utf-8")
                )
            return

        # 3. Route: Update an offer in the database
        elif self.path == "/api/offers/update":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                supermarket = payload.get("supermarket", "").strip()
                store_id = payload.get("store_id", "").strip()
                offer_id = payload.get("offer_id", "").strip()
                name = payload.get("name", "").strip()
                brand = payload.get("brand", "")
                weight_or_volume = payload.get("weight_or_volume", "")
                price_val = payload.get("price")
                original_price_val = payload.get("original_price")
                discount_percentage_val = payload.get("discount_percentage")
                ean_code = payload.get("ean_code", "")
                category = payload.get("category", "")
                promo_type = payload.get("promo_type", "")

                if (
                    not supermarket
                    or not store_id
                    or not offer_id
                    or not name
                    or price_val is None
                ):
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": "Missing required fields for update (supermarket, store_id, offer_id, name, price)"
                            }
                        ).encode("utf-8")
                    )
                    return

                try:
                    price = float(price_val)
                    original_price = (
                        float(original_price_val)
                        if original_price_val is not None
                        and str(original_price_val).strip() != ""
                        else None
                    )
                    discount_percentage = (
                        int(discount_percentage_val)
                        if discount_percentage_val is not None
                        and str(discount_percentage_val).strip() != ""
                        else None
                    )
                except ValueError as e:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {"error": f"Invalid numeric value formats: {e}"}
                        ).encode("utf-8")
                    )
                    return

                from db_engine.database import get_storage

                storage = get_storage(DB_PATH)
                fields = {
                    "name": name,
                    "brand": brand,
                    "weight_or_volume": weight_or_volume,
                    "price": price,
                    "original_price": original_price,
                    "discount_percentage": discount_percentage,
                    "ean_code": ean_code,
                    "category": category,
                    "promo_type": promo_type,
                }
                success = storage.update_offer(supermarket, store_id, offer_id, fields)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to update database record: {e}"}
                    ).encode("utf-8")
                )
            return

        # 4. Route: Delete an offer from the database
        elif self.path == "/api/offers/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                supermarket = payload.get("supermarket", "").strip()
                store_id = payload.get("store_id", "").strip()
                offer_id = payload.get("offer_id", "").strip()

                if not supermarket or not store_id or not offer_id:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": "Missing required fields for deletion (supermarket, store_id, offer_id)"
                            }
                        ).encode("utf-8")
                    )
                    return

                from db_engine.database import get_storage

                storage = get_storage(DB_PATH)
                success = storage.delete_offer(supermarket, store_id, offer_id)

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to delete database record: {e}"}
                    ).encode("utf-8")
                )
            return

        # 5. Route: Change product image in the database
        elif self.path == "/api/offers/change-image":
            content_type = self.headers.get("Content-Type")
            if not content_type or "multipart/form-data" not in content_type:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": "Content-Type must be multipart/form-data"}
                    ).encode("utf-8")
                )
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                msg = BytesParser().parsebytes(
                    b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
                )

                supermarket = ""
                store_id = ""
                offer_id = ""
                image_content = None
                image_filename = ""

                if msg.is_multipart():
                    for part in msg.get_payload():
                        name = part.get_param("name", header="content-disposition")
                        if name == "supermarket":
                            supermarket = part.get_payload(decode=True).decode().strip()
                        elif name == "store_id":
                            store_id = part.get_payload(decode=True).decode().strip()
                        elif name == "offer_id":
                            offer_id = part.get_payload(decode=True).decode().strip()
                        elif name == "file":
                            image_filename = part.get_filename() or "uploaded_image.png"
                            image_content = part.get_payload(decode=True)

                if not supermarket or not store_id or not offer_id or not image_content:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": "Missing required fields (supermarket, store_id, offer_id, file)"
                            }
                        ).encode("utf-8")
                    )
                    return

                # Check file extension
                ext = os.path.splitext(image_filename)[1].lower()
                if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "error": "Unsupported image format. Only PNG, JPG, JPEG, and WEBP are supported."
                            }
                        ).encode("utf-8")
                    )
                    return

                # Ensure storage/images directory exists
                os.makedirs("storage/images", exist_ok=True)

                # Generate clean unique filename
                import time

                timestamp = int(time.time())
                safe_supermarket = "".join(
                    c for c in supermarket if c.isalnum() or c in ("-", "_")
                ).strip()
                safe_store_id = "".join(
                    c for c in store_id if c.isalnum() or c in ("-", "_")
                ).strip()
                safe_offer_id = "".join(
                    c for c in offer_id if c.isalnum() or c in ("-", "_")
                ).strip()

                new_filename = f"manual_{safe_supermarket}_{safe_store_id}_{safe_offer_id}_{timestamp}{ext}"
                file_path = os.path.join("storage/images", new_filename)

                # Write file content
                with open(file_path, "wb") as f:
                    f.write(image_content)

                # Update database
                db_image_url = f"/storage/images/{new_filename}"
                from db_engine.database import get_storage

                storage = get_storage(DB_PATH)
                success = storage.update_offer(
                    supermarket, store_id, offer_id, {"image_url": db_image_url}
                )

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"success": success, "image_url": db_image_url}).encode(
                        "utf-8"
                    )
                )

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": f"Failed to change product image: {e}"}
                    ).encode("utf-8")
                )
            return

        else:
            self.send_response(404)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Endpoint not found"}).encode("utf-8")
            )
            return


def run_server() -> None:
    """Runs the visual verifier server."""
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    # Initialize database schema dynamically at startup
    from db_engine.database import initialize_db

    try:
        initialize_db(DB_PATH)
    except Exception as e:
        print(f"[Dashboard] Warning: Database initialization failed: {e}")

    with socketserver.ThreadingTCPServer(("", PORT), DashboardHTTPHandler) as httpd:
        print("\n" + "=" * 70)
        print(" GDO SCRAPER - VISUAL VERIFICATION DASHBOARD IS LIVE!")
        print("=" * 70)
        print(f" >>> Server is running on: http://localhost:{PORT}")
        print(" >>> Database read location: storage/promotions.db")
        print(" >>> Press Ctrl+C to terminate the dashboard server.")
        print("=" * 70 + "\n")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard server terminated. Bye!")
            sys.exit(0)


if __name__ == "__main__":
    run_server()
