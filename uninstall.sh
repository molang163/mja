#!/usr/bin/env bash
#
# uninstall.sh - Uninstaller for the mja GUI
#
# This script removes the user-level installation created by install.sh.
# By default it deletes the virtual environment, launcher and desktop entry
# while preserving user data.  Passing --purge additionally removes
# state, configuration and cache data.  No sudo privileges are required
# because all files reside under the user's home directory.

set -euo pipefail

PURGE=0
if [[ $# -gt 0 ]]; then
  case "$1" in
    --purge)
      PURGE=1
      ;;
    *)
      echo "Usage: $0 [--purge]" >&2
      exit 1
      ;;
  esac
fi

VENV_DIR="$HOME/.local/share/mja/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
STATE_DIR="$HOME/.local/state/mja"
SHARE_DIR="$HOME/.local/share/mja"

# Resolve desktop directory (best effort)
DESKTOP_DIR_ALT="$HOME/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR_ALT="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
fi
DESKTOP_SHORTCUT="$DESKTOP_DIR_ALT/mja-gui.desktop"

echo "[mja-uninstaller] Starting uninstallation..."

# Remove launcher
LAUNCHER="$BIN_DIR/mja-gui"
if [ -e "$LAUNCHER" ]; then
  echo "[mja-uninstaller] Removing launcher: $LAUNCHER"
  rm -f "$LAUNCHER"
fi

# Remove desktop entry
DESKTOP_ENTRY="$DESKTOP_DIR/mja-gui.desktop"
if [ -e "$DESKTOP_ENTRY" ]; then
  echo "[mja-uninstaller] Removing desktop entry: $DESKTOP_ENTRY"
  rm -f "$DESKTOP_ENTRY"
fi

# Remove desktop shortcut if present
if [ -e "$DESKTOP_SHORTCUT" ]; then
  echo "[mja-uninstaller] Removing desktop shortcut: $DESKTOP_SHORTCUT"
  rm -f "$DESKTOP_SHORTCUT"
fi

# Remove virtual environment
if [ -d "$VENV_DIR" ]; then
  echo "[mja-uninstaller] Removing virtual environment: $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

# Remove share directory if empty or on purge
if [ $PURGE -eq 1 ]; then
  # Remove state directory
  if [ -d "$STATE_DIR" ]; then
    echo "[mja-uninstaller] Purging state directory: $STATE_DIR"
    rm -rf "$STATE_DIR"
  fi
  # Remove share directory (includes venv and other data)
  if [ -d "$SHARE_DIR" ]; then
    echo "[mja-uninstaller] Purging share directory: $SHARE_DIR"
    rm -rf "$SHARE_DIR"
  fi
fi

echo "[mja-uninstaller] Uninstallation complete."
if [ $PURGE -eq 1 ]; then
  echo "All program files, configuration and state have been removed."
else
  echo "Program files have been removed. State and log data remain in $STATE_DIR."
fi

exit 0