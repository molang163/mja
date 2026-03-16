# mja: The Zero-Pollution AUR Manager for Manjaro

Languages: [English](README.md) | [简体中文](README.zh-CN.md)

> **🎯 Who is this for?**
> Manjaro desktop users who want the vast software library of the AUR without risking the stability of their host system. Best for those who prefer a GUI-assisted workflow for containerized package management.
> 
>🛑 Who is this NOT for?**
> Users of any non-Manjaro distribution (including Arch Linux, Ubuntu, Fedora), or those looking for a general-purpose cross-distro package manager.

Tired of AUR packages breaking your Manjaro system? mja is an orchestrator that isolates AUR packages into a Distrobox container, keeping your official host repositories completely untouched.

![mja GUI ](./docs/screenshot.png)

## Core Concept

Manjaro users want system stability but need the vast software library of the AUR. Mixing rolling-release AUR packages with Manjaro's delayed stable branch often leads to dependency hell.

mja acts as a strict routing layer:
1. Official Repo Packages: Routed directly to your host's pacman/pamac.
2. AUR Packages: Compiled and installed inside an isolated Arch Linux container (mja-arch) via paru.
3. Desktop Integration: Automatically exports .desktop files or CLI binaries back to your host.

## Installation

We provide a minimalist native GUI built with PySide6.

Note: In Arch/Manjaro systems, do not use `pip install PySide6` as it may break the externally-managed environment. Install dependencies via the system package manager:

```bash
# 1. Install Qt dependency
sudo pacman -S pyside6

# 2. Clone and run the installer
git clone https://github.com/molang163/mja.git
cd mja
bash install.sh
```

Once installed, you can launch it from your desktop application menu or type `mja-gui` in the terminal.

## Uninstallation

We respect your system. Clean installation comes with clean uninstallation:

```bash
# Run from the source directory:
bash uninstall.sh         # Standard removal (keeps state and logs)
bash uninstall.sh --purge # Nuclear option (removes state, configs, and containers)
```

## CLI Usage

For power users, mja provides a robust command-line interface:

```bash
# Smart search (Host and AUR)
mja search obsidian

# Install AUR package and export desktop icon
mja install obsidian --source aur --export auto

# Health diagnostics
mja doctor

# Remove package and clean up exported shortcuts
mja remove obsidian --unexport
```
