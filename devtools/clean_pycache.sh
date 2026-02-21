#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

echo "Cleaning Python cache under: $ROOT_DIR"

find "$ROOT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$ROOT_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

echo "Done."
