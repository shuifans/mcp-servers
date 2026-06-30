#!/bin/bash
set -euo pipefail

echo "=== cloud-help-docs-mcp installer ==="

# Resolve to the script's own directory so the installer works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Require uv (single source of truth for env + dependency resolution via uv.lock).
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found."
    echo "   Install it with one of:"
    echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "     brew install uv"
    echo "     pip install uv"
    exit 1
fi
echo "✓ uv $(uv --version | awk '{print $2}')"

# Create the virtual environment and install locked dependencies (incl. dev extras).
# uv reads requires-python from pyproject.toml and provisions a matching interpreter
# if needed, so no manual Python version check / bc is required.
echo "Syncing dependencies from uv.lock..."
uv sync --extra dev
echo "✓ Dependencies installed (.venv ready)"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "1. Get your IQS API key at: https://iqs.console.aliyun.com/"
echo "2. Register the MCP server in Claude Code (key passed via -e, never committed):"
echo ""
echo "   claude mcp add cloud-help-docs-mcp -s user \\"
echo "     -e IQS_API_KEY=<your_key> \\"
echo "     -- $SCRIPT_DIR/.venv/bin/python -m mcp_servers.cloud_help_docs.server"
echo ""
echo "Or restart Claude Code if already registered."
