#!/bin/bash
set -e

echo "=== aliyun-help-docs-mcp installer ==="

# Prefer python3.12 (Homebrew), fallback to python3
PYTHON_BIN=""
for candidate in python3.12 python3; do
    if command -v "$candidate" &> /dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ $(echo "$ver >= 3.10" | bc) -eq 1 ]]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python 3.10+ not found (install via: brew install python@3.12)"
    exit 1
fi
echo "✓ Python $ver ($PYTHON_BIN)"

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
fi
echo "✓ Virtual environment ready"

# Upgrade pip first (needed for hatchling editable installs)
echo "Upgrading pip..."
.venv/bin/pip install --upgrade pip --quiet

# Install package
echo "Installing dependencies..."
.venv/bin/pip install -e . --quiet
echo "✓ Dependencies installed"

# Create .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Please edit .env and set your IQS_API_KEY"
    echo "   Get your API key at: https://iqs.console.aliyun.com/"
    echo ""
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your IQS_API_KEY"
echo "2. Register MCP server in Claude Code:"
echo ""
echo "   claude mcp add aliyun-help-docs-mcp \\"
echo "     -e IQS_API_KEY=<your_key> \\"
echo "     -- $(pwd)/.venv/bin/python -m mcp_servers.aliyun_help_docs.server"
echo ""
echo "Or restart Claude Code if already registered."
