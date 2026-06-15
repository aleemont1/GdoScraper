#!/usr/bin/env bash
# Script per la generazione automatica della documentazione delle API con pdoc

# Esci in caso di errore
set -e

# Determina la cartella radice del progetto
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "======================================================================"
echo " GENERAZIONE DELLA DOCUMENTAZIONE DELLE API IN CORSO..."
echo "======================================================================"

# Verifica l'ambiente virtuale
if [ -d ".venv" ]; then
    echo "Attivazione dell'ambiente virtuale .venv..."
    source .venv/bin/activate
else
    echo "ATTENZIONE: Ambiente virtuale .venv non trovato. Verrà usato il python globale."
fi

# Verifica se pdoc è installato
if ! command -v pdoc &> /dev/null && ! python -c "import pdoc" &> /dev/null; then
    echo "Installazione di pdoc tramite uv..."
    if command -v uv &> /dev/null; then
        uv pip install pdoc
    else
        python -m pip install pdoc
    fi
fi

# Generazione della documentazione HTML
echo "Esecuzione di pdoc per generare la documentazione..."
python -m pdoc -o docs/api core drivers utils storage

echo "======================================================================"
echo " GENERAZIONE COMPLETATA CON SUCCESSO!"
echo " La documentazione HTML è disponibile in: docs/api/"
echo " Puoi aprirla nel browser aprendo il file: docs/api/index.html"
echo "======================================================================"
