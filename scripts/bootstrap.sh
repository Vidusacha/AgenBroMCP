#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Bootstrapping AgenBroMCP in $REPO_ROOT ==="

# 1. Ensure uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Check tesseract
if ! command -v tesseract >/dev/null 2>&1; then
    echo "Notice: system 'tesseract' not found in PATH. Install via apt/brew (e.g. 'sudo apt-get install -y tesseract-ocr tesseract-ocr-rus') or rely on built-in RapidOCR fallback."
fi

# 3. Sync Python environment
uv sync --all-extras

# 4. Install Playwright Chromium
uv run playwright install chromium

# 5. Create artifacts directory
mkdir -p "$REPO_ROOT/artifacts"

echo "=== Bootstrap complete! Run tests with: uv run pytest ==="
