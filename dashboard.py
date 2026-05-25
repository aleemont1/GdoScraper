import http.server
import socketserver
import sqlite3
import json
import os
import sys
from typing import Dict, Any, List

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

        /* KPI / Stats Row */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .kpi-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 22px;
            backdrop-filter: var(--glass-blur);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: var(--transition-smooth);
            position: relative;
            overflow: hidden;
        }

        .kpi-card:hover {
            transform: translateY(-4px);
            border-color: rgba(139, 92, 246, 0.3);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.2);
        }

        .kpi-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-size: 2.2rem;
            font-weight: 700;
            margin: 10px 0 5px 0;
        }

        .kpi-footer {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .kpi-total .kpi-value { color: #ffffff; }
        .kpi-coop .kpi-value { color: var(--accent-green); }
        .kpi-conad .kpi-value { color: var(--accent-orange); }
        .kpi-ins .kpi-value { color: var(--accent-purple); }
        .kpi-dpiu .kpi-value { color: var(--accent-red); }
        .kpi-avg .kpi-value { color: var(--accent-blue); }

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

    <!-- KPI / Stats Row -->
    <section class="stats-grid">
        <div class="kpi-card kpi-total">
            <span class="kpi-label">Total Offers</span>
            <span class="kpi-value" id="kpiTotal">0</span>
            <span class="kpi-footer">Extracted in SQLite promotions table</span>
        </div>
        <div class="kpi-card kpi-coop">
            <span class="kpi-label">Coop Offers</span>
            <span class="kpi-value" id="kpiCoop">0</span>
            <span class="kpi-footer">From REST API integrations</span>
        </div>
        <div class="kpi-card kpi-conad">
            <span class="kpi-label">Conad Offers</span>
            <span class="kpi-value" id="kpiConad">0</span>
            <span class="kpi-footer">From Column-First grid segments</span>
        </div>
        <div class="kpi-card kpi-ins">
            <span class="kpi-label">IN's Offers</span>
            <span class="kpi-value" id="kpiIns">0</span>
            <span class="kpi-footer">From Crawler & Dual-Engine OCR</span>
        </div>
        <div class="kpi-card kpi-dpiu">
            <span class="kpi-label">Dpiù Offers</span>
            <span class="kpi-value" id="kpiDpiu">0</span>
            <span class="kpi-footer">From REST API integrations</span>
        </div>
        <div class="kpi-card kpi-avg">
            <span class="kpi-label">Avg Promo Price</span>
            <span class="kpi-value" id="kpiAvg">€ 0.00</span>
            <span class="kpi-footer">Calculated across active database items</span>
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
                
                calculateKPIs();
                applyFilterAndRender();
                
            } catch (err) {
                console.error("Fetch failed: ", err);
                tableBody.innerHTML = '';
                errorDiv.style.display = 'block';
                errorDiv.innerHTML = `⚠️ Failed to query SQLite database. Make sure main.py has been run and storage/promotions.db exists.<br><small>${err.message}</small>`;
            }
        }

        // Calculates top level KPI metrics from active dataset
        function calculateKPIs() {
            const total = allOffers.length;
            const coopCount = allOffers.filter(o => o.supermarket === 'COOP').length;
            const conadCount = allOffers.filter(o => o.supermarket === 'CONAD').length;
            const insCount = allOffers.filter(o => o.supermarket === 'INS').length;
            const dpiuCount = allOffers.filter(o => o.supermarket === 'DPIU').length;
            
            // Calculate average price of promos
            let avgPrice = 0;
            if (total > 0) {
                const sum = allOffers.reduce((acc, o) => acc + o.price, 0);
                avgPrice = sum / total;
            }
            
            document.getElementById('kpiTotal').textContent = total;
            document.getElementById('kpiCoop').textContent = coopCount;
            document.getElementById('kpiConad').textContent = conadCount;
            document.getElementById('kpiIns').textContent = insCount;
            document.getElementById('kpiDpiu').textContent = dpiuCount;
            document.getElementById('kpiAvg').textContent = `€ ${avgPrice.toFixed(2)}`;
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
                const superBadge = offer.supermarket === 'COOP' 
                    ? `<span class="badge badge-coop">Coop</span>` 
                    : offer.supermarket === 'CONAD'
                    ? `<span class="badge badge-conad">Conad</span>`
                    : offer.supermarket === 'INS'
                    ? `<span class="badge badge-ins">IN's</span>`
                    : `<span class="badge badge-dpiu">Dpiù</span>`;
                    
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
                conn = sqlite3.connect(DB_PATH)
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
            
        # Route: Serve static product card cropped images from the local storage
        elif self.path.startswith("/storage/images/"):
            file_rel_path = self.path.lstrip("/")
            if os.path.exists(file_rel_path) and os.path.isfile(file_rel_path):
                self.send_response(200)
                if file_rel_path.endswith(".png"):
                    self.send_header("Content-type", "image/png")
                elif file_rel_path.endswith((".jpg", ".jpeg")):
                    self.send_header("Content-type", "image/jpeg")
                else:
                    self.send_header("Content-type", "application/octet-stream")
                self.end_headers()
                
                with open(file_rel_path, "rb") as f:
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

def run_server() -> None:
    """Runs the visual verifier server."""
    # Ensure standard socket port reuse so restarting the server is instant
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), DashboardHTTPHandler) as httpd:
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
