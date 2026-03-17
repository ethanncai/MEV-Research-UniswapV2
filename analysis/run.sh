#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  MEV Frontrunning Analysis Tool"
echo "  COMP5566 — Project 8"
echo "=========================================="

# --- Locate Python ---
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "Error: python3 not found. Please install Python 3.9+."
    exit 1
fi

echo "Using $($PY --version)"

# --- Virtual environment ---
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment ..."
    $PY -m venv venv
fi

source venv/bin/activate

# --- Install dependencies ---
echo ""
echo "Installing dependencies ..."
pip install -q -r requirements.txt

# --- Run analysis ---
echo ""
python main.py

echo ""
echo "=========================================="
echo "  Results saved to: $SCRIPT_DIR/output/"
echo "=========================================="
