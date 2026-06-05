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
    venv_python = os.path.join(script_dir, ".venv", "bin", "python")
    
    # If the local venv python exists and we are not already running on it, re-execute
    if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
        print(f"\n[Dashboard] 🔄 Running on global Python ({sys.executable}).")
        print(f"[Dashboard] 🚀 Self-healing: Re-executing inside the uv virtual environment ({venv_python})...\n")
        
        cmd = [venv_python] + sys.argv
        try:
            # Replace current process image cleanly on Unix-like systems
            os.execv(venv_python, cmd)
        except Exception:
            # Fallback subprocess call if execv fails
            sys.exit(subprocess.call(cmd))

_ensure_virtualenv()

import http.server
import socketserver
import sqlite3
import json
from typing import Dict, Any, List
from email.parser import BytesParser

PORT = 8000
DB_PATH = "storage/promotions.db"

# HTML/CSS/JS single-page app source code for the dashboard
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GDO Scraper - Visual Verifier</title>
    
    <!-- Modern Premium Typography -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    
    <style>
        /* Design Tokens & Variables */
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.6);
            --card-hover: rgba(23, 37, 84, 0.4);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-orange: #f59e0b;
            --accent-red: #ef4444;
            --glass-blur: blur(16px);
            --transition-smooth: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Global Reset */
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 30px 5%;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(59, 82, 246, 0.05) 0%, transparent 40%);
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: var(--bg-color);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--accent-purple);
        }

        /* Typography & Header */
        header {
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #fff 30%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }

        .subtitle {
            font-size: 0.95rem;
            color: var(--text-secondary);
            margin-top: 5px;
        }

        /* Statistics Section & Report Card */
        .stats-panel-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 22px;
            margin-bottom: 30px;
            backdrop-filter: var(--glass-blur);
            transition: var(--transition-smooth);
        }

        .stats-panel-card:hover {
            border-color: rgba(139, 92, 246, 0.2);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
        }

        .stats-list li {
            transition: var(--transition-smooth);
            padding: 8px 10px;
            border-radius: 8px;
        }

        .stats-list li:hover {
            background: rgba(255, 255, 255, 0.03);
            transform: translateX(4px);
        }

        .stats-table {
            width: 100%;
            border-collapse: collapse;
        }

        .stats-table th {
            border-bottom: 1.5px solid var(--border-color);
            padding: 10px 8px;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stats-table td {
            padding: 12px 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .stats-table tbody tr {
            transition: var(--transition-smooth);
        }

        .stats-table tbody tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge-manual {
            background-color: rgba(59, 130, 246, 0.12);
            color: var(--accent-blue);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        /* Control Panel / Filters Card */
        .control-panel {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 22px;
            margin-bottom: 30px;
            backdrop-filter: var(--glass-blur);
            position: relative;
            z-index: 20;
        }


        .filters-grid {
            display: grid;
            grid-template-columns: 2fr 1fr 1fr auto;
            gap: 15px;
            align-items: end;
        }

        @media (max-width: 768px) {
            .filters-grid {
                grid-template-columns: 1fr;
            }
        }

        .input-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        label {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        input, select {
            background-color: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 0.9rem;
            width: 100%;
            transition: var(--transition-smooth);
        }

        input:focus, select:focus {
            outline: none;
            border-color: var(--accent-purple);
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15);
        }

        /* Column Selector Dropdown Checklist */
        .column-selector {
            position: relative;
        }

        .dropdown-btn {
            background-color: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-primary);
            font-size: 0.9rem;
            cursor: pointer;
            text-align: left;
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 170px;
            transition: var(--transition-smooth);
        }

        .dropdown-btn:hover {
            border-color: var(--accent-purple);
        }

        .dropdown-content {
            display: none;
            position: absolute;
            right: 0;
            top: calc(100% + 5px);
            background: #111827;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px;
            z-index: 100;
            min-width: 200px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            max-height: 250px;
            overflow-y: auto;
        }

        .dropdown-content label {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 6px 8px;
            cursor: pointer;
            border-radius: 6px;
            transition: var(--transition-smooth);
            color: var(--text-primary);
            font-size: 0.85rem;
        }

        .dropdown-content label:hover {
            background-color: rgba(255,255,255,0.05);
        }

        .dropdown-content input[type="checkbox"] {
            width: auto;
            cursor: pointer;
        }

        /* Main Table Layout */
        .table-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            backdrop-filter: var(--glass-blur);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            margin-bottom: 30px;
            position: relative;
            z-index: 10;
        }

        .table-responsive {
            overflow-x: auto;
            width: 100%;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }

        th {
            background-color: rgba(0, 0, 0, 0.2);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
            user-select: none;
            cursor: pointer;
        }

        th:hover {
            color: var(--text-primary);
        }

        td {
            padding: 14px 20px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-primary);
            vertical-align: middle;
            max-width: 250px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        tr {
            transition: var(--transition-smooth);
        }

        tr:hover {
            background-color: var(--card-hover);
        }

        tr:last-child td {
            border-bottom: none;
        }

        /* Cell Badge Styles */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-coop {
            background-color: rgba(16, 185, 129, 0.12);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .badge-conad {
            background-color: rgba(245, 158, 11, 0.12);
            color: var(--accent-orange);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        .badge-ins {
            background-color: rgba(139, 92, 246, 0.12);
            color: var(--accent-purple);
            border: 1px solid rgba(139, 92, 246, 0.2);
        }

        .badge-dpiu {
            background-color: rgba(239, 68, 68, 0.12);
            color: var(--accent-red);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .badge-promo {
            background-color: rgba(139, 92, 246, 0.12);
            color: var(--accent-purple);
            border: 1px solid rgba(139, 92, 246, 0.2);
        }

        .price-text {
            font-family: inherit;
            font-weight: 700;
            color: var(--text-primary);
        }

        .price-strikethrough {
            text-decoration: line-through;
            color: var(--accent-red);
            font-size: 0.8rem;
            margin-left: 6px;
        }

        .discount-badge {
            background-color: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-left: 6px;
        }

        /* Footer & Pagination */
        .footer-pagination {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 22px;
            background-color: rgba(0, 0, 0, 0.15);
            border-top: 1px solid var(--border-color);
        }

        .pagination-info {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .pagination-btns {
            display: flex;
            gap: 10px;
        }

        .btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-family: inherit;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition-smooth);
        }

        .btn:hover:not(:disabled) {
            background-color: var(--accent-purple);
            border-color: var(--accent-purple);
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
        }

        .btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }

        /* Error States */
        .error-container {
            padding: 50px;
            text-align: center;
            color: var(--accent-red);
            font-weight: 600;
        }
        
        .empty-container {
            padding: 50px;
            text-align: center;
            color: var(--text-secondary);
            font-weight: 500;
        }

        /* Image Preview Thumbnail & Zoom */
        .thumb-container {
            position: relative;
            width: 42px;
            height: 42px;
            cursor: pointer;
            margin: 0 auto;
        }

        .table-thumb {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            transition: var(--transition-smooth);
            background-color: rgba(255,255,255,0.03);
        }

        .thumb-container:hover .table-thumb {
            border-color: var(--accent-purple);
            transform: scale(1.08);
            box-shadow: 0 0 10px rgba(139, 92, 246, 0.4);
        }

        .thumb-zoom {
            display: none;
            position: absolute;
            left: 55px;
            top: -90px;
            width: 260px;
            height: auto;
            z-index: 1000;
            background: #111827;
            border: 1.5px solid rgba(139, 92, 246, 0.5);
            border-radius: 12px;
            padding: 6px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.7);
            backdrop-filter: var(--glass-blur);
            animation: fadeIn 0.15s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: scale(0.95); }
            to { opacity: 1; transform: scale(1); }
        }

        .thumb-zoom img {
            width: 100%;
            height: auto;
            border-radius: 8px;
            display: block;
        }

        .thumb-container:hover .thumb-zoom {
            display: block;
        }

        /* Center columns alignment */
        .text-center {
            text-align: center;
        }
    </style>
</head>
<body>

    <header>
        <div>
            <h1>GDO Scraper Visual Verifier</h1>
            <div class="subtitle">Visual verification dashboard for extracted supermarket promotions database</div>
        </div>
        <div>
            <button class="btn" onclick="fetchData()">🔄 Reload Data</button>
        </div>
    </header>

    <!-- Manual PDF Circular Upload Panel -->
    <section class="control-panel" style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none;" onclick="toggleUploadPanel()">
            <h2 style="font-size: 1.2rem; font-weight: 700; background: linear-gradient(135deg, #fff 60%, var(--text-secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; display: flex; align-items: center; gap: 8px;">📤 Manual Flyer PDF Visual Scraper</h2>
            <span id="uploadToggleIcon" style="font-size: 0.9rem; color: var(--text-secondary); transition: var(--transition-smooth);">[ Expand Upload Form ▼ ]</span>
        </div>
        
        <div id="uploadPanelContent" style="display: none; margin-top: 20px; border-top: 1px solid var(--border-color); padding-top: 20px; animation: fadeIn 0.2s ease-out;">
            <form id="uploadForm" onsubmit="handleManualUpload(event)" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; align-items: end;">
                <div class="input-group">
                    <label for="pdfFile">Select Flyer PDF</label>
                    <input type="file" id="pdfFile" accept=".pdf" required style="padding: 7px 10px; cursor: pointer;">
                </div>
                <div class="input-group">
                    <label for="uploadSupermarket">Supermarket Name</label>
                    <input type="text" id="uploadSupermarket" placeholder="e.g. LIDL, ESSELUNGA" required>
                </div>
                <div class="input-group">
                    <label for="uploadStoreId">Store ID / City</label>
                    <input type="text" id="uploadStoreId" placeholder="e.g. d-cesena" required>
                </div>
                <div class="input-group">
                    <label for="uploadEngine">Parsing Engine</label>
                    <select id="uploadEngine">
                        <option value="AUTO">Auto-Detect (Offline OCR / Vector Grid)</option>
                        <option value="TESSERACT">Offline Tesseract OCR (Scanned Fallback)</option>
                        <option value="GEMINI">Gemini 2.5 Flash API (Structured Visual)</option>
                        <option value="CLAUDE">Claude Haiku 4.5 API (Structured Visual)</option>
                    </select>
                </div>
                <div>
                    <button class="btn" type="submit" style="width: 100%; height: 42px; display: flex; justify-content: center; align-items: center; gap: 8px;">
                        <span>Parse & Scrape Flyer</span>
                    </button>
                </div>
            </form>
            
            <!-- Loading and Status Message -->
            <div id="uploadStatus" style="display: none; margin-top: 15px; padding: 12px; border-radius: 8px; font-weight: 500; text-align: center; line-height: 1.5;">
                <!-- Filled dynamically -->
            </div>
        </div>
    </section>

    <!-- Statistics Section -->
    <section class="stats-panel-card">
        <div style="cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none;" onclick="toggleStatsPanel()">
            <h2 style="margin: 0; font-size: 1.1rem; font-weight: 600; display: flex; align-items: center; gap: 10px;">
                <span>📊</span> Statistiche e Report Volantini
            </h2>
            <span id="statsToggleIcon" style="font-size: 0.85rem; color: var(--text-secondary); transition: var(--transition-smooth);">[ Collapse ▲ ]</span>
        </div>
        
        <div id="statsPanelContent" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 30px; margin-top: 20px; animation: fadeIn 0.2s ease-out;">
            <!-- Left Panel: Global Stats List -->
            <div>
                <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 0.95rem; color: #ffffff; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">
                    📈 Statistiche Globali
                </h3>
                <ul class="stats-list" style="list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px;">
                    <li style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 8px;">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">Totale Offerte Database</span>
                        <strong id="statGlobalTotal" style="font-size: 1.1rem; color: #ffffff;">0</strong>
                    </li>
                    <li style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 8px;">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">Prezzo Medio Promo</span>
                        <strong id="statGlobalAvgPrice" style="font-size: 1.1rem; color: var(--accent-blue);">€ 0.00</strong>
                    </li>
                    <li style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 8px;">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">Sconto Massimo Rilevato</span>
                        <strong id="statGlobalMaxDiscount" style="font-size: 1.1rem; color: var(--accent-red);">0%</strong>
                    </li>
                    <li style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed rgba(255,255,255,0.05); padding-bottom: 8px;">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">Immagini Ritagliate (Coverage)</span>
                        <strong id="statGlobalImageCoverage" style="font-size: 1rem; color: var(--accent-green);">0 / 0 (0%)</strong>
                    </li>
                    <li style="display: flex; justify-content: space-between; align-items: center; padding-bottom: 4px;">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">Tipologia Promo Frequente</span>
                        <strong id="statGlobalTopPromoType" style="font-size: 0.95rem; color: var(--accent-purple);">STANDARD</strong>
                    </li>
                </ul>
            </div>
            
            <!-- Right Panel: Supermarket Stats Table -->
            <div>
                <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 0.95rem; color: #ffffff; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">
                    🏪 Statistiche per Insegna
                </h3>
                <div style="overflow-x: auto; max-height: 220px; overflow-y: auto;">
                    <table class="stats-table">
                        <thead>
                            <tr style="color: var(--text-secondary);">
                                <th style="text-align: left;">Insegna</th>
                                <th style="text-align: center;">Offerte</th>
                                <th style="text-align: right;">P. Medio</th>
                                <th style="text-align: right;">Prezzi (Min-Max)</th>
                                <th style="text-align: center;">Sconto Max</th>
                                <th style="text-align: right;">Immagini (%)</th>
                            </tr>
                        </thead>
                        <tbody id="statsTableBody">
                            <!-- Filled dynamically in JS -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </section>

    <!-- Filters Panel -->
    <section class="control-panel">
        <div class="filters-grid">
            <div class="input-group">
                <label for="searchInput">Search offers</label>
                <input type="text" id="searchInput" placeholder="Search by product name, brand or EAN..." oninput="handleFilterChange()">
            </div>
            
            <div class="input-group">
                <label for="supermarketFilter">Supermarket</label>
                <select id="supermarketFilter" onchange="handleFilterChange()">
                    <option value="ALL">All Supermarkets</option>
                    <option value="COOP">Coop</option>
                    <option value="CONAD">Conad</option>
                    <option value="INS">IN's Mercato</option>
                    <option value="DPIU">Dpiù Discount</option>
                </select>
            </div>

            <div class="input-group">
                <label for="promoFilter">Promo Type</label>
                <select id="promoFilter" onchange="handleFilterChange()">
                    <option value="ALL">All Types</option>
                    <option value="STANDARD">Standard Promo</option>
                    <option value="1+1">1+1 (BOGO)</option>
                    <option value="PERCENTAGE_DISCOUNT">Percentage Discount</option>
                    <option value="PREZZO_SOCIO">Coop Members</option>
                    <option value="DISCOUNT">Simple Discount</option>
                </select>
            </div>

            <!-- Column Selection dropdown -->
            <div class="input-group column-selector">
                <label>Show Columns</label>
                <button class="dropdown-btn" onclick="toggleDropdown(event)">
                    <span>Toggle Columns</span>
                    <span>▼</span>
                </button>
                <div class="dropdown-content" id="columnDropdown" onclick="event.stopPropagation()">
                    <label><input type="checkbox" checked data-col="supermarket" onchange="toggleColumnVisibility(this)"> Supermarket</label>
                    <label><input type="checkbox" checked data-col="preview" onchange="toggleColumnVisibility(this)"> Visual Preview</label>
                    <label><input type="checkbox" checked data-col="store_id" onchange="toggleColumnVisibility(this)"> Store ID</label>
                    <label><input type="checkbox" checked data-col="name" onchange="toggleColumnVisibility(this)"> Product Name</label>
                    <label><input type="checkbox" checked data-col="brand" onchange="toggleColumnVisibility(this)"> Brand</label>
                    <label><input type="checkbox" checked data-col="weight" onchange="toggleColumnVisibility(this)"> Weight/Volume</label>
                    <label><input type="checkbox" checked data-col="price" onchange="toggleColumnVisibility(this)"> Price</label>
                    <label><input type="checkbox" checked data-col="ean" onchange="toggleColumnVisibility(this)"> EAN Barcode</label>
                    <label><input type="checkbox" checked data-col="promo_type" onchange="toggleColumnVisibility(this)"> Promo Type</label>
                    <label><input type="checkbox" checked data-col="validity" onchange="toggleColumnVisibility(this)"> Validity</label>
                    <label><input type="checkbox" checked data-col="extracted" onchange="toggleColumnVisibility(this)"> Extracted At</label>
                </div>
            </div>
        </div>
    </section>
 
    <!-- Table Card -->
    <main class="table-card">
        <div class="table-responsive">
            <table id="offersTable">
                <thead>
                    <tr>
                        <th data-col="supermarket" onclick="sortTable('supermarket')">Supermarket</th>
                        <th data-col="preview" class="text-center">Preview</th>
                        <th data-col="store_id" onclick="sortTable('store_id')">Store ID</th>
                        <th data-col="name" onclick="sortTable('name')">Product Description</th>
                        <th data-col="brand" onclick="sortTable('brand')">Brand</th>
                        <th data-col="weight" onclick="sortTable('weight_or_volume')">Weight/Vol</th>
                        <th data-col="price" onclick="sortTable('price')">Price / Discount</th>
                        <th data-col="ean" onclick="sortTable('ean_code')">EAN Barcode</th>
                        <th data-col="promo_type" onclick="sortTable('promo_type')">Promo Type</th>
                        <th data-col="validity" onclick="sortTable('validity_string')">Validity</th>
                        <th data-col="extracted" onclick="sortTable('extracted_at')">Extracted At</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
                    <!-- Dynamic Rows Insertion -->
                </tbody>
            </table>
            
            <div id="errorState" class="error-container" style="display: none;"></div>
            <div id="emptyState" class="empty-container" style="display: none;">No promotional offers found matching the filters.</div>
        </div>

        <!-- Pagination Footer -->
        <footer class="footer-pagination">
            <div class="pagination-info" id="paginationInfo">Showing 0 to 0 of 0 offers</div>
            <div class="pagination-btns">
                <button class="btn" id="btnPrev" onclick="changePage(-1)" disabled>Previous</button>
                <button class="btn" id="btnNext" onclick="changePage(1)" disabled>Next</button>
            </div>
        </footer>
    </main>

    <script>
        // Global App State
        let allOffers = [];
        let filteredOffers = [];
        let currentPage = 1;
        const itemsPerPage = 15;
        let sortField = 'extracted_at';
        let sortAsc = false;

        // Dynamic case-insensitive Supermarket badge generator with deterministic color fallback
        function getSupermarketBadge(supermarket) {
            if (!supermarket) return `<span class="badge badge-manual">MANUAL</span>`;
            
            const upperName = supermarket.toUpperCase().trim();
            let badgeClass = 'badge-manual';
            let displayName = supermarket.toUpperCase().trim();
            
            if (upperName === 'COOP') {
                badgeClass = 'badge-coop';
                displayName = 'COOP';
            } else if (upperName === 'CONAD') {
                badgeClass = 'badge-conad';
                displayName = 'CONAD';
            } else if (upperName === 'INS' || upperName === "IN'S") {
                badgeClass = 'badge-ins';
                displayName = "IN'S";
            } else if (upperName === 'DPIU' || upperName === 'DPIÙ') {
                badgeClass = 'badge-dpiu';
                displayName = 'DPIÙ';
            } else {
                // Determine a unique hash color deterministically from the supermarket name
                let hash = 0;
                for (let i = 0; i < upperName.length; i++) {
                    hash = upperName.charCodeAt(i) + ((hash << 5) - hash);
                }
                const hue = Math.abs(hash % 360);
                
                // Return dynamic glassmorphic badge styled inline
                return `<span class="badge" style="background-color: hsla(${hue}, 70%, 50%, 0.12); color: hsl(${hue}, 85%, 65%); border: 1px solid hsla(${hue}, 70%, 50%, 0.25); text-transform: uppercase;">${displayName}</span>`;
            }
            
            return `<span class="badge ${badgeClass}">${displayName}</span>`;
        }

        // Document Event Listeners
        document.addEventListener('click', () => {
            document.getElementById('columnDropdown').style.display = 'none';
        });

        function toggleDropdown(event) {
            event.stopPropagation();
            const content = document.getElementById('columnDropdown');
            content.style.display = content.style.display === 'block' ? 'none' : 'block';
        }

        // Fetch Data from SQLite REST API Backend
        async function fetchData() {
            const errorDiv = document.getElementById('errorState');
            const emptyDiv = document.getElementById('emptyState');
            const tableBody = document.getElementById('tableBody');
            
            errorDiv.style.display = 'none';
            emptyDiv.style.display = 'none';
            tableBody.innerHTML = '<tr><td colspan="10" style="text-align: center; padding: 40px; color: var(--text-secondary);">⌛ Fetching active records from database...</td></tr>';
            
            try {
                const response = await fetch('/api/offers');
                if (!response.ok) {
                    throw new Error(`HTTP Error: ${response.status}`);
                }
                const data = await response.json();
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                allOffers = data;
                filteredOffers = [...allOffers];
                
                populateSupermarketFilterOptions();
                calculateKPIs();
                applyFilterAndRender();
                
            } catch (err) {
                console.error("Fetch failed: ", err);
                tableBody.innerHTML = '';
                errorDiv.style.display = 'block';
                errorDiv.innerHTML = `⚠️ Failed to query SQLite database. Make sure main.py has been run and storage/promotions.db exists.<br><small>${err.message}</small>`;
            }
        }

        // Dynamically populates the supermarket filter dropdown based on active DB records
        function populateSupermarketFilterOptions() {
            const select = document.getElementById('supermarketFilter');
            if (!select) return;
            const currentValue = select.value;
            
            const uniqueMarketsSet = new Set(allOffers.map(o => o.supermarket));
            const uniqueMarkets = Array.from(uniqueMarketsSet).sort();
            
            select.innerHTML = '<option value="ALL">All Supermarkets</option>';
            
            uniqueMarkets.forEach(market => {
                let displayName = market;
                if (market === 'COOP') displayName = 'Coop';
                else if (market === 'CONAD') displayName = 'Conad';
                else if (market === 'INS') displayName = "IN's Mercato";
                else if (market === 'DPIU') displayName = 'Dpiù Discount';
                
                const opt = document.createElement('option');
                opt.value = market;
                opt.textContent = displayName;
                select.appendChild(opt);
            });
            
            // Restore selection state
            if (Array.from(select.options).some(opt => opt.value === currentValue)) {
                select.value = currentValue;
            } else {
                select.value = 'ALL';
            }
        }

        function toggleStatsPanel() {
            const content = document.getElementById('statsPanelContent');
            const icon = document.getElementById('statsToggleIcon');
            if (content.style.display === 'none') {
                content.style.display = 'grid';
                icon.textContent = '[ Collapse ▲ ]';
            } else {
                content.style.display = 'none';
                icon.textContent = '[ Expand ▼ ]';
            }
        }

        // Calculates top level KPI metrics from active dataset
        function calculateKPIs() {
            const total = allOffers.length;
            
            // 1. Calculate Global stats
            let avgPrice = 0;
            let maxDiscount = 0;
            let imagesCount = 0;
            const promoTypeCounts = {};
            
            allOffers.forEach(o => {
                // Price avg
                avgPrice += o.price;
                // Max discount
                if (o.discount_percentage && o.discount_percentage > maxDiscount) {
                    maxDiscount = o.discount_percentage;
                }
                // Image coverage
                if (o.image_url && o.image_url.trim().length > 0) {
                    imagesCount++;
                }
                // Promo types
                const pType = o.promo_type || 'STANDARD';
                promoTypeCounts[pType] = (promoTypeCounts[pType] || 0) + 1;
            });
            
            if (total > 0) {
                avgPrice = avgPrice / total;
            }
            
            // Find top promo type
            let topPromoType = 'N/D';
            let maxTypeCount = 0;
            for (const [type, count] of Object.entries(promoTypeCounts)) {
                if (count > maxTypeCount) {
                    maxTypeCount = count;
                    topPromoType = type;
                }
            }
            
            // Map promo type human readable labels
            const promoLabels = {
                'STANDARD': 'STANDARD (Prezzo Tag)',
                '1+1': '1+1 (Prendi 2 paghi 1)',
                'PERCENTAGE_DISCOUNT': 'Sconto Percentuale',
                'PREZZO_SOCIO': 'Prezzo Soci',
                'DISCOUNT': 'Sconto Semplice'
            };
            const topPromoLabel = promoLabels[topPromoType] || topPromoType;
            
            // Update global stats DOM
            document.getElementById('statGlobalTotal').textContent = total;
            document.getElementById('statGlobalAvgPrice').textContent = `€ ${avgPrice.toFixed(2)}`;
            document.getElementById('statGlobalMaxDiscount').textContent = `${maxDiscount}%`;
            
            const imgPercent = total > 0 ? ((imagesCount / total) * 100).toFixed(1) : 0;
            document.getElementById('statGlobalImageCoverage').textContent = `${imagesCount} / ${total} (${imgPercent}%)`;
            document.getElementById('statGlobalTopPromoType').textContent = topPromoLabel;
            
            // 2. Calculate Per-Supermarket stats
            const uniqueMarketsSet = new Set(allOffers.map(o => o.supermarket));
            const uniqueMarkets = Array.from(uniqueMarketsSet).sort();
            
            const statsTableBody = document.getElementById('statsTableBody');
            statsTableBody.innerHTML = '';
            
            if (uniqueMarkets.length === 0) {
                statsTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 15px;">Nessun dato disponibile nel database</td></tr>`;
                return;
            }
            
            uniqueMarkets.forEach(market => {
                const mOffers = allOffers.filter(o => o.supermarket === market);
                const mTotal = mOffers.length;
                
                let mAvgPrice = 0;
                let mMinPrice = Infinity;
                let mMaxPrice = -Infinity;
                let mMaxDiscount = 0;
                let mImagesCount = 0;
                
                mOffers.forEach(o => {
                    mAvgPrice += o.price;
                    if (o.price < mMinPrice) mMinPrice = o.price;
                    if (o.price > mMaxPrice) mMaxPrice = o.price;
                    if (o.discount_percentage && o.discount_percentage > mMaxDiscount) {
                        mMaxDiscount = o.discount_percentage;
                    }
                    if (o.image_url && o.image_url.trim().length > 0) {
                        mImagesCount++;
                    }
                });
                
                if (mTotal > 0) {
                    mAvgPrice = mAvgPrice / mTotal;
                } else {
                    mMinPrice = 0;
                    mMaxPrice = 0;
                }
                
                const mImgPercent = mTotal > 0 ? ((mImagesCount / mTotal) * 100).toFixed(1) : 0;
                
                const superBadgeHtml = getSupermarketBadge(market);
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="padding: 12px 8px; vertical-align: middle;">
                        ${superBadgeHtml}
                    </td>
                    <td style="padding: 12px 8px; text-align: center; font-weight: bold; color: #ffffff;">${mTotal}</td>
                    <td style="padding: 12px 8px; text-align: right; color: var(--accent-blue); font-weight: 500;">€ ${mAvgPrice.toFixed(2)}</td>
                    <td style="padding: 12px 8px; text-align: right; color: var(--text-secondary); font-size: 0.85rem;">
                        € ${mMinPrice.toFixed(2)} - € ${mMaxPrice.toFixed(2)}
                    </td>
                    <td style="padding: 12px 8px; text-align: center; color: var(--accent-red); font-weight: 600;">${mMaxDiscount}%</td>
                    <td style="padding: 12px 8px; text-align: right; color: var(--accent-green); font-size: 0.85rem;">
                        ${mImagesCount} <small style="color: var(--text-secondary);">(${mImgPercent}%)</small>
                    </td>
                `;
                statsTableBody.appendChild(tr);
            });
        }

        // Handles search field or dropdown filters changes
        function handleFilterChange() {
            const search = document.getElementById('searchInput').value.toLowerCase().trim();
            const supermarket = document.getElementById('supermarketFilter').value;
            const promo = document.getElementById('promoFilter').value;
            
            filteredOffers = allOffers.filter(offer => {
                // Search filter (Name, Brand or EAN code)
                const nameMatch = offer.name ? offer.name.toLowerCase().includes(search) : false;
                const brandMatch = offer.brand ? offer.brand.toLowerCase().includes(search) : false;
                const eanMatch = offer.ean_code ? offer.ean_code.toLowerCase().includes(search) : false;
                
                const matchesSearch = !search || nameMatch || brandMatch || eanMatch;
                
                // Supermarket filter
                const matchesSupermarket = supermarket === 'ALL' || offer.supermarket === supermarket;
                
                // Promo type filter
                const matchesPromo = promo === 'ALL' || offer.promo_type === promo;
                
                return matchesSearch && matchesSupermarket && matchesPromo;
            });
            
            currentPage = 1;
            applySort();
            renderTable();
        }

        // Handles sorting
        function sortTable(field) {
            if (sortField === field) {
                sortAsc = !sortAsc;
            } else {
                sortField = field;
                sortAsc = true;
            }
            applySort();
            renderTable();
        }

        function applySort() {
            filteredOffers.sort((a, b) => {
                let valA = a[sortField];
                let valB = b[sortField];
                
                if (valA === null || valA === undefined) valA = '';
                if (valB === null || valB === undefined) valB = '';
                
                if (typeof valA === 'string') {
                    return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                } else {
                    return sortAsc ? valA - valB : valB - valA;
                }
            });
        }

        // Render rows dynamically into table
        function renderTable() {
            const tableBody = document.getElementById('tableBody');
            const emptyDiv = document.getElementById('emptyState');
            tableBody.innerHTML = '';
            
            if (filteredOffers.length === 0) {
                emptyDiv.style.display = 'block';
                document.getElementById('paginationInfo').textContent = "Showing 0 to 0 of 0 offers";
                document.getElementById('btnPrev').disabled = true;
                document.getElementById('btnNext').disabled = true;
                return;
            }
            
            emptyDiv.style.display = 'none';
            
            // Paginate slices
            const startIdx = (currentPage - 1) * itemsPerPage;
            const endIdx = Math.min(startIdx + itemsPerPage, filteredOffers.length);
            const pageSlice = filteredOffers.slice(startIdx, endIdx);
            
            pageSlice.forEach(offer => {
                const tr = document.createElement('tr');
                
                // Supermarket Badge
                const superBadge = getSupermarketBadge(offer.supermarket);
                    
                // Visual Preview Card Crop
                let previewHtml = `<span style="color: var(--text-secondary); font-size: 0.8rem;">-</span>`;
                if (offer.image_url) {
                    previewHtml = `
                        <div class="thumb-container">
                            <img src="${offer.image_url}" class="table-thumb" alt="Crop">
                            <div class="thumb-zoom">
                                <img src="${offer.image_url}" alt="Zoom">
                            </div>
                        </div>
                    `;
                }
                    
                // Price formatting (include discount percentage or crossed original price)
                let priceHtml = `<span class="price-text">€ ${offer.price.toFixed(2)}</span>`;
                if (offer.original_price && offer.original_price > offer.price) {
                    priceHtml += `<span class="price-strikethrough">€ ${offer.original_price.toFixed(2)}</span>`;
                }
                if (offer.discount_percentage) {
                    priceHtml += `<span class="discount-badge">-${offer.discount_percentage}%</span>`;
                }
                if (offer.price_per_unit) {
                    priceHtml += `<br><small style="color: var(--text-secondary); font-size: 0.75rem;">${offer.price_per_unit}</small>`;
                }
                
                // Formatted extracted_at
                let dateStr = 'N/A';
                if (offer.extracted_at) {
                    dateStr = offer.extracted_at.replace('T', ' ').split('.')[0];
                }
                
                // Render cells
                tr.innerHTML = `
                    <td data-col="supermarket">${superBadge}</td>
                    <td data-col="preview" class="text-center">${previewHtml}</td>
                    <td data-col="store_id" style="font-family: monospace; font-size: 0.8rem;">${offer.store_id || 'N/A'}</td>
                    <td data-col="name" title="${offer.name}" style="font-weight: 500;">${offer.name || 'UNKNOWN'}</td>
                    <td data-col="brand">${offer.brand || '<span style="color: var(--text-secondary); font-size: 0.8rem;">-</span>'}</td>
                    <td data-col="weight" style="color: var(--text-secondary);">${offer.weight_or_volume || '-'}</td>
                    <td data-col="price">${priceHtml}</td>
                    <td data-col="ean" style="font-family: monospace; font-size: 0.8rem; color: var(--text-secondary);">${offer.ean_code || '-'}</td>
                    <td data-col="promo_type"><span class="badge badge-promo">${offer.promo_type.replace('_', ' ')}</span></td>
                    <td data-col="validity" style="color: var(--text-secondary); font-size: 0.8rem;" title="${offer.validity_string || ''}">${offer.validity_string || '-'}</td>
                    <td data-col="extracted" style="color: var(--text-secondary); font-size: 0.75rem;">${dateStr}</td>
                `;
                
                tableBody.appendChild(tr);
            });
            
            // Sync column visibilities immediately for new elements
            syncColumnVisibilities();
            
            // Pagination controls update
            document.getElementById('paginationInfo').textContent = `Showing ${startIdx + 1} to ${endIdx} of ${filteredOffers.length} offers`;
            document.getElementById('btnPrev').disabled = (currentPage === 1);
            document.getElementById('btnNext').disabled = (endIdx >= filteredOffers.length);
        }

        // Pagination Handler
        function changePage(direction) {
            currentPage += direction;
            renderTable();
        }

        // Toggle visibility of columns dynamically
        function toggleColumnVisibility(checkbox) {
            const col = checkbox.getAttribute('data-col');
            const show = checkbox.checked;
            
            // Find all cells (header and body) matching this column
            const cells = document.querySelectorAll(`[data-col="${col}"]`);
            cells.forEach(c => {
                c.style.display = show ? '' : 'none';
            });
        }

        function syncColumnVisibilities() {
            const checkboxes = document.querySelectorAll('#columnDropdown input[type="checkbox"]');
            checkboxes.forEach(cb => {
                const col = cb.getAttribute('data-col');
                const cells = document.querySelectorAll(`[data-col="${col}"]`);
                cells.forEach(c => {
                    c.style.display = cb.checked ? '' : 'none';
                });
            });
        }

        function applyFilterAndRender() {
            applySort();
            renderTable();
        }

        function toggleUploadPanel() {
            const content = document.getElementById('uploadPanelContent');
            const icon = document.getElementById('uploadToggleIcon');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                icon.textContent = '[ Collapse Form ▲ ]';
            } else {
                content.style.display = 'none';
                icon.textContent = '[ Expand Upload Form ▼ ]';
            }
        }

        async function handleManualUpload(event) {
            event.preventDefault();
            
            const fileInput = document.getElementById('pdfFile');
            const supermarketInput = document.getElementById('uploadSupermarket');
            const storeIdInput = document.getElementById('uploadStoreId');
            const engineInput = document.getElementById('uploadEngine');
            const statusDiv = document.getElementById('uploadStatus');
            
            if (fileInput.files.length === 0) {
                alert("Please select a valid PDF file.");
                return;
            }
            
            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append("file", file);
            formData.append("supermarket", supermarketInput.value);
            formData.append("store_id", storeIdInput.value);
            formData.append("engine", engineInput.value);
            formData.append("use_gemini", engineInput.value === "GEMINI" ? "true" : "false");
            formData.append("use_claude", engineInput.value === "CLAUDE" ? "true" : "false");
            
            statusDiv.style.display = 'block';
            statusDiv.style.backgroundColor = 'rgba(59, 130, 246, 0.15)';
            statusDiv.style.color = '#60a5fa';
            statusDiv.style.border = '1px solid rgba(59, 130, 246, 0.3)';
            statusDiv.innerHTML = `⌛ <strong>Scraping in progress...</strong> Analyzing PDF pages, extracting vector text, running OCR fallbacks, cropping images, and saving offers. Please wait (this can take a few seconds)...`;
            
            const elements = event.target.elements;
            for (let i = 0; i < elements.length; i++) {
                elements[i].disabled = true;
            }
            
            try {
                const res = await fetch("/api/upload", {
                    method: "POST",
                    body: formData
                });
                
                const data = await res.json();
                
                if (data.success) {
                    statusDiv.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
                    statusDiv.style.color = '#34d399';
                    statusDiv.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                    statusDiv.innerHTML = `✅ <strong>Success!</strong> ${data.message}<br>Extracted <strong>${data.offers_count}</strong> promotional offers and upserted them successfully to the database.`;
                    
                    event.target.reset();
                    fetchData();
                } else {
                    throw new Error(data.error || "Unknown parser error.");
                }
            } catch (err) {
                statusDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
                statusDiv.style.color = '#f87171';
                statusDiv.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                statusDiv.innerHTML = `❌ <strong>Parsing Failed:</strong> ${err.message}`;
            } finally {
                for (let i = 0; i < elements.length; i++) {
                    elements[i].disabled = false;
                }
            }
        }

        // Initialize App on load
        window.addEventListener('DOMContentLoaded', () => {
            fetchData();
        });
    </script>
</body>
</html>
"""

class DashboardHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP Request Handler serving both the static Dashboard Single-Page HTML Code
    and the SQLite DB query REST endpoint `/api/offers`.
    """

    def do_GET(self) -> None:
        # Route: API Endpoint to retrieve promotions from SQLite
        if self.path == "/api/offers":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            response_data = []
            
            if not os.path.exists(DB_PATH):
                response_data = {"error": "Database not initialized. Please run main.py first."}
                self.wfile.write(json.dumps(response_data).encode("utf-8"))
                return
                
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                # Enable dictionary key lookup
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        supermarket, store_id, offer_id, name, brand, weight_or_volume,
                        price, original_price, discount_percentage, price_per_unit,
                        ean_code, image_url, category, promo_type, validity_string, extracted_at
                    FROM promotions 
                    ORDER BY extracted_at DESC, supermarket ASC, name ASC;
                """)
                
                rows = cursor.fetchall()
                response_data = [dict(row) for row in rows]
                
            except sqlite3.Error as e:
                response_data = {"error": f"SQLite database query error: {e}"}
            finally:
                if 'conn' in locals():
                    conn.close()
                    
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            
        # Route: Serve static product card cropped images and standard images from local storage
        elif self.path.startswith("/storage/"):
            import urllib.parse
            decoded_path = urllib.parse.unquote(self.path)
            file_rel_path = decoded_path.lstrip("/")
            
            storage_dir_abs = os.path.abspath("storage")
            requested_path_abs = os.path.abspath(file_rel_path)
            
            if (requested_path_abs == storage_dir_abs or requested_path_abs.startswith(storage_dir_abs + os.sep)) and os.path.exists(requested_path_abs) and os.path.isfile(requested_path_abs):
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

        # Route: Serve the visual dashboard dashboard HTML
        elif self.path in ("/", "/index.html", "/dashboard"):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
            
        else:
            # Fallback 404 for other unmapped static routes
            self.send_response(404)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self) -> None:
        # Route: Manual PDF circular flyer upload & parse endpoint
        if self.path == "/api/upload":
            content_type = self.headers.get("Content-Type")
            if not content_type or "multipart/form-data" not in content_type:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Content-Type must be multipart/form-data"}).encode("utf-8"))
                return
                
            try:
                # Read content length
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                
                # Parse body using email BytesParser
                msg = BytesParser().parsebytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
                
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
                            engine = part.get_payload(decode=True).decode().strip().upper()
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
                    self.wfile.write(json.dumps({"error": "No PDF file upload content discovered in payload"}).encode("utf-8"))
                    return
                    
                # Save the manual PDF file
                os.makedirs("downloads/uploaded", exist_ok=True)
                clean_filename = "".join(c for c in pdf_filename if c.isalnum() or c in (".", "_", "-")).strip()
                if not clean_filename:
                    clean_filename = "manual_flyer.pdf"
                if not clean_filename.endswith(".pdf"):
                    clean_filename += ".pdf"
                    
                file_path = os.path.join("downloads/uploaded", clean_filename)
                with open(file_path, "wb") as f:
                    f.write(pdf_content)
                    
                print(f"[UploadAPI] Saved uploaded flyer: {clean_filename} | Target Supermarket: {supermarket} | Store: {store_id} | Engine: {engine}")
                
                # Check for a .env file and load environment variables manually
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

                # Instantiate Manual Scraper Driver
                from drivers.manual.manual_driver import ManualSupermarketDriver
                from storage.database import save_offers
                
                driver = ManualSupermarketDriver(
                    supermarket_name=supermarket,
                    store_id=store_id,
                    engine=engine
                )
                
                # Run ETL pipeline directly on the uploaded PDF file
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
                        "saved_count": saved_count
                    }
                    self.wfile.write(json.dumps(response).encode("utf-8"))
                else:
                    self.send_response(400)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": "No promotional offers could be parsed from the PDF circular. Make sure the file format matches standard layouts."
                    }).encode("utf-8"))
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Scraper visual execution failed: {e}"
                }).encode("utf-8"))

def run_server() -> None:
    """Runs the visual verifier server."""
    # Ensure standard socket port reuse so restarting the server is instant
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    
    # Initialize database schema dynamically at startup
    from storage.database import initialize_db
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
