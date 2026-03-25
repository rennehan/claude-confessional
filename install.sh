#!/usr/bin/env bash
set -euo pipefail

# Claude Confessional installer
# Copies commands and scripts into ~/.claude/, registers hooks.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIOUS=false

for arg in "$@"; do
    case "$arg" in
        --pious) PIOUS=true ;;
    esac
done

echo "Installing Claude Confessional..."

# Clean up old commands/ layout (pre-skills migration)
OLD_CMDS=(record reflect confess amen sermon breakpoint dashboard)
for cmd in "${OLD_CMDS[@]}"; do
    rm -f ~/.claude/commands/"$cmd".md
done
rmdir ~/.claude/commands/ 2>/dev/null || true
echo "Cleaned up legacy commands/ files (if any)..."

# Create directories
mkdir -p ~/.claude/skills/record ~/.claude/skills/reflect ~/.claude/scripts

# Core skills
cp "$SCRIPT_DIR/.claude/skills/record/SKILL.md"   ~/.claude/skills/record/
cp "$SCRIPT_DIR/.claude/skills/reflect/SKILL.md"   ~/.claude/skills/reflect/

# Liturgical aliases (optional)
if [ "$PIOUS" = true ]; then
    mkdir -p ~/.claude/skills/confess ~/.claude/skills/amen ~/.claude/skills/sermon
    cp "$SCRIPT_DIR/.claude/skills/confess/SKILL.md"   ~/.claude/skills/confess/
    cp "$SCRIPT_DIR/.claude/skills/amen/SKILL.md"       ~/.claude/skills/amen/
    cp "$SCRIPT_DIR/.claude/skills/sermon/SKILL.md"     ~/.claude/skills/sermon/
    echo "Liturgical skills installed: /confess, /amen, /sermon"
fi

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

# Praying hands ASCII art by ejm (ascii.co.uk/art/prayer)
cat <<'ART'

 ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗
██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝
██║     ██║     ███████║██║   ██║██║  ██║█████╗
██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝
╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗
 ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝
       C O N F E S S I O N A L

ART

sleep 0.3

lines=(
"                         _"
"                       _|_|_"
"                     ,|_| |_|_"
"                     || | | |_|"
"                     || | | | |"
"                     || | | | |"
"                    _|| | | | |"
"                  ||)\\  ^ ^ ^ |"
"                  || |        |"
"                  || |        |"
"                  || |        |"
"                  \\\\          |"
"                   \\\\         /"
"                    )\\       ("
"                   /  \\       \\"
"                  /    \\       \\"
"                        \\       \\"
)

for line in "${lines[@]}"; do
    echo "$line"
    sleep 0.05
done

sleep 0.2
echo ""
echo "  ██████████████████████████████████████████████████"
echo "  █                                                █"
echo "  █        Restart Claude Code to begin.           █"
echo "  █                                                █"
echo "  ██████████████████████████████████████████████████"
echo ""
