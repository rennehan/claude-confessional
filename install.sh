#!/usr/bin/env bash
set -euo pipefail

# Claude Confessional installer
# Copies commands and scripts into ~/.claude/, registers hooks.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Claude Confessional..."

# Create directories
mkdir -p ~/.claude/commands ~/.claude/scripts

# Core commands
cp "$SCRIPT_DIR/record.md"      ~/.claude/commands/
cp "$SCRIPT_DIR/breakpoint.md"  ~/.claude/commands/
cp "$SCRIPT_DIR/reflect.md"     ~/.claude/commands/

# Liturgical aliases
cp "$SCRIPT_DIR/confess.md"     ~/.claude/commands/
cp "$SCRIPT_DIR/amen.md"        ~/.claude/commands/
cp "$SCRIPT_DIR/sermon.md"      ~/.claude/commands/

# Scripts
cp "$SCRIPT_DIR/confessional_store.py"  ~/.claude/scripts/
cp "$SCRIPT_DIR/transcript_reader.py"   ~/.claude/scripts/
cp "$SCRIPT_DIR/confessional_hook.py"   ~/.claude/scripts/
cp "$SCRIPT_DIR/dashboard_generator.py" ~/.claude/scripts/
chmod +x ~/.claude/scripts/confessional_store.py \
         ~/.claude/scripts/transcript_reader.py \
         ~/.claude/scripts/confessional_hook.py \
         ~/.claude/scripts/dashboard_generator.py

# Register hooks
python3 ~/.claude/scripts/confessional_hook.py --install

echo "Done. Restart Claude Code to activate hooks."
