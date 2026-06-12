#!/bin/bash
set -e

echo "=== cloud-help-docs-mcp installer ==="

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if [[ $(echo "$PY_VERSION < 3.10" | bc) -eq 1 ]]; then
    echo "❌ Python 3.10+ required (found $PY_VERSION)"
    exit 1
fi
echo "✓ Python $PY_VERSION"

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
echo "✓ Virtual environment ready"

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
echo "   claude mcp add cloud-help-docs-mcp \\"
echo "     -e IQS_API_KEY=<your_key> \\"
echo "     -- $(pwd)/.venv/bin/python -m mcp_servers.cloud_help_docs.server"
echo ""
echo "Or restart Claude Code if already registered."
