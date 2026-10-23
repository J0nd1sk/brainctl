#!/usr/bin/env bash
# Build a standalone brainctl-mcp binary via PyInstaller.
# Output: dist/brainctl-mcp on the current platform.

set -euo pipefail

cd "$(dirname "$0")/.."

# Detect target triple (used in artifact naming)
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) TARGET="aarch64-apple-darwin" ;;
    Darwin-x86_64) TARGET="x86_64-apple-darwin" ;;
    Linux-x86_64) TARGET="x86_64-unknown-linux-gnu" ;;
    MINGW*|MSYS*|CYGWIN*) TARGET="x86_64-pc-windows-msvc" ;;
    *) echo "Unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

echo "Building brainctl-mcp bundle for $TARGET..."

# Set up venv if not present
if [ ! -d .venv-bundle ]; then
    python3 -m venv .venv-bundle
fi
source .venv-bundle/bin/activate

# Install brainctl + PyInstaller
pip install -e ".[mcp]" >/dev/null
pip install "pyinstaller>=6.0" >/dev/null

# Build
pyinstaller --clean --noconfirm build/pyinstaller/brainctl_mcp.spec

# Verify the binary runs
echo "Verifying binary..."
./dist/brainctl-mcp --help 2>&1 | head -5 || echo "(no --help flag; binary built but help not available)"

# Stamp with target triple
mv dist/brainctl-mcp "dist/brainctl-mcp-$TARGET"
echo "Built: dist/brainctl-mcp-$TARGET"
