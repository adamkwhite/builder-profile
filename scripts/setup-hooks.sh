#!/bin/bash
# Setup script to install git hooks from scripts/hooks/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_SOURCE="$SCRIPT_DIR/hooks"
HOOKS_DEST=".git/hooks"

echo "Installing git hooks..."

# Copy pre-push hook
if [ -f "$HOOKS_SOURCE/pre-push" ]; then
    cp "$HOOKS_SOURCE/pre-push" "$HOOKS_DEST/pre-push"
    chmod +x "$HOOKS_DEST/pre-push"
    echo "✓ Installed pre-push hook (blocks direct pushes to main)"
fi

echo ""
echo "Git hooks installed successfully!"
