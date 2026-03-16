#!/usr/bin/env bash
#
# install.sh - User-level installer for the mja GUI
#
# This script creates a Python virtual environment under
# ~/.local/share/mja/venv, installs the mja package into it and
# registers a launcher (mja-gui) along with a desktop entry in
# ~/.local/share/applications.  It assumes that Python and
# python-pyside6 are already present on the system.  If PySide6 is
# missing, the user is prompted to install it via pacman and the
# script exits without making changes.

set -euo pipefail

# Determine the directory of this script (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Installation targets
VENV_DIR="$HOME/.local/share/mja/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "[mja-installer] Starting installation..."

command -v python >/dev/null 2>&1 || {
  echo "[mja-installer] Error: python is not installed. Please install Python 3 first." >&2
  exit 1
}

# Check PySide6 availability
if ! python - <<'PY' 2>/dev/null
import importlib.util, sys
sys.exit(0) if importlib.util.find_spec('PySide6') else sys.exit(1)
PY
then
  echo "[mja-installer] PySide6 is not available in your Python environment."
  echo "Please install it via your package manager (e.g. 'sudo pacman -S pyside6') and re-run this script."
  exit 1
fi

# Create or refresh the virtual environment
if [ ! -d "$VENV_DIR" ]; then
  echo "[mja-installer] Creating virtual environment at $VENV_DIR..."
  mkdir -p "$HOME/.local/share/mja"
  python -m venv --system-site-packages "$VENV_DIR"
fi

# Python 3.12+ virtual environments may not bundle setuptools by default.
# Without setuptools the local project cannot be built via pyproject.toml.
if ! "$VENV_DIR/bin/python" - <<'PYSETUP' 2>/dev/null
import importlib.util, sys
sys.exit(0) if importlib.util.find_spec('setuptools.build_meta') else sys.exit(1)
PYSETUP
then
  echo "[mja-installer] Bootstrapping setuptools in the virtual environment..."
  if ! "$VENV_DIR/bin/pip" install --disable-pip-version-check --quiet setuptools wheel; then
    echo "[mja-installer] Error: setuptools could not be bootstrapped automatically." >&2
    echo "Please run '$VENV_DIR/bin/pip install setuptools wheel' manually and re-run install.sh." >&2
    exit 1
  fi
fi

# Install or upgrade the package within the venv
echo "[mja-installer] Installing mja into the virtual environment..."
"$VENV_DIR/bin/pip" install --disable-pip-version-check --no-build-isolation --upgrade "$SCRIPT_DIR"

# Ensure ~/.local/bin exists and create launcher script
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/mja-gui"
cat >"$LAUNCHER" <<'SH'
#!/usr/bin/env bash
VENV_PATH="$HOME/.local/share/mja/venv"
exec "$VENV_PATH/bin/mja-gui" "$@"
SH
chmod +x "$LAUNCHER"

# Install .desktop file for application menu
mkdir -p "$DESKTOP_DIR"
DESKTOP_ENTRY="$DESKTOP_DIR/mja-gui.desktop"
cat >"$DESKTOP_ENTRY" <<DESKTOP
[Desktop Entry]
Type=Application
Name=mja GUI
Comment=GUI for Manjaro AUR isolation orchestrator
Exec=$LAUNCHER
Terminal=false
Icon=system-software-install
Categories=System;Utility;
StartupNotify=true
DESKTOP

# Optionally update desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" || true
fi

echo "[mja-installer] Installation complete."
echo "The virtual environment is located at: $VENV_DIR"
echo "Launch the GUI via 'mja-gui' or from your applications menu."

# Warn if ~/.local/bin is not on PATH
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "[mja-installer] Warning: $HOME/.local/bin is not in your PATH. You may need to add it to your shell configuration." ;;
esac

exit 0
