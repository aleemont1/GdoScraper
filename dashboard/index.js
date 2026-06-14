/* GDO Supermarket Scraper - Premium SPA Controller */

// Global App State
let allOffers = [];
let filteredOffers = [];
let currentPage = 1;
const itemsPerPage = 15;
let currentSupermarket = 'coop'; // Default wizard supermarket
let selectedStoreId = null;
let selectedFlyerIds = [];
let activeTaskId = null;
let logPollInterval = null;
let manualFile = null;
let editingOfferKey = null; // Format: "supermarket|store_id|offer_id"
let newProductImageFile = null;
let newProductImagePreviewUrl = null;
let currentLanguage = 'it'; // Default language is Italian
let currentSortField = null;
let currentSortOrder = 'asc';

// Localization Translation Dictionary
const translations = {
    it: {
        title: "Controllo Offerte Supermercati",
        app_title: "Offerte GDO",
        app_subtitle: "Gestione Volantini e Offerte",
        tab_audit: "Registro Promozioni",
        tab_extract: "Estrai Offerte",
        filter_supermarket_label: "Supermercato",
        opt_all_nodes: "Tutti i negozi",
        opt_manual_uploads: "Inseriti manualmente",
        search_input_label: "Cerca",
        search_input_placeholder: "Cerca nome prodotto, brand o codice a barre...",
        btn_db_stats: "Statistiche",
        btn_refresh_registers: "Aggiorna Registro",
        btn_reset_sort: "Ripristina Ordine",
        verification_engine_label: "MOTORE DI VERIFICA: ATTIVO",
        th_chain: "Catena",
        th_store_id: "ID Negozio",
        th_product: "Prodotto",
        th_brand: "Brand",
        th_weight: "Peso",
        th_retail_price: "Prezzo di Vendita",
        th_ean: "Codice EAN",
        th_extracted: "Data Estrazione",
        th_actions: "Azioni",
        table_initializing: "Inizializzazione del registro delle promozioni...",
        etl_config_title: "Impostazioni di Ricerca",
        etl_config_subtitle: "Scegli dove e come cercare le offerte promozionali",
        target_supermarket_label: "01 / Scegli il Supermercato",
        rest_api_engine: "Motore API REST",
        vector_core_parser: "Parser Vettoriale",
        ocr_grid_fallback: "Fallback Griglia OCR",
        rest_api_client: "Client API REST",
        local_document: "Documento Locale",
        geo_coordinates_label: "02 / Posizione del Negozio",
        geo_coordinates_helper: "Inserisci città, coordinate GPS o codice negozio.",
        geo_placeholder: "es. Cesena",
        btn_discover_stores: "Trova Negozi",
        discovered_stores_label: "Negozi Rilevati nel raggio:",
        active_catalogs_label: "Volantini Attivi rilevati:",
        upload_pdf_label: "02 / Carica Documento Volantino PDF",
        drag_drop_label: "Trascina qui il file PDF del volantino",
        browse_files_label: "o clicca per sfogliare i file locali",
        no_file_selected: "Nessun file selezionato",
        custom_supermarket_tag: "Tag Supermercato Personalizzato",
        custom_store_code: "Codice Negozio Personalizzato",
        advanced_options_label: "Opzioni",
        search_radius_label: "Raggio di ricerca (km)",
        target_db_path_label: "Percorso Database Target",
        parallel_execution_label: "Esecuzione Parallela",
        extraction_engine_label: "Motore di Estrazione",
        opt_engine_auto: "Rilevamento Automatico Griglia / OCR",
        opt_engine_tesseract: "Tesseract OCR Offline",
        opt_engine_gemini: "API Multimodale Gemini",
        opt_engine_claude: "API Claude Haiku",
        btn_start_extraction: "Avvia Estrazione Dati",
        pipeline_monitor_title: "Stato dell'operazione",
        pipeline_monitor_subtitle: "Dettagli e messaggi dell'attività in corso",
        db_analytics_title: "Aggregati & Analitiche Database",
        stat_total_promos: "Totale Promozioni",
        stat_total_nodes: "Supermercati",
        stats_breakdown_title: "Statistiche per Supermercato",
        stats_th_supermarket: "Supermercato",
        stats_th_store_id: "ID Negozio",
        stats_th_total_offers: "Offerte Totali",
        stats_th_min_price: "Prezzo Min",
        stats_th_max_price: "Prezzo Max",
        stats_gathering: "Raccolta degli aggregati del database...",
        confirm_action_title: "Conferma Azione",
        btn_cancel: "Annulla",
        btn_confirm: "Conferma",
        
        // Dynamic messaging
        showing_records: "Mostrati {count} record",
        msg_confirm_save: "Sei sicuro di voler salvare queste modifiche nel database?",
        msg_confirm_delete: "Sei sicuro di voler eliminare definitivamente questa offerta?",
        msg_name_required: "Il nome del prodotto è obbligatorio.",
        msg_price_required: "Il prezzo del prodotto è obbligatorio.",
        msg_price_number: "Il prezzo del prodotto deve essere un numero valido.",
        msg_orig_price_number: "Il prezzo originale deve essere un numero valido o vuoto.",
        msg_discount_number: "La percentuale di sconto deve essere un numero valido o vuoto.",
        msg_valid_image: "Seleziona un file immagine valido (PNG, JPG, JPEG o WEBP).",
        msg_upload_failed: "Caricamento dell'immagine fallito: {error}",
        msg_save_failed: "Salvataggio delle modifiche fallito: {error}",
        msg_delete_failed: "Eliminazione dell'offerta fallita: {error}",
        msg_loading_promotions: "Caricamento delle promozioni dal database...",
        msg_no_promotions: "🔍 Nessun record di promozione attivo trovato. Prova a cambiare i filtri o estrarre nuovi volantini.",
        msg_load_failed: "⚠️ Impossibile caricare i dati. Assicurati che storage/promotions.db esista.<br><small>{error}</small>",
        msg_store_discover_failed: "Impossibile trovare i negozi: {error}",
        msg_flyer_discover_failed: "Impossibile trovare i volantini: {error}",
        msg_discover_stores_btn: "Trova Negozi",
        msg_discovering_stores_btn: "Ricerca in corso...",
        msg_upload_manual_btn: "Avvia caricamento PDF e parsing",
        msg_start_extract_btn: "Avvia Estrazione Dati",
        msg_upload_pdf_success: "Volantino PDF manuale analizzato con successo!",
        msg_upload_pdf_persisted: "Estratte e salvate {count} offerte.",
        msg_upload_pdf_failed: "Errore Pipeline ETL: {error}",
        msg_spawn_etl_success: "Sottoprocesso avviato. ID Sessione Task: {id}",
        msg_spawn_etl_failed: "Avvio fallito: {error}",
        msg_etl_finished_success: "Estrazione Completata! Inserite le offerte promozionali con successo nel database SQLite.",
        msg_etl_finished_failed: "Estrazione Fallita. Il sottoprocesso è terminato con un codice di uscita diverso da zero. Controlla i log stdout sopra.",
        msg_no_store_data: "Nessun dato del negozio disponibile.",
        msg_stats_failed: "Impossibile recuperare le statistiche: {error}",
        msg_no_stores_found: "Nessun negozio fisico trovato nel raggio di ricerca. Prova ad aumentare il raggio o la query di coordinate.",
        msg_fetching_flyers: "Recupero dei volantini attivi per il negozio...",
        msg_no_flyers_found: "Nessun volantino attivo trovato. Lo scraper scaricherà l'elenco predefinito se avviato.",
        msg_spawning_scraper: "Avvio del programma di scaricamento delle offerte...",
        msg_uploading_manual_flyer: "Caricamento volantino manuale: {name}...",
        msg_parse_finished_title: "Analisi Completata!",
        msg_extraction_failed_title: "Estrazione Fallita",
        msg_initiating_live_scraping: "Avvio dello scaricamento offerte per {chain} (Codice Negozio: {id})...",
        msg_extraction_completed_title: "Estrazione Completata",
        msg_empty_stores_list: "Inserisci una città o coordinate per trovare i supermercati."
    },
    en: {
        title: "Supermarket Promotion Auditor",
        app_title: "GDO Promotions",
        app_subtitle: "Flyer & Promotion Manager",
        tab_audit: "Promotions Register",
        tab_extract: "Extract Offers",
        filter_supermarket_label: "Supermarket",
        opt_all_nodes: "All stores",
        opt_manual_uploads: "Manual Uploads",
        search_input_label: "Search",
        search_input_placeholder: "Type product name, brand, or barcode...",
        btn_db_stats: "Stats",
        btn_refresh_registers: "Refresh Registers",
        btn_reset_sort: "Reset Order",
        verification_engine_label: "VERIFICATION ENGINE: ACTIVE",
        th_chain: "Chain",
        th_store_id: "Store ID",
        th_product: "Product",
        th_brand: "Brand",
        th_weight: "Weight",
        th_retail_price: "Retail Price",
        th_ean: "EAN Barcode",
        th_extracted: "Extracted timestamp",
        th_actions: "Actions",
        table_initializing: "Initializing promotions datatable registers...",
        etl_config_title: "Search Settings",
        etl_config_subtitle: "Choose where and how to search for promotions",
        target_supermarket_label: "01 / Choose Supermarket",
        rest_api_engine: "REST API Engine",
        vector_core_parser: "Vector Core Parser",
        ocr_grid_fallback: "OCR Grid Fallback",
        rest_api_client: "REST API Client",
        local_document: "Local Document",
        geo_coordinates_label: "02 / Store Location",
        geo_coordinates_helper: "Enter town name, GPS coordinates, or store code.",
        geo_placeholder: "e.g., Cesena",
        btn_discover_stores: "Discover Stores",
        discovered_stores_label: "Discovered Stores in bounds:",
        active_catalogs_label: "Active Catalogs detected:",
        upload_pdf_label: "02 / Upload Circular PDF Document",
        drag_drop_label: "Drag & Drop Flyer PDF here",
        browse_files_label: "or click to browse local files",
        no_file_selected: "No file selected",
        custom_supermarket_tag: "Custom Supermarket Tag",
        custom_store_code: "Custom Store Code",
        advanced_options_label: "Options",
        search_radius_label: "Search Radius (km)",
        target_db_path_label: "Target Database path",
        parallel_execution_label: "Parallel execution",
        extraction_engine_label: "Extraction Engine",
        opt_engine_auto: "Auto-detect Grid / OCR",
        opt_engine_tesseract: "Offline Tesseract OCR",
        opt_engine_gemini: "Gemini Multimodal API",
        opt_engine_claude: "Claude Haiku API",
        btn_start_extraction: "Start Data Extraction",
        pipeline_monitor_title: "Operation status",
        pipeline_monitor_subtitle: "Activity details and messages",
        db_analytics_title: "Database Aggregates & Analytics",
        stat_total_promos: "Total Promos",
        stat_total_nodes: "Supermarkets",
        stats_breakdown_title: "Statistics by Supermarket",
        stats_th_supermarket: "Supermarket",
        stats_th_store_id: "Store ID",
        stats_th_total_offers: "Total Offers",
        stats_th_min_price: "Min Price",
        stats_th_max_price: "Max Price",
        stats_gathering: "Gathering database aggregates...",
        confirm_action_title: "Confirm Action",
        btn_cancel: "Cancel",
        btn_confirm: "Confirm",
        
        // Dynamic messaging
        showing_records: "Showing {count} records",
        msg_confirm_save: "Are you sure you want to save these changes to the database?",
        msg_confirm_delete: "Are you sure you want to permanently delete this offer?",
        msg_name_required: "Product name is required.",
        msg_price_required: "Product price is required.",
        msg_price_number: "Product price must be a valid number.",
        msg_orig_price_number: "Original price must be a valid number or empty.",
        msg_discount_number: "Discount percentage must be a valid number or empty.",
        msg_valid_image: "Please select a valid image file (PNG, JPG, JPEG, or WEBP).",
        msg_upload_failed: "Failed to upload image: {error}",
        msg_save_failed: "Failed to save changes: {error}",
        msg_delete_failed: "Failed to delete offer: {error}",
        msg_loading_promotions: "Loading promotions from database...",
        msg_no_promotions: "🔍 No active promotion records found. Try changing filters or scraping new flyers.",
        msg_load_failed: "⚠️ Failed to load data. Make sure storage/promotions.db exists.<br><small>{error}</small>",
        msg_store_discover_failed: "Failed to discover stores: {error}",
        msg_flyer_discover_failed: "Failed to retrieve flyers: {error}",
        msg_discover_stores_btn: "Discover Stores",
        msg_discovering_stores_btn: "Discovering...",
        msg_upload_manual_btn: "Start Flyer PDF Upload & Parse",
        msg_start_extract_btn: "Start Data Extraction",
        msg_upload_pdf_success: "Manual PDF parsed successfully!",
        msg_upload_pdf_persisted: "Successfully extracted {count} promotions.",
        msg_upload_pdf_failed: "ETL Pipeline Error: {error}",
        msg_spawn_etl_success: "Subprocess spawned. Task Session ID: {id}",
        msg_spawn_etl_failed: "Failed to execute: {error}",
        msg_etl_finished_success: "Extraction Completed! Upserted promotional offers successfully to SQLite db.",
        msg_etl_finished_failed: "Extraction Failed. Subprocess completed with non-zero exit code. Please review stdout logs above.",
        msg_no_store_data: "No store data available.",
        msg_stats_failed: "Failed to retrieve stats: {error}",
        msg_no_stores_found: "No physical stores found in search radius. Try increasing the radius or coordinates query.",
        msg_fetching_flyers: "Fetching active flyer catalogs for store...",
        msg_no_flyers_found: "No active flyers found. Scraper will download default listings if run.",
        msg_spawning_scraper: "Starting the promotion download program...",
        msg_uploading_manual_flyer: "Uploading manual flyer: {name}...",
        msg_parse_finished_title: "Parse Finished!",
        msg_extraction_failed_title: "Extraction Failed",
        msg_initiating_live_scraping: "Starting promotion download for {chain} (Store Code: {id})...",
        msg_extraction_completed_title: "Extraction Completed",
        msg_empty_stores_list: "Enter a city or coordinates to find supermarkets."
    }
};

// Translate function with dynamic variable substitution
function t(key, variables = {}) {
    const lang = currentLanguage || 'it';
    let text = translations[lang][key] || translations['en'][key] || key;
    for (const [varName, varValue] of Object.entries(variables)) {
        text = text.replace(new RegExp(`\\{${varName}\\}`, 'g'), varValue);
    }
    return text;
}

// Apply current translations to all DOM elements with translation keys
function applyTranslations() {
    // 1. Text elements
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        el.textContent = t(key);
    });

    // 2. Placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.dataset.i18nPlaceholder;
        el.placeholder = t(key);
    });

    // 3. Document Title
    document.title = t('title');

    // 4. Update language indicator label in header toggle
    const langIcon = document.getElementById('lang-icon');
    if (langIcon) {
        langIcon.textContent = currentLanguage.toUpperCase();
    }
}

// Toggle active language state
function toggleLanguage() {
    currentLanguage = currentLanguage === 'it' ? 'en' : 'it';
    localStorage.setItem('lang', currentLanguage);
    applyTranslations();
    applyFilters(); // Re-render the grid dynamically using correct language terms
}

// Initialize SPA App on DOM Load
document.addEventListener('DOMContentLoaded', () => {
    // Load persisted language or default to 'it'
    currentLanguage = localStorage.getItem('lang') || 'it';
    applyTranslations();

    // Load initial database promotions
    loadOffers();
    
    // Set theme from localStorage or default to dark
    const savedTheme = localStorage.getItem('theme') || 'dark';
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
        document.getElementById('theme-icon').textContent = '☼';
    } else {
        document.body.classList.remove('dark-mode');
        document.getElementById('theme-icon').textContent = '☾';
    }

    // Set default wizard panels visibility
    selectSupermarket('coop');
    
    // Bind mouse move logic for image preview zoom card
    setupImageZoomer();
});

/* Router & Navigation */
function switchTab(tabName) {
    const tabAudit = document.getElementById('tab-audit');
    const tabExtract = document.getElementById('tab-extract');
    const viewAudit = document.getElementById('view-audit');
    const viewExtract = document.getElementById('view-extract');

    if (tabName === 'audit') {
        tabAudit.classList.add('active');
        tabExtract.classList.remove('active');
        viewAudit.classList.add('active');
        viewExtract.classList.remove('active');
        // Refresh table whenever we navigate back to audit
        loadOffers();
    } else if (tabName === 'extract') {
        tabExtract.classList.add('active');
        tabAudit.classList.remove('active');
        viewExtract.classList.add('active');
        viewAudit.classList.remove('active');
    }
}

/* Light / Dark Theme Mode Toggle */
function toggleTheme() {
    const isDark = document.body.classList.toggle('dark-mode');
    document.getElementById('theme-icon').textContent = isDark ? '☼' : '☾';
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

/* Page 1: Promotions Auditing Logic */
async function loadOffers() {
    const tableBody = document.getElementById('table-body');
    tableBody.innerHTML = `<tr><td colspan="9" class="table-empty">${t('msg_loading_promotions')}</td></tr>`;
    
    try {
        const res = await fetch('/api/offers');
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        
        allOffers = data;
        filteredOffers = [...allOffers];
        
        currentPage = 1;
        applyFilters();
    } catch (err) {
        console.error("Failed to load offers:", err);
        tableBody.innerHTML = `<tr><td colspan="9" class="table-empty">${t('msg_load_failed', {error: err.message})}</td></tr>`;
    }
}

function applyFilters() {
    const supermarketFilter = document.getElementById('filter-supermarket').value;
    const searchInput = document.getElementById('search-input').value.toLowerCase().trim();
    
    filteredOffers = allOffers.filter(offer => {
        // Supermarket chain filter
        const matchesSupermarket = (supermarketFilter === 'ALL') || 
            (offer.supermarket && offer.supermarket.toUpperCase() === supermarketFilter.toUpperCase());
            
        // Search text filter
        const nameMatch = offer.name ? offer.name.toLowerCase().includes(searchInput) : false;
        const brandMatch = offer.brand ? offer.brand.toLowerCase().includes(searchInput) : false;
        const categoryMatch = offer.category ? offer.category.toLowerCase().includes(searchInput) : false;
        const eanMatch = offer.ean_code ? offer.ean_code.toLowerCase().includes(searchInput) : false;
        
        const matchesSearch = !searchInput || nameMatch || brandMatch || categoryMatch || eanMatch;
        
        return matchesSupermarket && matchesSearch;
    });
    
    if (currentSortField) {
        applySorting();
    }
    
    currentPage = 1;
    renderTable();
}

function applySorting() {
    if (!currentSortField) return;
    
    filteredOffers.sort((a, b) => {
        let valA = a[currentSortField];
        let valB = b[currentSortField];
        
        if (valA === undefined || valA === null) valA = '';
        if (valB === undefined || valB === null) valB = '';
        
        if (typeof valA === 'string') valA = valA.toLowerCase().trim();
        if (typeof valB === 'string') valB = valB.toLowerCase().trim();
        
        if (currentSortField === 'price' || currentSortField === 'original_price' || currentSortField === 'discount_percentage') {
            const numA = parseFloat(valA) || 0;
            const numB = parseFloat(valB) || 0;
            return (currentSortOrder === 'asc') ? numA - numB : numB - numA;
        }
        
        if (valA < valB) return (currentSortOrder === 'asc') ? -1 : 1;
        if (valA > valB) return (currentSortOrder === 'asc') ? 1 : -1;
        return 0;
    });
}

function sortBy(field) {
    if (currentSortField === field) {
        currentSortOrder = (currentSortOrder === 'asc') ? 'desc' : 'asc';
    } else {
        currentSortField = field;
        currentSortOrder = 'asc';
    }
    
    const resetBtn = document.getElementById('btn-reset-sort');
    if (resetBtn) resetBtn.classList.remove('hidden');
    
    document.querySelectorAll('.sortable-header').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    const targetHeader = document.querySelector(`th[onclick="sortBy('${field}')"]`);
    if (targetHeader) {
        targetHeader.classList.add(currentSortOrder === 'asc' ? 'sorted-asc' : 'sorted-desc');
    }
    
    applySorting();
    currentPage = 1;
    renderTable();
}

function resetSort() {
    currentSortField = null;
    currentSortOrder = 'asc';
    
    const resetBtn = document.getElementById('btn-reset-sort');
    if (resetBtn) resetBtn.classList.add('hidden');
    
    document.querySelectorAll('.sortable-header').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    applyFilters();
}

function renderTable() {
    const tableBody = document.getElementById('table-body');
    const recordCount = document.getElementById('record-count');
    tableBody.innerHTML = '';
    
    if (filteredOffers.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="9" class="table-empty">${t('msg_no_promotions')}</td></tr>`;
        recordCount.textContent = t('showing_records', {count: 0});
        return;
    }
    
    recordCount.textContent = t('showing_records', {count: filteredOffers.length});
    
    // Pagination slicing
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, filteredOffers.length);
    const pageSlice = filteredOffers.slice(startIndex, endIndex);
    
    pageSlice.forEach(offer => {
        const tr = document.createElement('tr');
        
        // Supermarket Chain Badge
        const badge = getSupermarketBadge(offer.supermarket);
        
        // Thumbnail handling
        let previewHtml = '<span style="color: var(--text-tertiary);">-</span>';
        if (offer.image_url) {
            previewHtml = `
                <div class="thumb-container">
                    <img src="${offer.image_url}" class="table-thumb" alt="Product Image" 
                         onmouseenter="showZoomer(event, '${offer.image_url}', '${escapeHtml(offer.name)}', '€ ${offer.price.toFixed(2)}')" 
                         onmouseleave="hideZoomer()">
                </div>
            `;
        }
        
        // Price format
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
        
        // Date format
        let dateStr = '-';
        if (offer.extracted_at) {
            dateStr = offer.extracted_at.replace('T', ' ').split('.')[0];
        }

        const isEditing = (editingOfferKey === `${offer.supermarket}|${offer.store_id}|${offer.offer_id}`);
        
        if (isEditing) {
            let editPreviewHtml = '';
            const currentImageUrl = newProductImagePreviewUrl || offer.image_url;
            if (currentImageUrl) {
                editPreviewHtml = `
                    <div class="thumb-container editing" onclick="triggerProductImageUpload()" title="Click to replace product image">
                        <img id="edit-thumb-img" src="${currentImageUrl}" class="table-thumb editing-thumb" alt="Product Image">
                        <div class="thumb-overlay">✎</div>
                    </div>
                `;
            } else {
                editPreviewHtml = `
                    <div class="thumb-container editing empty" onclick="triggerProductImageUpload()" title="Click to add product image">
                        <div id="edit-thumb-img-placeholder" class="empty-thumb">＋</div>
                        <div class="thumb-overlay">✎</div>
                    </div>
                `;
            }

            tr.innerHTML = `
                <td>${badge}</td>
                <td class="text-center">${offer.store_id || 'N/A'}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        ${editPreviewHtml}
                        <input type="text" id="edit-name" class="edit-input" value="${escapeHtml(offer.name || '')}" style="font-weight: 600;">
                    </div>
                </td>
                <td><input type="text" id="edit-brand" class="edit-input" value="${escapeHtml(offer.brand || '')}"></td>
                <td><input type="text" id="edit-weight" class="edit-input" value="${escapeHtml(offer.weight_or_volume || '')}"></td>
                <td>
                    <div style="display: flex; flex-direction: column; gap: 4px;">
                        <input type="number" step="0.01" id="edit-price" class="edit-input number-input" value="${offer.price}" placeholder="Price">
                        <input type="number" step="0.01" id="edit-original-price" class="edit-input number-input" value="${offer.original_price || ''}" placeholder="Orig.">
                        <input type="number" min="0" max="100" id="edit-discount" class="edit-input number-input" value="${offer.discount_percentage || ''}" placeholder="Disc. %">
                    </div>
                </td>
                <td><input type="text" id="edit-ean" class="edit-input" value="${escapeHtml(offer.ean_code || '')}" style="font-family: monospace;"></td>
                <td style="font-size: 0.8rem; color: var(--text-secondary);">${dateStr}</td>
                <td style="text-align: center;">
                    <div style="display: flex; justify-content: center; gap: 6px;">
                        <button class="btn btn-primary btn-action-sm" onclick="saveEdit('${offer.supermarket}', '${offer.store_id}', '${offer.offer_id}')" title="Confirm">✓</button>
                        <button class="btn btn-secondary btn-action-sm" onclick="cancelEdit()" title="Cancel">✕</button>
                    </div>
                </td>
            `;
        } else {
            tr.innerHTML = `
                <td>${badge}</td>
                <td class="text-center">${offer.store_id || 'N/A'}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        ${previewHtml}
                        <div style="font-weight: 600;">${offer.name || 'Unknown Item'}</div>
                    </div>
                </td>
                <td>${offer.brand || '-'}</td>
                <td>${offer.weight_or_volume || '-'}</td>
                <td>${priceHtml}</td>
                <td style="font-family: monospace; font-size: 0.85rem;">${offer.ean_code || '-'}</td>
                <td style="font-size: 0.8rem; color: var(--text-secondary);">${dateStr}</td>
                <td style="text-align: center;">
                    <div style="display: flex; justify-content: center; gap: 6px;">
                        <button class="btn btn-secondary btn-action-sm" onclick="startEdit('${offer.supermarket}', '${offer.store_id}', '${offer.offer_id}')" title="Edit">✎</button>
                        <button class="btn btn-danger btn-action-sm" onclick="deleteOffer('${offer.supermarket}', '${offer.store_id}', '${offer.offer_id}')" title="Delete">🗑</button>
                    </div>
                </td>
            `;
        }
        
        tableBody.appendChild(tr);
    });
    
    // Add pagination nav controls at the bottom of the table card
    renderPaginationControls();
}

function renderPaginationControls() {
    const totalPages = Math.ceil(filteredOffers.length / itemsPerPage);
    if (totalPages <= 1) return;
    
    const tableCard = document.querySelector('.table-card');
    let paginationDiv = document.getElementById('table-pagination');
    if (!paginationDiv) {
        paginationDiv = document.createElement('div');
        paginationDiv.id = 'table-pagination';
        paginationDiv.style.display = 'flex';
        paginationDiv.style.justifyContent = 'center';
        paginationDiv.style.alignItems = 'center';
        paginationDiv.style.gap = '15px';
        paginationDiv.style.marginTop = '20px';
        tableCard.appendChild(paginationDiv);
    }
    
    const prevText = currentLanguage === 'it' ? '◀ Precedente' : '◀ Previous';
    const nextText = currentLanguage === 'it' ? 'Successivo ▶' : 'Next ▶';
    const pageOfText = currentLanguage === 'it' ? `Pagina ${currentPage} di ${totalPages}` : `Page ${currentPage} of ${totalPages}`;

    paginationDiv.innerHTML = `
        <button class="btn btn-secondary" id="btn-prev-page" ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(-1)">${prevText}</button>
        <span style="font-weight: 600; font-size: 0.9rem;">${pageOfText}</span>
        <button class="btn btn-secondary" id="btn-next-page" ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(1)">${nextText}</button>
    `;
}

function changePage(offset) {
    currentPage += offset;
    renderTable();
}

function getSupermarketBadge(supermarket) {
    if (!supermarket) return '<span class="badge badge-manual">MANUAL</span>';
    const s = supermarket.toUpperCase().trim();
    if (s === 'COOP') return '<span class="badge badge-coop">COOP</span>';
    if (s === 'CONAD') return '<span class="badge badge-conad">CONAD</span>';
    if (s === 'INS' || s === "IN'S") return `<span class="badge badge-ins">IN'S</span>`;
    if (s === 'DPIU' || s === 'DPIÙ') return '<span class="badge badge-dpiu">DPIÙ</span>';
    return `<span class="badge badge-manual">${s}</span>`;
}

/* Floating Image Zoomer Controller */
function setupImageZoomer() {
    const zoomer = document.getElementById('image-zoomer');
    document.addEventListener('mousemove', (e) => {
        if (!zoomedActive) return;
        
        // Position modal offset from mouse pointer
        const offset = 15;
        let x = e.clientX + offset;
        let y = e.clientY + offset;
        
        // Prevent layout overflow viewport
        const width = zoomer.offsetWidth;
        const height = zoomer.offsetHeight;
        if (x + width > window.innerWidth) {
            x = e.clientX - width - offset;
        }
        if (y + height > window.innerHeight) {
            y = e.clientY - height - offset;
        }
        
        zoomer.style.left = `${x + window.scrollX}px`;
        zoomer.style.top = `${y + window.scrollY}px`;
    });
}

let zoomedActive = false;
function showZoomer(event, src, name, price) {
    const zoomer = document.getElementById('image-zoomer');
    const img = document.getElementById('zoomer-img');
    const nameEl = document.getElementById('zoomer-name');
    const priceEl = document.getElementById('zoomer-price');
    
    img.src = src;
    nameEl.textContent = name;
    priceEl.textContent = price;
    zoomer.classList.remove('hidden');
    zoomedActive = true;
}

function hideZoomer() {
    const zoomer = document.getElementById('image-zoomer');
    zoomer.classList.add('hidden');
    zoomedActive = false;
}

/* Statistics modal triggers */
async function showStatsModal() {
    const modal = document.getElementById('stats-modal');
    modal.classList.remove('hidden');
    
    const totalOffersEl = document.getElementById('stat-total-offers');
    const totalSupermarketsEl = document.getElementById('stat-total-supermarkets');
    const statsTableBody = document.getElementById('modal-stats-table-body');
    
    statsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center;">${t('stats_gathering')}</td></tr>`;
    
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        const data = await res.json();
        
        totalOffersEl.textContent = data.total_offers || 0;
        totalSupermarketsEl.textContent = data.total_chains || 0;
        
        statsTableBody.innerHTML = '';
        if (!data.breakdown || data.breakdown.length === 0) {
            statsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center;">${t('msg_no_store_data')}</td></tr>`;
            return;
        }
        
        data.breakdown.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${getSupermarketBadge(row.supermarket)}</td>
                <td style="font-family: monospace;">${row.store_id}</td>
                <td class="text-center" style="font-weight: 700;">${row.total_offers}</td>
                <td class="text-right" style="color: var(--accent-green);">€ ${row.min_price.toFixed(2)}</td>
                <td class="text-right" style="color: var(--accent-red);">€ ${row.max_price.toFixed(2)}</td>
            `;
            statsTableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Stats query failed:", err);
        statsTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--accent-red);">${t('msg_stats_failed', {error: err.message})}</td></tr>`;
    }
}

function closeStatsModal(event) {
    const modal = document.getElementById('stats-modal');
    modal.classList.add('hidden');
}

/* Page 2: Data Extraction Wizard Logic */
function selectSupermarket(chain) {
    currentSupermarket = chain;
    
    // Manage active state classes
    ['coop', 'conad', 'ins', 'dpiu', 'manual'].forEach(c => {
        const card = document.getElementById(`sm-${c}`);
        if (c === chain) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });
    
    // Toggle manual vs automatic sections
    const targetStoreSection = document.getElementById('target-store-section');
    const manualUploadSection = document.getElementById('manual-upload-section');
    const parallelWrapper = document.getElementById('parallel-wrapper');
    const engineWrapper = document.getElementById('engine-wrapper');
    
    // Reset lists
    selectedStoreId = null;
    selectedFlyerIds = [];
    document.getElementById('discovered-stores-card').classList.add('hidden');
    document.getElementById('discovered-flyers-card').classList.add('hidden');
    
    if (chain === 'manual') {
        targetStoreSection.classList.add('hidden');
        manualUploadSection.classList.remove('hidden');
        parallelWrapper.classList.remove('hidden');
        engineWrapper.classList.remove('hidden');
        document.getElementById('btn-trigger-scrape').textContent = t('msg_upload_manual_btn');
    } else {
        targetStoreSection.classList.remove('hidden');
        manualUploadSection.classList.add('hidden');
        document.getElementById('btn-trigger-scrape').textContent = t('msg_start_extract_btn');
        
        // Hide options based on supermarket capabilities
        if (chain === 'coop') {
            parallelWrapper.classList.add('hidden'); // Coop doesn't need parallel parsing (API based)
            engineWrapper.classList.add('hidden');     // Coop uses direct REST API
            document.getElementById('store-target-input').value = 'Cesena';
        } else if (chain === 'conad') {
            parallelWrapper.classList.remove('hidden'); // Conad downloads PDF flyers, parallel parsing is useful
            engineWrapper.classList.add('hidden');      // Conad uses offline raster extractor (PDF parsing)
            document.getElementById('store-target-input').value = '44.1396,12.2464';
        } else if (chain === 'ins') {
            parallelWrapper.classList.remove('hidden');
            engineWrapper.classList.remove('hidden');   // IN's uses OCR, lets you configure engine
            document.getElementById('store-target-input').value = 'Cesena';
        } else if (chain === 'dpiu') {
            parallelWrapper.classList.add('hidden');    // Dpiù uses direct REST API
            engineWrapper.classList.add('hidden');
            document.getElementById('store-target-input').value = 'Cesena';
        }
    }
}

// Geocode location / direct store locator query
async function searchStores() {
    const query = document.getElementById('store-target-input').value.trim();
    const radius = document.getElementById('radius-input').value;
    const btn = document.getElementById('btn-search-stores');
    
    if (!query) {
        showAlert("Please enter a city name, direct store code or coordinates (lat,lon)", "warning");
        return;
    }
    
    btn.disabled = true;
    btn.textContent = t('msg_discovering_stores_btn');
    
    const storeSelectionList = document.getElementById('stores-selection-list');
    const discoveredStoresCard = document.getElementById('discovered-stores-card');
    const discoveredFlyersCard = document.getElementById('discovered-flyers-card');
    
    storeSelectionList.innerHTML = '';
    discoveredStoresCard.classList.add('hidden');
    discoveredFlyersCard.classList.add('hidden');
    selectedStoreId = null;
    selectedFlyerIds = [];
    
    try {
        const url = `/api/search-stores?supermarket=${currentSupermarket}&q=${encodeURIComponent(query)}&radius=${radius}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const stores = await res.json();
        
        if (stores.error) {
            throw new Error(stores.error);
        }
        
        if (stores.length === 0) {
            storeSelectionList.innerHTML = `<div style="padding: 10px; color: var(--text-secondary);">${t('msg_no_stores_found')}</div>`;
            discoveredStoresCard.classList.remove('hidden');
            return;
        }
        
        stores.forEach((store, index) => {
            const item = document.createElement('div');
            item.className = 'store-select-item';
            item.dataset.storeId = store.id;
            item.dataset.itemIndex = index;
            item.onclick = () => selectStoreItem(store.id, index);
            
            const nameSpan = document.createElement('div');
            nameSpan.innerHTML = `<span class="item-name">${escapeHtml(store.name)}</span><br><span class="item-address">${escapeHtml(store.address || store.city || '')}</span>`;
            
            const distSpan = document.createElement('span');
            distSpan.className = 'item-distance';
            distSpan.textContent = store.distance ? `${store.distance.toFixed(1)} km` : `Code: ${store.id}`;
            
            item.appendChild(nameSpan);
            item.appendChild(distSpan);
            storeSelectionList.appendChild(item);
        });
        
        discoveredStoresCard.classList.remove('hidden');
        
        // Auto-select the first store in the list for better UX
        if (stores.length > 0) {
            selectStoreItem(stores[0].id, 0);
        }
        
    } catch (err) {
        console.error("Store discovery failed:", err);
        showAlert(t('msg_store_discover_failed', {error: err.message}), "error");
    } finally {
        btn.disabled = false;
        btn.textContent = t('msg_discover_stores_btn');
    }
}
 
// Highlights selected store and fetches its flyer catalogs
async function selectStoreItem(storeId, itemIndex) {
    selectedStoreId = storeId;
    selectedFlyerIds = [];
    
    // Update highlights based on unique item list index
    const items = document.querySelectorAll('.store-select-item');
    items.forEach(it => {
        if (parseInt(it.dataset.itemIndex) === itemIndex) {
            it.classList.add('selected');
        } else {
            it.classList.remove('selected');
        }
    });
    
    // Fetch flyers for this store
    const flyersSelectionList = document.getElementById('flyers-selection-list');
    const discoveredFlyersCard = document.getElementById('discovered-flyers-card');
    
    flyersSelectionList.innerHTML = `<div style="padding: 10px; color: var(--text-secondary);">${t('msg_fetching_flyers')}</div>`;
    discoveredFlyersCard.classList.remove('hidden');
    
    try {
        const url = `/api/get-flyers?supermarket=${currentSupermarket}&store_id=${encodeURIComponent(storeId)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const flyers = await res.json();
        
        if (flyers.error) {
            throw new Error(flyers.error);
        }
        
        flyersSelectionList.innerHTML = '';
        if (flyers.length === 0) {
            flyersSelectionList.innerHTML = `<div style="padding: 10px; color: var(--text-secondary);">${t('msg_no_flyers_found')}</div>`;
            return;
        }
        
        flyers.forEach(flyer => {
            const item = document.createElement('div');
            item.className = 'flyer-select-item';
            
            const label = document.createElement('label');
            
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = flyer.id;
            cb.checked = true; // Selected by default
            cb.onchange = () => toggleFlyerSelection(flyer.id, cb.checked);
            
            // Add to selected list initially
            selectedFlyerIds.push(flyer.id);
            
            const titleSpan = document.createElement('span');
            titleSpan.innerHTML = `<span class="item-name">${escapeHtml(flyer.title)}</span><br><span class="item-validity">${escapeHtml(flyer.validity || '')}</span>`;
            
            label.appendChild(cb);
            label.appendChild(titleSpan);
            item.appendChild(label);
            flyersSelectionList.appendChild(item);
        });
    } catch (err) {
        console.error("Failed to fetch flyers:", err);
        flyersSelectionList.innerHTML = `<div style="padding: 10px; color: var(--accent-red);">${t('msg_flyer_discover_failed', {error: err.message})}</div>`;
    }
}

function toggleFlyerSelection(flyerId, checked) {
    if (checked) {
        if (!selectedFlyerIds.includes(flyerId)) {
            selectedFlyerIds.push(flyerId);
        }
    } else {
        selectedFlyerIds = selectedFlyerIds.filter(id => id !== flyerId);
    }
}

/* Advanced Configuration Toggler */
let advancedOpen = false;
function toggleAdvancedSettings() {
    advancedOpen = !advancedOpen;
    const block = document.getElementById('advanced-settings-block');
    const icon = document.getElementById('advanced-toggle-icon');
    if (advancedOpen) {
        block.classList.remove('hidden');
        icon.textContent = '▼';
    } else {
        block.classList.add('hidden');
        icon.textContent = '▶';
    }
}

/* Drag & Drop Manual File Selector */
function triggerFileInput() {
    document.getElementById('manual-file-input').click();
}

function handleDragOver(e) {
    e.preventDefault();
    document.getElementById('dropzone').classList.add('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    const dropzone = document.getElementById('dropzone');
    dropzone.classList.remove('dragover');
    
    if (e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        if (file.type === 'application/pdf') {
            setManualFile(file);
        } else {
            showAlert("Only PDF flyers can be uploaded!", "error");
        }
    }
}

function handleFileSelect(e) {
    if (e.target.files.length > 0) {
        setManualFile(e.target.files[0]);
    }
}

function setManualFile(file) {
    manualFile = file;
    document.getElementById('file-name-label').textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    
    // Pre-fill supermarket and store labels from filename where possible
    const cleanName = file.name.toLowerCase();
    const supermarketInput = document.getElementById('manual-supermarket-name');
    if (cleanName.includes('coop')) supermarketInput.value = 'COOP';
    else if (cleanName.includes('conad')) supermarketInput.value = 'CONAD';
    else if (cleanName.includes('ins')) supermarketInput.value = "IN'S";
    else if (cleanName.includes('dpiu') || cleanName.includes('dpiù')) supermarketInput.value = 'DPIÙ';
}

/* Scrape Execution Orchestrator */
async function triggerScrapeExecution() {
    const consoleLogs = document.getElementById('console-logs');
    const executionResultCard = document.getElementById('execution-result-card');
    const btn = document.getElementById('btn-trigger-scrape');
    
    // Clear console logs & hide old results
    consoleLogs.innerHTML = `<p class="system-line">[SYSTEM] ${t('msg_spawning_scraper')}</p>`;
    executionResultCard.classList.add('hidden');
    
    // Validate inputs
    if (currentSupermarket === 'manual') {
        if (!manualFile) {
            showAlert("Please select or drop a flyer PDF file first!", "warning");
            return;
        }
        
        btn.disabled = true;
        
        // Manual uses multipart upload
        const formData = new FormData();
        formData.append("file", manualFile);
        formData.append("supermarket", document.getElementById('manual-supermarket-name').value.trim() || 'MANUAL');
        formData.append("store_id", document.getElementById('manual-store-id').value.trim() || 'MANUAL_STORE');
        formData.append("engine", document.getElementById('engine-input').value);
        formData.append("use_gemini", document.getElementById('engine-input').value === 'GEMINI' ? 'true' : 'false');
        formData.append("use_claude", document.getElementById('engine-input').value === 'CLAUDE' ? 'true' : 'false');
        
        appendLogLine('system', `${t('msg_uploading_manual_flyer', {name: manualFile.name})}`);
        
        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (data.success) {
                appendLogLine('success', t('msg_upload_pdf_success'));
                appendLogLine('success', t('msg_upload_pdf_persisted', {count: data.offers_count}));
                
                // Show result card
                showScrapeResult(true, t('msg_parse_finished_title'), t('msg_upload_pdf_persisted', {count: data.offers_count}));
                
                // Reset file select
                manualFile = null;
                document.getElementById('file-name-label').textContent = t('no_file_selected');
                
                // Refresh audit
                loadOffers();
            } else {
                throw new Error(data.error || "Manual parsing failed.");
            }
        } catch (err) {
            appendLogLine('error', t('msg_upload_pdf_failed', {error: err.message}));
            showScrapeResult(false, t('msg_extraction_failed_title'), err.message);
        } finally {
            btn.disabled = false;
        }
        
    } else {
        // Active API/PDF scraping
        if (!selectedStoreId) {
            showAlert("Please search and select a supermarket store location first!", "warning");
            return;
        }
        
        btn.disabled = true;
        
        const payload = {
            supermarket: currentSupermarket,
            store_id: selectedStoreId,
            flyer_ids: selectedFlyerIds,
            radius: parseInt(document.getElementById('radius-input').value) || 15,
            db_path: document.getElementById('db-path-input').value || 'storage/promotions.db',
            parallel: document.getElementById('parallel-input').checked,
            engine: document.getElementById('engine-input').value
        };
        
        appendLogLine('system', t('msg_initiating_live_scraping', {chain: currentSupermarket.toUpperCase(), id: selectedStoreId}));
        
        try {
            const res = await fetch('/api/scrape/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: jsonStringifyCompact(payload)
            });
            const data = await res.json();
            
            if (data.success) {
                activeTaskId = data.task_id;
                appendLogLine('system', t('msg_spawn_etl_success', {id: activeTaskId}));
                
                // Set up polling logs
                if (logPollInterval) clearInterval(logPollInterval);
                logPollInterval = setInterval(pollScraperLogs, 800);
            } else {
                throw new Error(data.error || "Failed to start scraping task.");
            }
        } catch (err) {
            appendLogLine('error', t('msg_spawn_etl_failed', {error: err.message}));
            showScrapeResult(false, t('msg_extraction_failed_title'), err.message);
            btn.disabled = false;
        }
    }
}

// Log line helper
function appendLogLine(type, text) {
    const consoleLogs = document.getElementById('console-logs');
    const line = document.createElement('p');
    
    if (type === 'system') line.className = 'system-line';
    else if (type === 'info') line.className = 'log-info';
    else if (type === 'warn') line.className = 'log-warn';
    else if (type === 'error') line.className = 'log-error';
    else if (type === 'success') line.className = 'log-success';
    
    // Add timestamps
    const now = new Date().toLocaleTimeString();
    line.textContent = `[${now}] ${text}`;
    
    consoleLogs.appendChild(line);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

// Polls active subprocess logs from server
async function pollScraperLogs() {
    if (!activeTaskId) return;
    
    try {
        const res = await fetch(`/api/scrape/logs?task_id=${activeTaskId}`);
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const data = await res.json();
        
        // Write raw logs to console
        const consoleLogs = document.getElementById('console-logs');
        consoleLogs.innerHTML = '';
        
        if (data.logs) {
            data.logs.split('\n').forEach(line => {
                if (!line.trim()) return;
                
                const p = document.createElement('p');
                if (line.includes(' - CRITICAL - ') || line.includes(' - ERROR - ')) {
                    p.className = 'log-error';
                } else if (line.includes(' - WARNING - ')) {
                    p.className = 'log-warn';
                } else if (line.includes(' - INFO - ')) {
                    p.className = 'log-info';
                } else if (line.includes('finished successfully') || line.includes('Successfully')) {
                    p.className = 'log-success';
                } else {
                    p.className = 'system-line';
                }
                p.textContent = line;
                consoleLogs.appendChild(p);
            });
            consoleLogs.scrollTop = consoleLogs.scrollHeight;
        }
        
        // Check task status
        if (data.status === 'completed') {
            clearInterval(logPollInterval);
            document.getElementById('btn-trigger-scrape').disabled = false;
            showScrapeResult(true, t('msg_extraction_completed_title'), t('msg_etl_finished_success'));
            loadOffers();
            activeTaskId = null;
        } else if (data.status === 'failed') {
            clearInterval(logPollInterval);
            document.getElementById('btn-trigger-scrape').disabled = false;
            showScrapeResult(false, t('msg_extraction_failed_title'), t('msg_etl_finished_failed'));
            activeTaskId = null;
        }
    } catch (err) {
        console.error("Error polling logs:", err);
        clearInterval(logPollInterval);
        document.getElementById('btn-trigger-scrape').disabled = false;
        activeTaskId = null;
    }
}

function showScrapeResult(success, title, desc) {
    const card = document.getElementById('execution-result-card');
    const badge = document.getElementById('result-badge');
    const titleEl = document.getElementById('result-title');
    const descEl = document.getElementById('result-description');
    
    badge.className = success ? 'result-badge success' : 'result-badge error';
    badge.textContent = success ? 'SUCCESS' : 'FAILED';
    titleEl.textContent = title;
    descEl.textContent = desc;
    
    card.classList.remove('hidden');
}

/* Utils */
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Compact JSON stringify to print lists elegantly
function jsonStringifyCompact(obj) {
    return JSON.stringify(obj);
}

// Start editing a specific offer
function startEdit(supermarket, storeId, offerId) {
    editingOfferKey = `${supermarket}|${storeId}|${offerId}`;
    newProductImageFile = null;
    newProductImagePreviewUrl = null;
    renderTable();
}

// Cancel current edit operation
function cancelEdit() {
    editingOfferKey = null;
    newProductImageFile = null;
    newProductImagePreviewUrl = null;
    renderTable();
}

// Save edited offer details to the backend
async function saveEdit(supermarket, storeId, offerId) {
    const nameInput = document.getElementById('edit-name');
    const brandInput = document.getElementById('edit-brand');
    const weightInput = document.getElementById('edit-weight');
    const priceInput = document.getElementById('edit-price');
    const originalPriceInput = document.getElementById('edit-original-price');
    const discountInput = document.getElementById('edit-discount');
    const eanInput = document.getElementById('edit-ean');

    if (!nameInput || !priceInput) {
        showAlert(t('msg_save_failed', {error: t('msg_name_required')}), "error");
        return;
    }

    const name = nameInput.value.trim();
    const brand = brandInput ? brandInput.value.trim() : "";
    const weight = weightInput ? weightInput.value.trim() : "";
    const priceStr = priceInput.value.trim();
    const originalPriceStr = originalPriceInput ? originalPriceInput.value.trim() : "";
    const discountStr = discountInput ? discountInput.value.trim() : "";
    const ean = eanInput ? eanInput.value.trim() : "";

    if (!name) {
        showAlert(t('msg_name_required'), "warning");
        return;
    }

    if (!priceStr) {
        showAlert(t('msg_price_required'), "warning");
        return;
    }

    const price = parseFloat(priceStr);
    if (isNaN(price)) {
        showAlert(t('msg_price_number'), "warning");
        return;
    }

    let originalPrice = null;
    if (originalPriceStr !== "") {
        originalPrice = parseFloat(originalPriceStr);
        if (isNaN(originalPrice)) {
            showAlert(t('msg_orig_price_number'), "warning");
            return;
        }
    }

    let discount = null;
    if (discountStr !== "") {
        discount = parseInt(discountStr, 10);
        if (isNaN(discount)) {
            showAlert(t('msg_discount_number'), "warning");
            return;
        }
    }

    // Force confirmation of modifications
    if (!await showConfirm(t('msg_confirm_save'))) {
        return;
    }

    // If there is a new local image file, upload it first
    if (newProductImageFile) {
        const formData = new FormData();
        formData.append("supermarket", supermarket);
        formData.append("store_id", storeId);
        formData.append("offer_id", offerId);
        formData.append("file", newProductImageFile);

        try {
            const imgRes = await fetch('/api/offers/change-image', {
                method: 'POST',
                body: formData
            });

            if (!imgRes.ok) {
                const errData = await imgRes.json();
                throw new Error(errData.error || `HTTP ${imgRes.status} during image upload`);
            }

            const imgData = await imgRes.json();
            if (!imgData.success) {
                throw new Error(imgData.error || "Image upload failed.");
            }
        } catch (err) {
            console.error("Image upload failed:", err);
            showAlert(t('msg_upload_failed', {error: err.message}), "error");
            return; // Abort saving other fields if image upload fails
        }
    }

    // Find original values for fields not edited directly (like category and promo_type)
    const originalOffer = allOffers.find(o => o.supermarket === supermarket && o.store_id === storeId && o.offer_id === offerId);
    const category = originalOffer ? originalOffer.category : "";
    const promoType = originalOffer ? originalOffer.promo_type : "";

    const payload = {
        supermarket,
        store_id: storeId,
        offer_id: offerId,
        name,
        brand: brand || null,
        weight_or_volume: weight || null,
        price,
        original_price: originalPrice,
        discount_percentage: discount,
        ean_code: ean || null,
        category,
        promo_type: promoType
    };

    try {
        const res = await fetch('/api/offers/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.error || `HTTP ${res.status}`);
        }

        const data = await res.json();
        if (data.success) {
            editingOfferKey = null;
            newProductImageFile = null;
            newProductImagePreviewUrl = null;
            await loadOffers();
        } else {
            throw new Error(data.error || "Update operation returned unsuccessful response.");
        }
    } catch (err) {
        console.error("Save edit failed:", err);
        showAlert(t('msg_save_failed', {error: err.message}), "error");
    }
}

// Delete an offer from the database
async function deleteOffer(supermarket, storeId, offerId) {
    if (!await showConfirm(t('msg_confirm_delete'))) {
        return;
    }

    const payload = {
        supermarket,
        store_id: storeId,
        offer_id: offerId
    };

    try {
        const res = await fetch('/api/offers/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.error || `HTTP ${res.status}`);
        }

        const data = await res.json();
        if (data.success) {
            // If the deleted offer was being edited, clear the edit state
            if (editingOfferKey === `${supermarket}|${storeId}|${offerId}`) {
                editingOfferKey = null;
                newProductImageFile = null;
                newProductImagePreviewUrl = null;
            }
            await loadOffers();
        } else {
            throw new Error(data.error || "Delete operation returned unsuccessful response.");
        }
    } catch (err) {
        console.error("Delete offer failed:", err);
        showAlert(t('msg_delete_failed', {error: err.message}), "error");
    }
}

// Triggers the hidden file input click event
function triggerProductImageUpload() {
    const fileInput = document.getElementById('product-image-file-input');
    if (fileInput) {
        fileInput.value = ''; // Reset to allow choosing same file again
        fileInput.click();
    }
}

// Handles selecting a local image file for previewing
function handleProductImageFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        showAlert(t('msg_valid_image'), "warning");
        return;
    }

    newProductImageFile = file;

    const reader = new FileReader();
    reader.onload = function(e) {
        newProductImagePreviewUrl = e.target.result;
        
        // Dynamically update preview element
        const editThumbImg = document.getElementById('edit-thumb-img');
        if (editThumbImg) {
            editThumbImg.src = newProductImagePreviewUrl;
        } else {
            // Re-render table if placeholder was visible
            renderTable();
        }
    };
    reader.readAsDataURL(file);
}

// Show a custom toast notification instead of browser alert()
function showAlert(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const msgSpan = document.createElement('span');
    msgSpan.className = 'toast-message';
    msgSpan.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = () => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    };

    toast.appendChild(msgSpan);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    // Trigger reflow to enable transition
    toast.offsetHeight;
    toast.classList.add('show');

    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}

// Custom promise-based confirm dialog instead of browser confirm()
function showConfirm(message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('confirm-modal');
        const msgEl = document.getElementById('confirm-modal-message');
        const btnConfirm = document.getElementById('confirm-modal-btn-confirm');
        const btnCancel = document.getElementById('confirm-modal-btn-cancel');

        if (!modal || !msgEl || !btnConfirm || !btnCancel) {
            // Fallback to native confirm if element is not found
            resolve(confirm(message));
            return;
        }

        msgEl.textContent = message;
        modal.classList.remove('hidden');

        const cleanup = (value) => {
            modal.classList.add('hidden');
            btnConfirm.onclick = null;
            btnCancel.onclick = null;
            resolve(value);
        };

        btnConfirm.onclick = () => cleanup(true);
        btnCancel.onclick = () => cleanup(false);
    });
}
