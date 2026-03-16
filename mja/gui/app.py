from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Import helper for formatting popularity values from the search module
from mja.search import format_popularity, sort_search_dicts

APP_TITLE = "mja GUI"
from mja import __version__ as APP_VERSION

# ---------------------------------------------------------------------------
# Simple in-memory translation system
#
# The GUI defaults to Chinese text for all labels, messages and buttons.  To
# support switching between Chinese and English without pulling in a full i18n
# framework we define a translation dictionary keyed by the original text.
# Each entry maps language codes ("zh" and "en") to the corresponding
# translation.  The helper ``tr()`` returns the translation according to
# ``current_language``, defaulting to the original string when no mapping is
# available.

# Current UI language; 'zh' by default
current_language = 'zh'

# Translation table.  Keys correspond to the original Chinese (or English)
# text used in the UI.  Each entry provides the Chinese (zh) and English (en)
# versions.  When adding new UI strings ensure both languages are supplied.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "搜索": {"zh": "搜索", "en": "Search"},
    "输入包名，例如 google-chrome / nitch / vlc": {
        "zh": "输入包名，例如 google-chrome / nitch / vlc",
        "en": "Enter package name, e.g. google-chrome / nitch / vlc",
    },
    "全部": {"zh": "全部", "en": "All"},
    "仅 repo": {"zh": "仅 repo", "en": "Repo only"},
    "仅 AUR": {"zh": "仅 AUR", "en": "AUR only"},
    "安装选中包": {"zh": "安装选中包", "en": "Install selected package"},
    "当前未选择包": {"zh": "当前未选择包", "en": "No package selected"},
    "当前选择：": {"zh": "当前选择：", "en": "Selected: "},
    "来源": {"zh": "来源", "en": "Source"},
    "名称": {"zh": "名称", "en": "Name"},
    "版本": {"zh": "版本", "en": "Version"},
    "精确匹配": {"zh": "精确匹配", "en": "Exact"},
    "描述": {"zh": "描述", "en": "Description"},
    "热度/票数": {"zh": "热度/票数", "en": "Popularity/Votes"},
    "正在安装或编译软件，某些步骤可能持续数分钟，请耐心等待。": {
        "zh": "正在安装或编译软件，某些步骤可能持续数分钟，请耐心等待。",
        "en": "Installing or building software may take several minutes during some steps. Please wait patiently.",
    },
    "安装成功后创建桌面快捷方式": {
        "zh": "安装成功后创建桌面快捷方式",
        "en": "Create desktop shortcut after successful installation",
    },
    "已取消，正在结束任务……": {"zh": "已取消，正在结束任务……", "en": "Cancelled, ending the task..."},
    "任务已取消": {"zh": "任务已取消", "en": "The task was cancelled"},
    "软件已安装，但未找到可用于创建桌面快捷方式的 desktop 文件。": {
        "zh": "软件已安装，但未找到可用于创建桌面快捷方式的 desktop 文件。",
        "en": "The software was installed, but no desktop file suitable for creating a desktop shortcut was found.",
    },
    "桌面快捷方式已创建": {
        "zh": "桌面快捷方式已创建",
        "en": "Desktop shortcut created successfully",
    },
    # Dialog and form labels
    "包名": {"zh": "包名", "en": "Package name"},
    "来源": {"zh": "来源", "en": "Source"},
    "导出模式": {"zh": "导出模式", "en": "Export mode"},
    "bin 名称": {"zh": "bin 名称", "en": "Binary name"},
    "开始安装": {"zh": "开始安装", "en": "Start installation"},
    "取消": {"zh": "取消", "en": "Cancel"},
    "确认": {"zh": "确认", "en": "Confirm"},
    "确认选择": {"zh": "确认选择", "en": "Confirm selection"},
    "开始卸载": {"zh": "开始卸载", "en": "Start removal"},
    "同时 unexport": {"zh": "同时 unexport", "en": "Unexport as well"},
    "是": {"zh": "是", "en": "Yes"},
    "否": {"zh": "否", "en": "No"},
    "开始修复": {"zh": "开始修复", "en": "Start repair"},
    "修复模式": {"zh": "修复模式", "en": "Repair mode"},
    # Navigation and status
    "仪表盘": {"zh": "仪表盘", "en": "Dashboard"},
    "已安装": {"zh": "已安装", "en": "Installed"},
    "日志": {"zh": "日志", "en": "Logs"},
    "维护": {"zh": "维护", "en": "Maintenance"},
    "就绪": {"zh": "就绪", "en": "Ready"},
    "当前页面：": {"zh": "当前页面：", "en": "Current page: "},
    "刷新全部": {"zh": "刷新全部", "en": "Refresh All"},
    "退出": {"zh": "退出", "en": "Exit"},
    "文件": {"zh": "文件", "en": "File"},
    "语言": {"zh": "语言", "en": "Language"},
    "中文": {"zh": "中文", "en": "Chinese"},
    "Refresh Logs": {"zh": "Refresh Logs", "en": "Refresh Logs"},
    # Misc messages
    "先输入要搜索的包名。": {"zh": "先输入要搜索的包名。", "en": "Please enter a package name first."},
    "全部记录": {"zh": "全部记录", "en": "All records"},
    "仅已安装": {"zh": "仅已安装", "en": "Installed only"},
    "显示": {"zh": "显示", "en": "Show"},
    "刷新": {"zh": "刷新", "en": "Refresh"},
    "更新": {"zh": "更新", "en": "Update"},
    "卸载": {"zh": "卸载", "en": "Remove"},
    "修复导出": {"zh": "修复导出", "en": "Repair Export"},
    "安装状态": {"zh": "安装状态", "en": "Install Status"},
    "导出状态": {"zh": "导出状态", "en": "Export Status"},
    "容器": {"zh": "容器", "en": "Container"},
    "安装时间": {"zh": "安装时间", "en": "Installed At"},
    "日志路径：": {"zh": "日志路径：", "en": "Log path: "},
    "最近日志会显示在这里。": {"zh": "最近日志会显示在这里。", "en": "Recent logs will be shown here."},
    "还没有 latest.log。先执行一次 install / update / remove 之类的命令。": {"zh": "还没有 latest.log。先执行一次 install / update / remove 之类的命令。", "en": "No latest.log yet. Run an install / update / remove task first."},
    "高级维护": {"zh": "高级维护", "en": "Advanced Maintenance"},
    "状态修复": {"zh": "状态修复", "en": "State Repair"},
    "运行 doctor": {"zh": "运行 doctor", "en": "Run doctor"},
    "尚未获取环境信息。": {"zh": "尚未获取环境信息。", "en": "Environment information has not been loaded yet."},
    "正在检查环境……": {"zh": "正在检查环境……", "en": "Checking environment..."},
    "正在读取 doctor 结果……": {"zh": "正在读取 doctor 结果……", "en": "Reading doctor results..."},
    "这里会显示 doctor 的摘要。": {"zh": "这里会显示 doctor 的摘要。", "en": "The doctor summary will be shown here."},
    "Doctor 状态": {"zh": "Doctor 状态", "en": "Doctor Status"},
    "State 文件": {"zh": "State 文件", "en": "State File"},
    "环境判断": {"zh": "环境判断", "en": "Environment"},
    "导出异常": {"zh": "导出异常", "en": "Export Issues"},
    "健康": {"zh": "健康", "en": "Healthy"},
    "有问题": {"zh": "有问题", "en": "Issues"},
    "完全支持": {"zh": "完全支持", "en": "Fully supported"},
    "非官方支持": {"zh": "非官方支持", "en": "Unofficial support"},
    "部分未配置": {"zh": "部分未配置", "en": "Partially configured"},
    "强制关闭": {"zh": "强制关闭", "en": "Force Close"},
    "关闭窗口": {"zh": "关闭窗口", "en": "Close Window"},
    "查看详细输出": {"zh": "查看详细输出", "en": "Show Details"},
    "隐藏详细输出": {"zh": "隐藏详细输出", "en": "Hide Details"},
    "更新范围": {"zh": "更新范围", "en": "Update Scope"},
    "更新包": {"zh": "更新包", "en": "Update Packages"},
    "开始更新": {"zh": "开始更新", "en": "Start Update"},
    "安装": {"zh": "安装", "en": "Install"},
    "卸载": {"zh": "卸载", "en": "Remove"},
    "开始修复": {"zh": "开始修复", "en": "Start Repair"},
    "开始卸载": {"zh": "开始卸载", "en": "Start Removal"},
    "开始安装": {"zh": "开始安装", "en": "Start Installation"},
    "同时 unexport": {"zh": "同时 unexport", "en": "Unexport as well"},
    "修复模式": {"zh": "修复模式", "en": "Repair Mode"},
    "可选：仅 mode=bin 时常用": {"zh": "可选：仅 mode=bin 时常用", "en": "Optional: mainly used when mode=bin"},
    "可选：指定 bin 名称，仅 export=bin 时常用": {"zh": "可选：指定 bin 名称，仅 export=bin 时常用", "en": "Optional: specify a binary name, mainly used when export=bin"},
    "正在初始化任务……": {"zh": "正在初始化任务……", "en": "Initializing task..."},
    "正在执行任务（PTY 模式开启）……": {"zh": "正在执行任务（PTY 模式开启）……", "en": "Running task (PTY mode enabled)..."},
    "正在执行任务（未检测到 script，输出可能延迟）……": {"zh": "正在执行任务（未检测到 script，输出可能延迟）……", "en": "Running task (script not found, output may be delayed)..."},
    "已提交密码，请稍候……": {"zh": "已提交密码，请稍候……", "en": "Password submitted. Please wait..."},
    "已选择提供者，继续执行任务……": {"zh": "已选择提供者，继续执行任务……", "en": "Provider selected. Continuing task..."},
    "已确认，继续执行任务……": {"zh": "已确认，继续执行任务……", "en": "Confirmed. Continuing task..."},
    "命令失败": {"zh": "命令失败", "en": "Command Failed"},
    "只读操作失败。请查看详细输出。": {"zh": "只读操作失败。请查看详细输出。", "en": "Read-only operation failed. Please check the detailed output."},
    "显示": {"zh": "显示", "en": "Show"},
    "先选中一个包。": {"zh": "先选中一个包。", "en": "Please select a package first."},
    "执行 update": {"zh": "执行 update", "en": "Run update"},
    "执行 state rebuild": {"zh": "执行 state rebuild", "en": "Run state rebuild"},
    "刷新日志": {"zh": "刷新日志", "en": "Refresh Logs"},
    "需要提权": {"zh": "需要提权", "en": "Privileges Required"},
    "执行此操作需要管理员权限（sudo），请输入密码：": {"zh": "执行此操作需要管理员权限（sudo），请输入密码：", "en": "This action requires administrator privileges (sudo). Please enter your password:"},
    "需要认证": {"zh": "需要认证", "en": "Authentication Required"},
    "后台任务正在请求密码，请输入密码：": {"zh": "后台任务正在请求密码，请输入密码：", "en": "The background task is requesting a password. Please enter it:"},
    "为": {"zh": "为", "en": "Select provider for"},
    "选择提供者": {"zh": "选择提供者", "en": ""},
    "检测到多个可选提供者，请选择要安装的条目。": {"zh": "检测到多个可选提供者，请选择要安装的条目。", "en": "Multiple providers were found. Please choose the package to install."},
    "需要确认": {"zh": "需要确认", "en": "Confirmation Required"},
    "检测到后台任务需要确认（Y/n）。是否继续？": {"zh": "检测到后台任务需要确认（Y/n）。是否继续？", "en": "The background task requires confirmation (Y/n). Continue?"},
    "继续": {"zh": "继续", "en": "Continue"},
    "安装完成：": {"zh": "安装完成：", "en": "Installation completed: "},
    "卸载完成：": {"zh": "卸载完成：", "en": "Removal completed: "},
    "导出修复完成：": {"zh": "导出修复完成：", "en": "Export repair completed: "},
    "更新完成：": {"zh": "更新完成：", "en": "Update completed: "},
    "状态重建完成": {"zh": "状态重建完成", "en": "State rebuild completed"},
    "命令执行完成": {"zh": "命令执行完成", "en": "Command completed"},
    "界面已自动刷新。": {"zh": "界面已自动刷新。", "en": "The interface has been refreshed automatically."},
    "更新失败。请查看详细输出，确认是镜像、认证还是容器环境问题。": {"zh": "更新失败。请查看详细输出，确认是镜像、认证还是容器环境问题。", "en": "Update failed. Check the detailed output for mirror, authentication, or container issues."},
    "安装失败：": {"zh": "安装失败：", "en": "Installation failed: "},
    "卸载失败：": {"zh": "卸载失败：", "en": "Removal failed: "},
    "导出修复失败：": {"zh": "导出修复失败：", "en": "Export repair failed: "},
    "目标包": {"zh": "目标包", "en": "target package"},
    "未能成功安装。请查看详细输出。": {"zh": "未能成功安装。请查看详细输出。", "en": "could not be installed successfully. Please check the detailed output."},
    "未能成功移除。请查看详细输出。": {"zh": "未能成功移除。请查看详细输出。", "en": "could not be removed successfully. Please check the detailed output."},
    "未能成功修复。请查看详细输出。": {"zh": "未能成功修复。请查看详细输出。", "en": "could not be repaired successfully. Please check the detailed output."},
    "未知": {"zh": "未知", "en": "Unknown"},
    "PySide6 不可用，无法启动桌面界面。": {"zh": "PySide6 不可用，无法启动桌面界面。", "en": "PySide6 is unavailable, so the desktop interface cannot be started."},
    "导入错误：": {"zh": "导入错误：", "en": "Import error: "},
    "你可以做的事：": {"zh": "你可以做的事：", "en": "You can do the following:"},
    "1. 安装 PySide6 后重新运行这个脚本": {"zh": "1. 安装 PySide6 后重新运行这个脚本", "en": "1. Install PySide6 and run this script again"},
    "2. 继续直接使用 CLI：python -m mja --help": {"zh": "2. 继续直接使用 CLI：python -m mja --help", "en": "2. Continue using the CLI directly: python -m mja --help"},
    "3. 先查看当前环境和状态摘要": {"zh": "3. 先查看当前环境和状态摘要", "en": "3. Check the current environment and state summary first"},
    "doctor 摘要不可用。": {"zh": "doctor 摘要不可用。", "en": "The doctor summary is unavailable."},
    "最近日志（末尾）：": {"zh": "最近日志（末尾）：", "en": "Recent log tail:"},
    "doctor 总状态：": {"zh": "doctor 总状态：", "en": "Doctor overall status: "},
    "未知 Linux": {"zh": "未知 Linux", "en": "Unknown Linux"},
    "系统检测为 {os_pretty}，但 pamac 不可用。mja 的 Manjaro 主路径可能不完整。": {"zh": "系统检测为 {os_pretty}，但 pamac 不可用。mja 的 Manjaro 主路径可能不完整。", "en": "The system was detected as {os_pretty}, but pamac is unavailable. The main Manjaro path of mja may be incomplete."},
    "系统检测为 {os_pretty}，基础路径可用，但容器工具链尚未配置。": {"zh": "系统检测为 {os_pretty}，基础路径可用，但容器工具链尚未配置。", "en": "The system was detected as {os_pretty}. The base path is available, but the container toolchain is not configured yet."},
    "系统检测为 {os_pretty}，环境检查通过。": {"zh": "系统检测为 {os_pretty}，环境检查通过。", "en": "The system was detected as {os_pretty}. Environment checks passed."},
    "当前系统检测为 {os_pretty}。mja 主要为 Manjaro 设计，在该系统上属于非官方支持环境。": {"zh": "当前系统检测为 {os_pretty}。mja 主要为 Manjaro 设计，在该系统上属于非官方支持环境。", "en": "The current system was detected as {os_pretty}. mja is mainly designed for Manjaro and is considered an unofficially supported environment on this system."},
    " 同时容器工具链也未配置。": {"zh": " 同时容器工具链也未配置。", "en": " The container toolchain is also not configured."},
    "系统身份未识别，但当前环境缺少 pamac，看起来更像 Arch 或其他非 Manjaro 系统。": {"zh": "系统身份未识别，但当前环境缺少 pamac，看起来更像 Arch 或其他非 Manjaro 系统。", "en": "The system identity could not be determined, but pamac is missing. This environment looks more like Arch or another non-Manjaro system."},
    "系统身份未识别，且容器工具链尚未配置。": {"zh": "系统身份未识别，且容器工具链尚未配置。", "en": "The system identity could not be determined, and the container toolchain is not configured yet."},
    "系统身份未识别，但基础检查已完成。": {"zh": "系统身份未识别，但基础检查已完成。", "en": "The system identity could not be determined, but the basic checks have completed."},
    "正在更新软件包，某些步骤可能持续数分钟，请耐心等待。": {"zh": "正在更新软件包，某些步骤可能持续数分钟，请耐心等待。", "en": "Updating packages may take several minutes during some steps. Please wait patiently."},
    "正在卸载软件，某些步骤可能持续数分钟，请耐心等待。": {"zh": "正在卸载软件，某些步骤可能持续数分钟，请耐心等待。", "en": "Removing software may take several minutes during some steps. Please wait patiently."},
    "正在修复导出，某些步骤可能持续数分钟，请耐心等待。": {"zh": "正在修复导出，某些步骤可能持续数分钟，请耐心等待。", "en": "Repairing exports may take several minutes during some steps. Please wait patiently."},
    "正在重建状态，某些步骤可能持续数分钟，请耐心等待。": {"zh": "正在重建状态，某些步骤可能持续数分钟，请耐心等待。", "en": "Rebuilding state may take several minutes during some steps. Please wait patiently."},
}

def tr(text: str) -> str:
    """Return the translated string for the current language.

    Args:
        text: The original text used in the code.  This key is looked up in the
            ``TRANSLATIONS`` dictionary.  If no entry exists, the text is
            returned unchanged.

    Returns:
        The translated string for ``current_language``, or the original text
        when no translation is available.
    """
    entry = TRANSLATIONS.get(text)
    if entry is None:
        return text
    return entry.get(current_language, text)


def set_language(lang: str) -> None:
    """Set the application language.

    Changing the language updates the ``current_language`` global.  UI code
    should call an appropriate ``update_language()`` method to refresh
    existing widgets after invoking this function.

    Args:
        lang: Either 'zh' (Chinese) or 'en' (English).
    """
    global current_language
    if lang in ("zh", "en"):
        current_language = lang

# ---------------------------------------------------------------------------
# Desktop shortcut helper
#
# After a successful installation the user can choose to create a desktop
# shortcut on the host.  Desktop entries exported via distrobox are stored
# under ``~/.local/share/applications`` on the host.  Their file names may
# either be the bare package name (e.g. ``foo.desktop``) or prefixed with
# the container name (e.g. ``mja-arch-foo.desktop`` or ``container-foo.desktop``).
# The helper below attempts to locate a matching desktop file for a given
# package and copy it to ``~/Desktop``.  It returns True on success and
# False if no appropriate file is found.
def _resolve_desktop_dir(home_path: Path | None = None) -> Path:
    """Resolve the user's desktop directory using XDG conventions when possible."""
    home_path = home_path or Path.home()

    xdg_user_dir = shutil.which("xdg-user-dir")
    if xdg_user_dir:
        try:
            result = subprocess.run([xdg_user_dir, "DESKTOP"], capture_output=True, text=True, check=False)
            candidate = result.stdout.strip()
            if result.returncode == 0 and candidate:
                resolved = Path(candidate).expanduser()
                if resolved.is_absolute():
                    return resolved
        except Exception:
            pass

    config_path = home_path / ".config" / "user-dirs.dirs"
    if config_path.exists():
        try:
            for line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("XDG_DESKTOP_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    value = value.replace("$HOME", str(home_path))
                    return Path(value).expanduser()
        except Exception:
            pass

    return home_path / "Desktop"



def get_wait_message(operation: str) -> str:
    mapping = {
        "install": tr("正在安装或编译软件，某些步骤可能持续数分钟，请耐心等待。"),
        "update": tr("正在更新软件包，某些步骤可能持续数分钟，请耐心等待。"),
        "remove": tr("正在卸载软件，某些步骤可能持续数分钟，请耐心等待。"),
        "repair": tr("正在修复导出，某些步骤可能持续数分钟，请耐心等待。"),
        "rebuild": tr("正在重建状态，某些步骤可能持续数分钟，请耐心等待。"),
    }
    return mapping.get(operation, "")

def copy_desktop_shortcut(package_name: str) -> bool:
    """Copy an exported desktop file for the given package to the user's desktop.

    Host-side desktop files may be exported using the desktop entry basename
    (e.g. ``com.google.Chrome.desktop``) rather than the package name.  To avoid
    false negatives we first inspect the state file for recorded
    ``desktop_entries`` and then search the exported applications directory for
    exact basenames and prefixed variants.  If the state file is unavailable we
    fall back to package-name based guesses.
    """
    home_path = Path.home()
    base_dir = home_path / ".local" / "share" / "applications"
    if not base_dir.is_dir():
        return False

    expected_names: list[str] = []
    state_path = home_path / ".local" / "state" / "mja" / "state.json"
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            record = payload.get("packages", {}).get(package_name, {})
            for entry in record.get("desktop_entries", []):
                name = Path(entry).name
                if name and name not in expected_names:
                    expected_names.append(name)
        except Exception:
            pass

    fallback_name = f"{package_name}.desktop"
    if fallback_name not in expected_names:
        expected_names.append(fallback_name)

    candidates: list[Path] = []
    seen: set[str] = set()
    try:
        for expected in expected_names:
            direct = base_dir / expected
            if direct.is_file() and str(direct) not in seen:
                candidates.append(direct)
                seen.add(str(direct))
            for entry in base_dir.iterdir():
                if not entry.is_file() or not entry.name.endswith(".desktop"):
                    continue
                if entry.name == expected or entry.name.endswith(f"-{expected}") or entry.name.endswith(f"-{package_name}.desktop"):
                    if str(entry) not in seen:
                        candidates.append(entry)
                        seen.add(str(entry))
    except Exception:
        return False

    if not candidates:
        return False

    desktop_dir = _resolve_desktop_dir(home_path)
    try:
        desktop_dir.mkdir(parents=True, exist_ok=True)
        source = candidates[0]
        target = desktop_dir / source.name
        shutil.copy2(source, target)
        try:
            mode = source.stat().st_mode
            target.chmod(mode | 0o100)
        except Exception:
            pass
        return True
    except Exception:
        return False

try:
    from PySide6.QtCore import (
        QObject,
        QRunnable,
        Qt,
        QThreadPool,
        QProcess,
        QProcessEnvironment,
        Signal,
    )
    from PySide6.QtGui import QAction, QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QStackedWidget,
        QStatusBar,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
        QCheckBox,
    )

    PYSIDE6_AVAILABLE = True
    PYSIDE6_IMPORT_ERROR = ""
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    PYSIDE6_AVAILABLE = False
    PYSIDE6_IMPORT_ERROR = str(exc)


@dataclass
class CommandResult:
    ok: bool
    data: Any | None = None
    text: str = ""
    error: str = ""
    returncode: int = 0
    command: list[str] | None = None


def _build_mja_command(subargs: list[str], *, json_mode: bool) -> list[str]:
    args = [sys.executable, "-m", "mja", *subargs]
    if json_mode:
        args.append("--json")
    return args


def build_install_subargs(
    package_name: str,
    *,
    source: str = "auto",
    export: str = "auto",
    bin_name: str = "",
) -> list[str]:
    args = ["install", package_name, "--source", source, "--export", export]
    if bin_name.strip():
        args.extend(["--bin", bin_name.strip()])
    return args


def build_remove_subargs(package_name: str, *, unexport: bool = False) -> list[str]:
    args = ["remove", package_name]
    if unexport:
        args.append("--unexport")
    return args


def build_repair_export_subargs(
    package_name: str,
    *,
    mode: str = "auto",
    bin_name: str = "",
) -> list[str]:
    args = ["repair", "export", package_name, "--mode", mode]
    if bin_name.strip():
        args.extend(["--bin", bin_name.strip()])
    return args


def build_update_subargs(scope: str) -> list[str]:
    args = ["update"]
    if scope == "host":
        args.append("--host")
    elif scope == "container":
        args.append("--container")
    elif scope == "all":
        args.append("--all")
    return args


def _parse_completed_process(
    proc: subprocess.CompletedProcess[str], *, parse_json: bool
) -> CommandResult:
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()

    if proc.returncode != 0:
        return CommandResult(
            ok=False,
            text=combined,
            error=combined or f"Command failed with exit code {proc.returncode}",
            returncode=proc.returncode,
        )

    if parse_json:
        try:
            payload = json.loads(stdout) if stdout else None
        except json.JSONDecodeError as exc:
            return CommandResult(
                ok=False,
                text=stdout,
                error=f"JSON parse failed: {exc}",
                returncode=proc.returncode,
            )
        return CommandResult(ok=True, data=payload, text=stdout, returncode=proc.returncode)

    return CommandResult(ok=True, text=combined, returncode=proc.returncode)


def run_mja_command(
    subargs: list[str], *, json_mode: bool = False, cwd: str | None = None
) -> CommandResult:
    args = _build_mja_command(subargs, json_mode=json_mode)
    try:
        proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    except Exception as exc:  # pragma: no cover
        return CommandResult(ok=False, error=str(exc), returncode=1, command=args)

    result = _parse_completed_process(proc, parse_json=json_mode)
    result.command = args
    return result


def read_os_release() -> tuple[str, str]:
    os_id = ""
    os_pretty = tr("未知 Linux")
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ID="):
                    os_id = line.split("=", 1)[1].strip('"')
                elif line.startswith("PRETTY_NAME="):
                    os_pretty = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return os_id, os_pretty


def classify_environment(checks: list[dict[str, Any]]) -> tuple[str, str]:
    if not checks:
        return ("info", tr("尚未获取环境信息。"))

    os_id, os_pretty = read_os_release()
    checks_by_name = {check.get("name", ""): check for check in checks}
    pacman_ok = checks_by_name.get("pacman", {}).get("ok")
    pamac_ok = checks_by_name.get("pamac", {}).get("ok")
    distrobox_ok = checks_by_name.get("distrobox", {}).get("ok")
    runtime_ok = checks_by_name.get("container-runtime", {}).get("ok")

    if os_id == "manjaro":
        if pamac_ok is False:
            return (
                "warning",
                tr("系统检测为 {os_pretty}，但 pamac 不可用。mja 的 Manjaro 主路径可能不完整。").format(os_pretty=os_pretty),
            )
        if distrobox_ok is False and runtime_ok is False:
            return (
                "info",
                tr("系统检测为 {os_pretty}，基础路径可用，但容器工具链尚未配置。").format(os_pretty=os_pretty),
            )
        return ("ok", tr("系统检测为 {os_pretty}，环境检查通过。").format(os_pretty=os_pretty))

    if os_id:
        detail = tr("当前系统检测为 {os_pretty}。mja 主要为 Manjaro 设计，在该系统上属于非官方支持环境。").format(os_pretty=os_pretty)
        if distrobox_ok is False and runtime_ok is False:
            detail += tr(" 同时容器工具链也未配置。")
        return ("warning", detail)

    if pacman_ok and pamac_ok is False:
        return (
            "warning",
            tr("系统身份未识别，但当前环境缺少 pamac，看起来更像 Arch 或其他非 Manjaro 系统。"),
        )

    if distrobox_ok is False and runtime_ok is False:
        return ("info", tr("系统身份未识别，且容器工具链尚未配置。"))

    return ("info", tr("系统身份未识别，但基础检查已完成。"))


def group_doctor_checks(checks: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {
        "基础环境": [],
        "容器支持": [],
        "导出与记录": [],
        "其他": [],
    }

    for check in checks:
        name = check.get("name", "")
        if name in {"python", "pacman", "pamac", "distrobox", "container-runtime"}:
            groups["基础环境"].append(check)
        elif name.startswith("container-") or name.startswith("record-container-"):
            groups["容器支持"].append(check)
        elif name.startswith("export-") or name.startswith("state_") or name in {"state_dir", "state_file"}:
            groups["导出与记录"].append(check)
        else:
            groups["其他"].append(check)

    lines: list[str] = []
    for title, items in groups.items():
        if not items:
            continue
        lines.append(f"=== {title} ===")
        for check in items:
            state = "OK" if check.get("ok") else "FAIL"
            if check.get("skipped"):
                state = "SKIPPED"
            lines.append(f"[{state}] {check.get('name')}: {check.get('detail')}")
        lines.append("")

    return "\n".join(lines).strip()


def parse_numbered_options(text: str) -> list[str]:
    matches = list(re.finditer(r"(\d+)\)\s*", text))
    if not matches:
        return []

    options: list[str] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        option = text[start:end].strip()
        option = option.strip(",:; ")
        option = re.sub(r"\s+", " ", option)
        if option:
            options.append(option)
    return options


def detect_interaction_prompt(text: str) -> dict[str, Any] | None:
    if re.search(r"(?im)^\s*\[sudo\]\s*password\s+for\s+.+?:\s*$", text):
        return {
            "type": "password",
            "title": tr("需要提权"),
            "message": tr("执行此操作需要管理员权限（sudo），请输入密码："),
        }

    if re.search(r"(?im)^\s*Password:\s*$", text):
        return {
            "type": "password",
            "title": tr("需要认证"),
            "message": tr("后台任务正在请求密码，请输入密码："),
        }

    if re.search(r"(?im)^\s*密码[:：]\s*$", text):
        return {
            "type": "password",
            "title": tr("需要认证"),
            "message": tr("后台任务正在请求密码，请输入密码："),
        }

    if "providers available for" in text or "个提供者" in text:
        provider_match = re.search(
            r"(?:There are\s+\d+\s+providers available for\s+|软件库\s+)(\S+?)(?:[\s:：]|$)",
            text,
        )
        package_name = provider_match.group(1).strip() if provider_match else "未知包"
        options = parse_numbered_options(text)
        if options:
            return {
                "type": "provider_select",
                "title": f"{tr('为')} {package_name} {tr('选择提供者')}",
                "message": tr("检测到多个可选提供者，请选择要安装的条目。"),
                "options": options,
            }

    if re.search(r"\[Y/n\]", text, re.IGNORECASE):
        return {
            "type": "yes_no",
            "title": tr("需要确认"),
            "message": tr("检测到后台任务需要确认（Y/n）。是否继续？"),
            "yes": tr("继续"),
            "no": tr("取消"),
        }

    return None


def summarize_success(operation: str, target: str = "", extra: str = "") -> str:
    mapping = {
        "install": f"{tr('安装完成：')}{target}",
        "remove": f"{tr('卸载完成：')}{target}",
        "repair": f"{tr('导出修复完成：')}{target}",
        "update": f"{tr('更新完成：')}{target or extra}",
        "rebuild": tr("状态重建完成"),
    }
    base = mapping.get(operation, tr("命令执行完成"))
    return base + "\n\n" + tr("界面已自动刷新。")


def summarize_failure(operation: str, text: str, target: str = "") -> str:
    lower = text.lower()

    if "404" in lower and "failed retrieving file" in lower:
        return (
            f"{target or '当前任务'} 失败：下载依赖时镜像返回 404。\n\n"
            "这通常是镜像同步或容器内包数据库问题，可稍后重试，或先执行 update --container。"
        )

    if "failed to retrieve some files" in lower:
        return (
            f"{target or '当前任务'} 失败：部分依赖文件无法获取。\n\n"
            "请检查网络、镜像状态，或先更新容器内数据库。"
        )

    if "container_not_found" in lower or "container not found" in lower:
        return (
            f"{target or '当前任务'} 失败：目标容器不存在。\n\n"
            "请先检查 mja-arch 容器是否存在。"
        )

    if "paru_not_ready" in lower:
        return (
            f"{target or '当前任务'} 失败：容器内 paru 不可用。\n\n"
            "请先修复容器环境。"
        )

    if "not_installed" in lower or "package not recorded" in lower:
        return f"{target or '该包'} 当前不在可操作记录中。"

    if operation == "update":
        return tr("更新失败。请查看详细输出，确认是镜像、认证还是容器环境问题。")

    if operation == "install":
        return f"{tr('安装失败：')}{target or tr('目标包')} {tr('未能成功安装。请查看详细输出。')}"

    if operation == "remove":
        return f"{tr('卸载失败：')}{target or tr('目标包')} {tr('未能成功移除。请查看详细输出。')}"

    if operation == "repair":
        return f"{tr('导出修复失败：')}{target or tr('目标包')} {tr('未能成功修复。请查看详细输出。')}"

    if operation == "rebuild":
        return "状态重建失败。请查看详细输出。"

    return "命令执行失败。请查看详细输出。"


def filter_installed_rows(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """Filter installed rows based on the selected mode.

    The installed page allows users to choose between showing only installed
    packages or all recorded entries.  The UI presents this choice via a
    combo box containing a translated label for "仅已安装"/"Installed only"
    (index 0) and "全部记录"/"All records" (index 1).  Rather than
    matching on the literal text (which changes with language), we test
    against the translated strings using the lightweight `tr()` helper.

    Args:
        rows: The list of all package records.
        mode: The current text of the filter combo box.

    Returns:
        A filtered list containing only installed packages when the
        user selects the "仅已安装" option, otherwise the full list.
    """
    # When the mode equals the translated "仅已安装" label, return only installed rows
    if mode == tr("仅已安装"):
        return [row for row in rows if row.get("install_status") == "installed"]
    # For any other value (including translated "全部记录"), return all rows
    return rows


def trim_prompt_buffer(current: str, incoming: str, *, max_len: int = 4096) -> str:
    merged = current + incoming
    if len(merged) <= max_len:
        return merged
    return merged[-max_len:]


class FallbackConsoleApp:
    def __init__(self) -> None:
        self.log_path = Path.home() / ".local/state/mja/logs/latest.log"

    def run(self) -> int:
        print(f"{APP_TITLE} {APP_VERSION}")
        print(tr("PySide6 不可用，无法启动桌面界面。"))
        print(f"{tr('导入错误：')}{PYSIDE6_IMPORT_ERROR}")
        print()
        print(tr("你可以做的事："))
        print(tr("1. 安装 PySide6 后重新运行这个脚本"))
        print(tr("2. 继续直接使用 CLI：python -m mja --help"))
        print(tr("3. 先查看当前环境和状态摘要"))
        print()

        doctor = run_mja_command(["doctor"], json_mode=True)
        if doctor.ok and isinstance(doctor.data, dict):
            self._print_doctor_summary(doctor.data)
        else:
            print(tr("doctor 摘要不可用。"))
            if doctor.error:
                print(doctor.error)

        latest_log = self._read_latest_log()
        if latest_log:
            print()
            print(tr("最近日志（末尾）："))
            print("-" * 60)
            print(latest_log)
            print("-" * 60)
        return 0

    def _print_doctor_summary(self, payload: dict[str, Any]) -> None:
        print(f"{tr('doctor 总状态：')}{tr('健康') if payload.get('ok') else tr('有问题')}")
        for check in payload.get("checks", []):
            state = "OK" if check.get("ok") else "FAIL"
            if check.get("skipped"):
                state = "SKIPPED"
            print(f"[{state}] {check.get('name')}: {check.get('detail')}")

    def _read_latest_log(self) -> str:
        if not self.log_path.exists():
            return ""
        text = self.log_path.read_text(encoding="utf-8", errors="replace").strip()
        lines = text.splitlines()
        return "\n".join(lines[-12:])


if PYSIDE6_AVAILABLE:

    class WorkerSignals(QObject):
        finished = Signal(object)
        failed = Signal(str)
        log = Signal(str)


    class CommandWorker(QRunnable):
        def __init__(
            self,
            args: list[str],
            *,
            parse_json: bool = False,
            cwd: str | None = None,
        ) -> None:
            super().__init__()
            self.args = args
            self.parse_json = parse_json
            self.cwd = cwd
            self.signals = WorkerSignals()

        def run(self) -> None:
            self.signals.log.emit(f"$ {' '.join(self.args)}")
            try:
                proc = subprocess.run(
                    self.args,
                    capture_output=True,
                    text=True,
                    cwd=self.cwd,
                )
            except Exception as exc:  # pragma: no cover
                self.signals.failed.emit(str(exc))
                return

            result = _parse_completed_process(proc, parse_json=self.parse_json)
            result.command = self.args
            if not result.ok:
                self.signals.failed.emit(result.error or "命令失败")
                return
            self.signals.finished.emit(result)


    class MjaClient(QObject):
        command_started = Signal(str)
        command_log = Signal(str)
        command_failed = Signal(str)

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self.pool = QThreadPool.globalInstance()
            self.python_exe = sys.executable

        def run_json(self, subargs: list[str], on_success: Callable[[CommandResult], None]) -> None:
            args = _build_mja_command(subargs, json_mode=True)
            self.command_started.emit(" ".join(args))
            worker = CommandWorker(args, parse_json=True)
            worker.signals.log.connect(self.command_log)
            worker.signals.failed.connect(self.command_failed)
            worker.signals.finished.connect(on_success)
            self.pool.start(worker)

        def run_text(self, subargs: list[str], on_success: Callable[[CommandResult], None]) -> None:
            args = _build_mja_command(subargs, json_mode=False)
            self.command_started.emit(" ".join(args))
            worker = CommandWorker(args, parse_json=False)
            worker.signals.log.connect(self.command_log)
            worker.signals.failed.connect(self.command_failed)
            worker.signals.finished.connect(on_success)
            self.pool.start(worker)


    class ResultDialog(QDialog):
        def __init__(
            self,
            title: str,
            summary: str,
            details: str,
            *,
            success: bool,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setModal(True)
            self.resize(760, 260 if success else 560)

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            title_label = QLabel(title)
            title_label.setObjectName("DialogTitle")
            root.addWidget(title_label)

            self.summary_label = QLabel(summary)
            self.summary_label.setWordWrap(True)
            self.summary_label.setObjectName("InfoBanner")
            self.summary_label.setProperty("level", "ok" if success else "warning")
            root.addWidget(self.summary_label)

            self.toggle_btn = QPushButton(tr("查看详细输出"))
            self.toggle_btn.clicked.connect(self._toggle_details)
            root.addWidget(self.toggle_btn)

            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.setPlainText(details)
            self.output.setVisible(not success)
            root.addWidget(self.output, 1)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            buttons.accepted.connect(self.accept)
            root.addWidget(buttons)

        def _toggle_details(self) -> None:
            visible = not self.output.isVisible()
            self.output.setVisible(visible)
            self.toggle_btn.setText(tr("隐藏详细输出") if visible else tr("查看详细输出"))
            if visible:
                self.resize(max(self.width(), 760), max(self.height(), 560))
            else:
                self.resize(max(self.width(), 760), 260)


    def show_result_dialog(
        parent: QWidget,
        title: str,
        summary: str,
        details: str,
        *,
        success: bool,
    ) -> None:
        dialog = ResultDialog(title, summary, details, success=success, parent=parent)
        dialog.exec()


    class ConfirmDialog(QDialog):
        def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setModal(True)
            self.resize(440, 180)

            root = QVBoxLayout(self)
            text = QLabel(message)
            text.setWordWrap(True)
            root.addWidget(text)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
            )
            buttons.button(QDialogButtonBox.StandardButton.Yes).setText(tr("确认"))
            buttons.button(QDialogButtonBox.StandardButton.No).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)


    class ProviderChoiceDialog(QDialog):
        def __init__(self, title: str, message: str, options: list[str], parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setModal(True)
            self.resize(520, 260)

            root = QVBoxLayout(self)
            label = QLabel(message)
            label.setWordWrap(True)
            root.addWidget(label)

            self.combo = QComboBox()
            self.combo.addItems(options)
            root.addWidget(self.combo)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("确认选择"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def selected_index(self) -> int:
            return self.combo.currentIndex() + 1


    class TaskDialog(QDialog):
        ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        def __init__(
            self,
            title: str,
            subargs: list[str],
            *,
            operation: str,
            target: str = "",
            extra: str = "",
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setModal(True)
            self.resize(900, 650)
            self.subargs = subargs
            self.operation = operation
            self.target = target
            self.extra = extra

            self.result_ok = False
            self.result_text = ""
            self.result_code: int | None = None
            self._buffer = ""
            self._running = True
            self._interaction_active = False
            # Track whether the user explicitly cancelled this task via prompts.
            self.user_cancelled: bool = False

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(12)

            self.summary = QLabel(tr("正在初始化任务……"))
            self.summary.setWordWrap(True)
            self.summary.setObjectName("InfoBanner")
            self.summary.setProperty("level", "info")
            root.addWidget(self.summary)

            # Optional waiting hint label.  For long-running tasks such as
            # installation or updates this label advises the user that the
            # operation may take a while.  It is hidden for non-transactional
            # commands (e.g. search or doctor).
            self.wait_label = QLabel(get_wait_message(self.operation))
            self.wait_label.setWordWrap(True)
            # Show the wait hint only for selected operations
            if operation in {"install", "update", "remove", "repair", "rebuild"}:
                self.wait_label.setVisible(True)
            else:
                self.wait_label.setVisible(False)
            root.addWidget(self.wait_label)

            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.document().setMaximumBlockCount(5000)
            root.addWidget(self.output, 1)

            buttons = QHBoxLayout()
            self.close_btn = QPushButton(tr("强制关闭"))
            self.close_btn.clicked.connect(self._handle_close_clicked)
            buttons.addStretch(1)
            buttons.addWidget(self.close_btn)
            root.addLayout(buttons)

            self.proc = QProcess(self)
            env = QProcessEnvironment.systemEnvironment()
            env.insert("LANG", "C")
            env.insert("LC_ALL", "C")
            env.insert("LANGUAGE", "C")

            has_script = shutil.which("script") is not None
            original_cmd = [sys.executable, "-m", "mja", *subargs]

            if has_script:
                cmd_str = " ".join(shlex.quote(arg) for arg in original_cmd)
                self.proc.setProgram("script")
                self.proc.setArguments(["-qefc", cmd_str, "/dev/null"])
                self.summary.setText(tr("正在执行任务（PTY 模式开启）……"))
            else:
                env.insert("PYTHONUNBUFFERED", "1")
                self.proc.setProgram(sys.executable)
                self.proc.setArguments(["-m", "mja", *subargs])
                self.summary.setText(tr("正在执行任务（未检测到 script，输出可能延迟）……"))

            self.proc.setProcessEnvironment(env)
            self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            self.proc.readyReadStandardOutput.connect(self._read_output)
            self.proc.finished.connect(self._finished)
            self.proc.start()

        def _append_plain(self, text: str) -> None:
            if not text:
                return
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.insertPlainText(text)
            self.output.moveCursor(QTextCursor.MoveOperation.End)

        def _overwrite_current_line(self, text: str) -> None:
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            cursor.insertText(text)
            self.output.setTextCursor(cursor)

        def _read_output(self) -> None:
            raw_data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            if not raw_data:
                return

            clean_data = self.ANSI_ESCAPE_RE.sub("", raw_data).replace("\r\n", "\n")
            parts = clean_data.split("\r")

            for index, part in enumerate(parts):
                if index == 0:
                    self._append_plain(part)
                else:
                    if part == "":  # 🌟 修复点：精确拦截纯空字符串，防止擦除现有进度条
                        continue
                    self._overwrite_current_line(part)

            prompt_source = clean_data.replace("\r", "")
            self._buffer = trim_prompt_buffer(self._buffer, prompt_source, max_len=4096)
            self._maybe_handle_interaction()

        def _maybe_handle_interaction(self) -> None:
            # Skip interaction handling if user has already cancelled the task.
            if self._interaction_active or self.user_cancelled:
                return

            prompt = detect_interaction_prompt(self._buffer)
            if not prompt:
                return

            self._interaction_active = True
            try:
                # Password prompt: ask the user for a password via an input dialog.
                if prompt["type"] == "password":
                    text, ok = QInputDialog.getText(
                        self,
                        prompt["title"],
                        prompt["message"],
                        QLineEdit.EchoMode.Password,
                    )
                    if ok and text:
                        # Forward the password to the subprocess
                        self.proc.write((text + "\n").encode())
                        self.summary.setText(tr("已提交密码，请稍候……"))
                    else:
                        # User cancelled password entry – terminate the process and mark as cancelled
                        self.user_cancelled = True
                        self.proc.kill()
                        self.summary.setText(tr("已取消，正在结束任务……"))
                    self._buffer = ""
                    return

                # Provider selection prompt: present options via a combo box dialog
                if prompt["type"] == "provider_select":
                    dialog = ProviderChoiceDialog(prompt["title"], prompt["message"], prompt["options"], self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        # Send the selected provider index (1-based) to the process
                        self.proc.write(f"{dialog.selected_index()}\n".encode())
                        self.summary.setText(tr("已选择提供者，继续执行任务……"))
                    else:
                        # User cancelled provider selection – terminate the process and mark as cancelled
                        self.user_cancelled = True
                        self.proc.kill()
                        self.summary.setText(tr("已取消，正在结束任务……"))
                    self._buffer = ""
                    return

                # Yes/no prompt: ask the user to continue
                if prompt["type"] == "yes_no":
                    dialog = ConfirmDialog(prompt["title"], prompt["message"], self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        # User chose to continue
                        self.proc.write(b"Y\n")
                        self.summary.setText(tr("已确认，继续执行任务……"))
                    else:
                        # User chose not to continue – send 'n' and mark as cancelled
                        self.proc.write(b"n\n")
                        self.user_cancelled = True
                        self.summary.setText(tr("已取消，正在结束任务……"))
                    self._buffer = ""
                    return
            finally:
                self._interaction_active = False

        def _finished(self, exit_code: int, _exit_status) -> None:
            self._running = False
            self.result_code = exit_code
            self.result_text = self.output.toPlainText().strip()
            self.result_ok = exit_code == 0

            # If the user explicitly cancelled the task via an interaction prompt,
            # display a neutral cancellation message instead of success or failure.
            if self.user_cancelled:
                # Consider cancelled tasks as non-failures for styling purposes
                self.summary.setProperty("level", "warning")
                self.summary.style().unpolish(self.summary)
                self.summary.style().polish(self.summary)
                self.summary.update()
                self.summary.setText(tr("任务已取消"))
                self.close_btn.setText(tr("关闭窗口"))
                return

            # Otherwise compute success or failure summary based on the process exit code
            summary = (
                summarize_success(self.operation, self.target, self.extra)
                if self.result_ok
                else summarize_failure(self.operation, self.result_text, self.target)
            )

            self.summary.setProperty("level", "ok" if self.result_ok else "warning")
            self.summary.style().unpolish(self.summary)
            self.summary.style().polish(self.summary)
            self.summary.update()
            self.summary.setText(summary)
            self.close_btn.setText(tr("关闭窗口"))

        def _confirm_interrupt(self) -> bool:
            dialog = ConfirmDialog(
                APP_TITLE,
                "任务仍在运行。要终止当前任务并关闭窗口吗？",
                self,
            )
            return dialog.exec() == QDialog.DialogCode.Accepted

        def _handle_close_clicked(self) -> None:
            if self._running:
                if self._confirm_interrupt():
                    self.proc.kill()
                    self.reject()
                return
            self.accept()

        def closeEvent(self, event) -> None:  # type: ignore[override]
            if self._running:
                if self._confirm_interrupt():
                    self.proc.kill()
                    event.accept()
                else:
                    event.ignore()
                return
            event.accept()


    class InstallDialog(QDialog):
        def __init__(self, package_name: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"{tr('安装')} {package_name}")
            self.package_name = package_name
            self.setModal(True)
            self.resize(440, 200)

            root = QVBoxLayout(self)
            form = QFormLayout()

            self.package_label = QLabel(package_name)
            self.source_combo = QComboBox()
            self.source_combo.addItems(["auto", "repo", "aur"])
            self.export_combo = QComboBox()
            self.export_combo.addItems(["auto", "desktop", "bin", "none"])
            self.bin_edit = QLineEdit()
            self.bin_edit.setPlaceholderText(tr("可选：指定 bin 名称，仅 export=bin 时常用"))

            form.addRow(tr("包名"), self.package_label)
            form.addRow(tr("来源"), self.source_combo)
            form.addRow(tr("导出模式"), self.export_combo)
            form.addRow(tr("bin 名称"), self.bin_edit)
            root.addLayout(form)

            # Optional checkbox to create a desktop shortcut after successful installation
            self.shortcut_checkbox = QCheckBox(tr("安装成功后创建桌面快捷方式"))
            self.shortcut_checkbox.setChecked(False)
            root.addWidget(self.shortcut_checkbox)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("开始安装"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def get_values(self) -> tuple[str, str, str]:
            return (
                self.source_combo.currentText(),
                self.export_combo.currentText(),
                self.bin_edit.text().strip(),
            )

        def should_create_shortcut(self) -> bool:
            """Return whether the desktop shortcut checkbox is checked."""
            return self.shortcut_checkbox.isChecked()


    class RemoveDialog(QDialog):
        def __init__(self, package_name: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"{tr('卸载')} {package_name}")
            self.setModal(True)
            self.resize(420, 170)

            root = QVBoxLayout(self)
            form = QFormLayout()
            self.package_label = QLabel(package_name)
            self.unexport_combo = QComboBox()
            self.unexport_combo.addItems([tr("否"), tr("是")])
            form.addRow(tr("包名"), self.package_label)
            form.addRow(tr("同时 unexport"), self.unexport_combo)
            root.addLayout(form)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("开始卸载"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def should_unexport(self) -> bool:
            """Return whether the user requested to unexport at removal.

            The combo box always contains two options corresponding to
            "否"/"是" (No/Yes) in the current UI language.  Rely on the
            selected index rather than the translated text to determine
            whether unexporting should occur.  This avoids brittle
            comparisons against specific language strings and ensures
            consistent behaviour when the interface language changes.

            Returns:
                True if the second option (Yes) is selected, otherwise False.
            """
            # Index 0 corresponds to "否" (No), index 1 corresponds to "是" (Yes)
            return self.unexport_combo.currentIndex() == 1


    class RepairExportDialog(QDialog):
        def __init__(self, package_name: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(f"{tr('修复导出')} {package_name}")
            self.setModal(True)
            self.resize(420, 190)

            root = QVBoxLayout(self)
            form = QFormLayout()
            self.package_label = QLabel(package_name)
            self.mode_combo = QComboBox()
            self.mode_combo.addItems(["auto", "desktop", "bin"])
            self.bin_edit = QLineEdit()
            self.bin_edit.setPlaceholderText(tr("可选：仅 mode=bin 时常用"))
            form.addRow(tr("包名"), self.package_label)
            form.addRow(tr("修复模式"), self.mode_combo)
            form.addRow(tr("bin 名称"), self.bin_edit)
            root.addLayout(form)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("开始修复"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def get_values(self) -> tuple[str, str]:
            return self.mode_combo.currentText(), self.bin_edit.text().strip()


    class UpdateDialog(QDialog):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setWindowTitle(tr("更新包"))
            self.setModal(True)
            self.resize(420, 150)

            root = QVBoxLayout(self)
            form = QFormLayout()
            self.scope_combo = QComboBox()
            self.scope_combo.addItems(["all", "host", "container"])
            form.addRow(tr("更新范围"), self.scope_combo)
            root.addLayout(form)

            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("开始更新"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

        def get_scope(self) -> str:
            return self.scope_combo.currentText()


    class StatCard(QFrame):
        def __init__(self, title: str, value: str = "-", parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setFrameShape(QFrame.Shape.StyledPanel)
            self.setObjectName("StatCard")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(6)

            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.value_label = QLabel(value)
            self.value_label.setObjectName("CardValue")

            layout.addWidget(self.title_label)
            layout.addWidget(self.value_label)
            layout.addStretch(1)

        def set_value(self, value: str) -> None:
            self.value_label.setText(value)


    class DashboardPage(QWidget):
        def __init__(self, client: MjaClient, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.client = client

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(16)

            header = QHBoxLayout()
            self.title_label = QLabel(tr("仪表盘"))
            self.title_label.setObjectName("PageTitle")
            self.refresh_btn = QPushButton(tr("运行 doctor"))
            self.refresh_btn.clicked.connect(self.refresh)
            header.addWidget(self.title_label)
            header.addStretch(1)
            header.addWidget(self.refresh_btn)
            root.addLayout(header)

            self.banner = QLabel(tr("尚未获取环境信息。"))
            self.banner.setObjectName("InfoBanner")
            self.banner.setProperty("level", "info")
            self.banner.setWordWrap(True)
            root.addWidget(self.banner)

            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(12)

            self.card_doctor = StatCard(tr("Doctor 状态"))
            self.card_state = StatCard(tr("State 文件"))
            self.card_env = StatCard(tr("环境判断"))
            self.card_exports = StatCard(tr("导出异常"))

            grid.addWidget(self.card_doctor, 0, 0)
            grid.addWidget(self.card_state, 0, 1)
            grid.addWidget(self.card_env, 1, 0)
            grid.addWidget(self.card_exports, 1, 1)
            root.addLayout(grid)

            self.summary = QPlainTextEdit()
            self.summary.setReadOnly(True)
            self.summary.setPlaceholderText(tr("这里会显示 doctor 的摘要。"))
            root.addWidget(self.summary, 1)

        def refresh(self) -> None:
            self.refresh_btn.setEnabled(False)
            self.summary.setPlainText(tr("正在检查环境……"))
            self.banner.setText(tr("正在读取 doctor 结果……"))
            self.client.run_json(["doctor"], self._handle_doctor)

        def _handle_doctor(self, result: CommandResult) -> None:
            self.refresh_btn.setEnabled(True)
            payload = result.data or {}
            checks = payload.get("checks", [])
            ok = payload.get("ok", False)

            env_level, env_text = classify_environment(checks)
            export_errors = [
                c for c in checks if c.get("name", "").startswith("export-") and not c.get("ok", False)
            ]

            self.card_doctor.set_value(tr("健康") if ok else tr("有问题"))
            self.card_state.set_value(payload.get("state_file", {}).get("status", "unknown"))
            self.card_env.set_value(
                {
                    "ok": "完全支持",
                    "warning": "非官方支持",
                    "info": "部分未配置",
                }.get(env_level, tr("未知"))
            )
            self.card_exports.set_value(str(len(export_errors)))

            self.banner.setText(env_text)
            self.banner.setProperty("level", env_level)
            self.banner.style().unpolish(self.banner)
            self.banner.style().polish(self.banner)
            self.banner.update()

            self.summary.setPlainText(group_doctor_checks(checks))

        def update_language(self) -> None:
            self.title_label.setText(tr("仪表盘"))
            self.refresh_btn.setText(tr("运行 doctor"))
            self.summary.setPlaceholderText(tr("这里会显示 doctor 的摘要。"))
            self.card_doctor.title_label.setText(tr("Doctor 状态"))
            self.card_state.title_label.setText(tr("State 文件"))
            self.card_env.title_label.setText(tr("环境判断"))
            self.card_exports.title_label.setText(tr("导出异常"))


    class SearchPage(QWidget):
        def __init__(self, client: MjaClient, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.client = client
            self.rows: list[dict[str, Any]] = []

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(16)

            self.title_label = QLabel(tr("搜索"))
            self.title_label.setObjectName("PageTitle")
            root.addWidget(self.title_label)

            controls = QHBoxLayout()
            self.query = QLineEdit()
            self.query.setPlaceholderText(tr("输入包名，例如 google-chrome / nitch / vlc"))
            self.scope = QComboBox()
            self.scope.addItems([tr("全部"), tr("仅 repo"), tr("仅 AUR")])
            self.search_btn = QPushButton(tr("搜索"))
            self.search_btn.clicked.connect(self.search)
            controls.addWidget(self.query, 1)
            controls.addWidget(self.scope)
            controls.addWidget(self.search_btn)
            root.addLayout(controls)

            action_bar = QHBoxLayout()
            self.selected_label = QLabel(tr("当前未选择包"))
            self.install_btn = QPushButton(tr("安装选中包"))
            self.install_btn.setEnabled(False)
            self.install_btn.clicked.connect(self.install_selected)
            action_bar.addWidget(self.selected_label)
            action_bar.addStretch(1)
            action_bar.addWidget(self.install_btn)
            root.addLayout(action_bar)

            self.table = QTableWidget(0, 6)
            # Set translated header labels
            self.table.setHorizontalHeaderLabels([
                tr("来源"),
                tr("名称"),
                tr("版本"),
                tr("精确匹配"),
                tr("描述"),
                tr("热度/票数"),
            ])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.table.setAlternatingRowColors(True)
            self.table.itemSelectionChanged.connect(self._update_selection_state)
            root.addWidget(self.table, 1)

        def search(self) -> None:
            query = self.query.text().strip()
            if not query:
                QMessageBox.information(self, APP_TITLE, tr("先输入要搜索的包名。"))
                return

            args = ["search", query]
            # Determine scope based on the current (translated) text
            scope_text = self.scope.currentText()
            if scope_text == tr("仅 repo"):
                args.append("--repo")
            elif scope_text == tr("仅 AUR"):
                args.append("--aur")

            self.search_btn.setEnabled(False)
            self.client.run_json(args, self._handle_search)

        def _handle_search(self, result: CommandResult) -> None:
            self.search_btn.setEnabled(True)
            payload = result.data or {"repo": [], "aur": []}
            self.rows = sort_search_dicts([*payload.get("repo", []), *payload.get("aur", [])], self.query.text().strip())

            selected_name = None
            if current := self._selected_row():
                selected_name = current.get("name")
            v_scroll = self.table.verticalScrollBar().value()

            self.table.setUpdatesEnabled(False)
            self.table.clearContents()
            self.table.setRowCount(len(self.rows))

            row_to_select = -1
            for row_index, item in enumerate(self.rows):
                name = item.get("name", "")
                if name == selected_name:
                    row_to_select = row_index

                popularity = item.get("popularity")
                votes = item.get("votes")
                # Use human-friendly formatting for popularity and votes
                popularity_text = "-"
                if popularity is not None or votes is not None:
                    pop_str = "-" if popularity is None else format_popularity(popularity)
                    votes_str = "-" if votes is None else str(votes)
                    popularity_text = f"{pop_str} / {votes_str}"

                values = [
                    item.get("source", ""),
                    name,
                    item.get("version", ""),
                    tr("是") if item.get("exact") else tr("否"),
                    item.get("description", ""),
                    popularity_text,
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row_index, col, QTableWidgetItem(str(value)))

            if row_to_select >= 0:
                self.table.selectRow(row_to_select)
            self.table.verticalScrollBar().setValue(v_scroll)
            self.table.setUpdatesEnabled(True)
            self._update_selection_state()

        def _selected_row(self) -> dict[str, Any] | None:
            selected = self.table.selectionModel().selectedRows()
            if not selected:
                return None
            row_index = selected[0].row()
            if row_index < 0 or row_index >= len(self.rows):
                return None
            return self.rows[row_index]

        def _update_selection_state(self) -> None:
            item = self._selected_row()
            if not item:
                # Update label to reflect that no package is selected
                self.selected_label.setText(tr("当前未选择包"))
                self.install_btn.setEnabled(False)
                return
            # Show which package is currently selected
            self.selected_label.setText(f"{tr('当前选择：')}{item.get('name', '-')}")
            self.install_btn.setEnabled(True)

        def install_selected(self) -> None:
            item = self._selected_row()
            if not item:
                QMessageBox.information(self, APP_TITLE, tr("先选中一个包。"))
                return

            dialog = InstallDialog(item.get("name", ""), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            source, export, bin_name = dialog.get_values()
            # Determine whether to create a desktop shortcut after successful installation
            create_shortcut = False
            if hasattr(dialog, "should_create_shortcut"):
                create_shortcut = dialog.should_create_shortcut()

            args = build_install_subargs(
                item.get("name", ""),
                source=source,
                export=export,
                bin_name=bin_name,
            )
            task = TaskDialog(
                f"{tr('安装')} {item.get('name', '')}",
                args,
                operation="install",
                target=item.get("name", ""),
                parent=self,
            )
            task.exec()
            # After the task completes, refresh UI and optionally handle desktop shortcut
            main_window = self.window()
            if hasattr(main_window, "refresh_everything"):
                main_window.refresh_everything()
            # If installation succeeded and the user requested a desktop shortcut, attempt to copy
            if task.result_ok and create_shortcut:
                name = item.get("name", "")
                if copy_desktop_shortcut(name):
                    QMessageBox.information(self, APP_TITLE, tr("桌面快捷方式已创建"))
                else:
                    QMessageBox.information(self, APP_TITLE, tr("软件已安装，但未找到可用于创建桌面快捷方式的 desktop 文件。"))

        def update_language(self) -> None:
            """Refresh all user-visible text according to the current language.

            This method should be called when the global language changes to
            update labels, placeholders and table headers.  It does not
            re-execute searches; however, the match column values ("是"/"否")
            will be translated when the table is rebuilt on the next search.
            """
            # Update the title
            self.title_label.setText(tr("搜索"))
            # Update placeholders and combo box items
            self.query.setPlaceholderText(tr("输入包名，例如 google-chrome / nitch / vlc"))
            # Update scope selection values while preserving current index
            current_index = self.scope.currentIndex()
            self.scope.clear()
            self.scope.addItems([tr("全部"), tr("仅 repo"), tr("仅 AUR")])
            self.scope.setCurrentIndex(current_index)
            # Update search button text
            self.search_btn.setText(tr("搜索"))
            # Update selected label based on current selection
            self._update_selection_state()
            # Update install button text
            self.install_btn.setText(tr("安装选中包"))
            # Update table headers
            self.table.setHorizontalHeaderLabels([
                tr("来源"),
                tr("名称"),
                tr("版本"),
                tr("精确匹配"),
                tr("描述"),
                tr("热度/票数"),
            ])

            # Update the exact match column values for existing rows
            # When the language changes, the underlying boolean value for
            # "exact" does not change, but the displayed text should.
            # Iterate through stored search results and refresh the fourth
            # column to reflect the current language's Yes/No translation.
            for row_index, item in enumerate(self.rows):
                # Skip if the row does not exist in the table yet
                if row_index >= self.table.rowCount():
                    break
                col = 3  # index of the "精确匹配" column
                value = tr("是") if item.get("exact") else tr("否")
                cell_item = self.table.item(row_index, col)
                if cell_item is not None:
                    cell_item.setText(value)


    class InstalledPage(QWidget):
        def __init__(self, client: MjaClient, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.client = client
            self.all_rows: list[dict[str, Any]] = []
            self.rows: list[dict[str, Any]] = []

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(16)

            header = QHBoxLayout()
            self.title_label = QLabel(tr("已安装"))
            self.title_label.setObjectName("PageTitle")
            self.filter_combo = QComboBox()
            self.filter_combo.addItems([tr("仅已安装"), tr("全部记录")])
            self.filter_combo.currentTextChanged.connect(self._apply_filter)
            self.refresh_btn = QPushButton(tr("刷新"))
            self.refresh_btn.clicked.connect(self.refresh)
            self.update_btn = QPushButton(tr("更新"))
            self.update_btn.clicked.connect(self.run_update)
            header.addWidget(self.title_label)
            header.addStretch(1)
            self.show_label = QLabel(tr("显示"))
            header.addWidget(self.show_label)
            header.addWidget(self.filter_combo)
            header.addWidget(self.update_btn)
            header.addWidget(self.refresh_btn)
            root.addLayout(header)

            action_bar = QHBoxLayout()
            self.selected_label = QLabel(tr("当前未选择包"))
            self.remove_btn = QPushButton(tr("卸载"))
            self.remove_btn.setEnabled(False)
            self.remove_btn.clicked.connect(self.remove_selected)
            self.repair_btn = QPushButton(tr("修复导出"))
            self.repair_btn.setEnabled(False)
            self.repair_btn.clicked.connect(self.repair_selected)
            action_bar.addWidget(self.selected_label)
            action_bar.addStretch(1)
            action_bar.addWidget(self.repair_btn)
            action_bar.addWidget(self.remove_btn)
            root.addLayout(action_bar)

            self.table = QTableWidget(0, 6)
            self.table.setHorizontalHeaderLabels([tr("包名"), tr("来源"), tr("安装状态"), tr("导出状态"), tr("容器"), tr("安装时间")])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.table.setAlternatingRowColors(True)
            self.table.itemSelectionChanged.connect(self._update_selection_state)
            root.addWidget(self.table, 1)

        def refresh(self) -> None:
            self.refresh_btn.setEnabled(False)
            self.client.run_json(["list"], self._handle_list)

        def _handle_list(self, result: CommandResult) -> None:
            self.refresh_btn.setEnabled(True)
            self.all_rows = result.data or []
            self._apply_filter()

        def _apply_filter(self) -> None:
            selected_name = None
            if current := self._selected_row():
                selected_name = current.get("name")
            v_scroll = self.table.verticalScrollBar().value()

            self.table.setUpdatesEnabled(False)
            self.rows = filter_installed_rows(self.all_rows, self.filter_combo.currentText())
            self.table.clearContents()
            self.table.setRowCount(len(self.rows))

            row_to_select = -1
            for row_index, item in enumerate(self.rows):
                name = item.get("name", "")
                if name == selected_name:
                    row_to_select = row_index

                values = [
                    name,
                    item.get("source", ""),
                    item.get("install_status", ""),
                    item.get("export_status", ""),
                    item.get("container") or "-",
                    item.get("installed_at") or "-",
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row_index, col, QTableWidgetItem(str(value)))

            if row_to_select >= 0:
                self.table.selectRow(row_to_select)
            self.table.verticalScrollBar().setValue(v_scroll)
            self.table.setUpdatesEnabled(True)
            self._update_selection_state()

        def _selected_row(self) -> dict[str, Any] | None:
            selected = self.table.selectionModel().selectedRows()
            if not selected:
                return None
            row_index = selected[0].row()
            if row_index < 0 or row_index >= len(self.rows):
                return None
            return self.rows[row_index]

        def _update_selection_state(self) -> None:
            item = self._selected_row()
            if not item:
                self.selected_label.setText(tr("当前未选择包"))
                self.remove_btn.setEnabled(False)
                self.repair_btn.setEnabled(False)
                return
            self.selected_label.setText(f"{tr('当前选择：')}{item.get('name', '-')}")
            self.remove_btn.setEnabled(item.get("install_status") == "installed")
            self.repair_btn.setEnabled(
                item.get("source") == "aur-container" and item.get("install_status") == "installed"
            )

        def run_update(self) -> None:
            dialog = UpdateDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            scope = dialog.get_scope()
            args = build_update_subargs(scope)
            task = TaskDialog(
                tr("执行 update"),
                args,
                operation="update",
                target=scope,
                parent=self,
            )
            task.exec()
            main_window = self.window()
            if hasattr(main_window, "refresh_everything"):
                main_window.refresh_everything()

        def remove_selected(self) -> None:
            item = self._selected_row()
            if not item:
                return
            dialog = RemoveDialog(item.get("name", ""), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            args = build_remove_subargs(item.get("name", ""), unexport=dialog.should_unexport())
            task = TaskDialog(
                f"{tr('卸载')} {item.get('name', '')}",
                args,
                operation="remove",
                target=item.get("name", ""),
                parent=self,
            )
            task.exec()
            main_window = self.window()
            if hasattr(main_window, "refresh_everything"):
                main_window.refresh_everything()

        def repair_selected(self) -> None:
            item = self._selected_row()
            if not item:
                return
            dialog = RepairExportDialog(item.get("name", ""), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            mode, bin_name = dialog.get_values()
            args = build_repair_export_subargs(item.get("name", ""), mode=mode, bin_name=bin_name)
            task = TaskDialog(
                f"{tr('修复导出')} {item.get('name', '')}",
                args,
                operation="repair",
                target=item.get("name", ""),
                parent=self,
            )
            task.exec()
            main_window = self.window()
            if hasattr(main_window, "refresh_everything"):
                main_window.refresh_everything()

        def update_language(self) -> None:
            self.title_label.setText(tr("已安装"))
            current_index = self.filter_combo.currentIndex()
            self.filter_combo.blockSignals(True)
            self.filter_combo.clear()
            self.filter_combo.addItems([tr("仅已安装"), tr("全部记录")])
            self.filter_combo.setCurrentIndex(current_index)
            self.filter_combo.blockSignals(False)
            self.show_label.setText(tr("显示"))
            self.refresh_btn.setText(tr("刷新"))
            self.update_btn.setText(tr("更新"))
            self.remove_btn.setText(tr("卸载"))
            self.repair_btn.setText(tr("修复导出"))
            self._update_selection_state()
            self.table.setHorizontalHeaderLabels([tr("包名"), tr("来源"), tr("安装状态"), tr("导出状态"), tr("容器"), tr("安装时间")])


    class LogsPage(QWidget):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.log_path = Path.home() / ".local/state/mja/logs/latest.log"

            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(16)

            header = QHBoxLayout()
            self.title_label = QLabel(tr("日志"))
            self.title_label.setObjectName("PageTitle")
            self.refresh_btn = QPushButton(tr("刷新日志"))
            self.refresh_btn.clicked.connect(self.refresh)
            header.addWidget(self.title_label)
            header.addStretch(1)
            header.addWidget(self.refresh_btn)
            root.addLayout(header)

            info = QLabel(f"{tr('日志路径：')}{self.log_path}")
            info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            root.addWidget(info)

            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.setPlaceholderText(tr("最近日志会显示在这里。"))
            root.addWidget(self.output, 1)

        def refresh(self) -> None:
            if not self.log_path.exists():
                self.output.setPlainText(
                    tr("还没有 latest.log。先执行一次 install / update / remove 之类的命令。")
                )
                return
            self.output.setPlainText(self.log_path.read_text(encoding="utf-8", errors="replace"))
            self.output.moveCursor(QTextCursor.MoveOperation.End)

        def update_language(self) -> None:
            self.title_label.setText(tr("日志"))
            self.refresh_btn.setText(tr("刷新日志"))
            self.output.setPlaceholderText(tr("最近日志会显示在这里。"))


    class MaintenancePage(QWidget):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 18)
            root.setSpacing(16)

            self.title_label = QLabel(tr("维护"))
            self.title_label.setObjectName("PageTitle")
            root.addWidget(self.title_label)

            box = QGroupBox(tr("高级维护"))
            form = QFormLayout(box)
            self.rebuild_btn = QPushButton(tr("执行 state rebuild"))
            self.rebuild_btn.clicked.connect(self.run_rebuild)
            form.addRow(tr("状态修复"), self.rebuild_btn)
            root.addWidget(box)
            root.addStretch(1)

        def run_rebuild(self) -> None:
            task = TaskDialog(
                tr("执行 state rebuild"),
                ["state", "rebuild"],
                operation="rebuild",
                parent=self,
            )
            task.exec()
            main_window = self.window()
            if hasattr(main_window, "refresh_everything"):
                main_window.refresh_everything()

        def update_language(self) -> None:
            self.title_label.setText(tr("维护"))
            self.rebuild_btn.setText(tr("执行 state rebuild"))


    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.client = MjaClient(self)

            self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
            self.resize(1180, 760)

            self.client.command_started.connect(self._append_log)
            self.client.command_log.connect(self._append_log)
            self.client.command_failed.connect(self._handle_command_error)

            self._build_ui()
            self._build_menu()
            self._apply_style()

            self.refresh_everything()

        def _build_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)

            root = QHBoxLayout(central)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            self.nav = QListWidget()
            self.nav.setFixedWidth(210)
            self.nav.setSpacing(4)
            # Store navigation labels to support language switching
            self.nav_labels = ["仪表盘", "搜索", "已安装", "日志", "维护"]
            for label in self.nav_labels:
                QListWidgetItem(tr(label), self.nav)
            self.nav.currentRowChanged.connect(self._switch_page)
            root.addWidget(self.nav)

            self.stack = QStackedWidget()
            root.addWidget(self.stack, 1)

            self.dashboard_page = DashboardPage(self.client)
            self.search_page = SearchPage(self.client)
            self.installed_page = InstalledPage(self.client)
            self.logs_page = LogsPage()
            self.maintenance_page = MaintenancePage()

            self.stack.addWidget(self.dashboard_page)
            self.stack.addWidget(self.search_page)
            self.stack.addWidget(self.installed_page)
            self.stack.addWidget(self.logs_page)
            self.stack.addWidget(self.maintenance_page)

            self.nav.setCurrentRow(0)

            status = QStatusBar()
            self.setStatusBar(status)
            self.status_label = QLabel(tr("就绪"))
            status.addWidget(self.status_label)

        def _build_menu(self) -> None:
            menubar = self.menuBar()
            # Build File menu
            self.file_menu = menubar.addMenu(tr("文件"))
            self.refresh_action = QAction(tr("刷新全部"), self)
            self.refresh_action.triggered.connect(self.refresh_everything)
            self.file_menu.addAction(self.refresh_action)

            self.exit_action = QAction(tr("退出"), self)
            self.exit_action.triggered.connect(self.close)
            self.file_menu.addAction(self.exit_action)

            # Build Language menu for switching UI languages
            self.lang_menu = menubar.addMenu(tr("语言"))
            self.zh_action = QAction(tr("中文"), self)
            self.zh_action.triggered.connect(lambda: self._change_language("zh"))
            self.lang_menu.addAction(self.zh_action)
            self.en_action = QAction("English", self)
            self.en_action.triggered.connect(lambda: self._change_language("en"))
            self.lang_menu.addAction(self.en_action)

        def _change_language(self, lang: str) -> None:
            """Handle a language selection from the menu.

            Updates the global language and refreshes the UI.  Supported
            languages are 'zh' for Chinese and 'en' for English.  If an
            unsupported language code is provided, no action is taken.
            """
            set_language(lang)
            self.update_language()

        def update_language(self) -> None:
            """Refresh all user-visible text across the main window.

            This method is invoked after the global language changes to
            propagate translations to navigation items, status bar text,
            page content and menu labels.  Individual pages may define
            their own ``update_language()`` methods which are called
            if present.
            """
            # Update navigation labels
            for i, label in enumerate(self.nav_labels):
                item = self.nav.item(i)
                if item is not None:
                    item.setText(tr(label))
            # Update status bar text.  Preserve the current page index
            current_index = self.nav.currentRow()
            titles = {
                0: "仪表盘",
                1: "搜索",
                2: "已安装",
                3: "日志",
                4: "维护",
            }
            current_title = titles.get(current_index, "-")
            # If the status label contains colon, refresh only the page part
            if current_title:
                self.status_label.setText(f"{tr('当前页面：')}{tr(current_title)}")
            else:
                self.status_label.setText(tr("就绪"))
            # Update menu labels
            try:
                self.file_menu.setTitle(tr("文件"))
                self.refresh_action.setText(tr("刷新全部"))
                self.exit_action.setText(tr("退出"))
            except Exception:
                pass
            # Update pages
            for page in (self.dashboard_page, self.search_page, self.installed_page, self.logs_page, self.maintenance_page):
                if hasattr(page, "update_language"):
                    page.update_language()
            try:
                self.lang_menu.setTitle(tr("语言"))
                self.zh_action.setText(tr("中文"))
                self.en_action.setText("English")
            except Exception:
                pass

        def _apply_style(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow {
                    background: #1e1f24;
                }
                QListWidget {
                    background: #18191d;
                    border: none;
                    color: #d8dee9;
                    padding: 10px 8px;
                }
                QListWidget::item {
                    padding: 12px 10px;
                    border-radius: 8px;
                }
                QListWidget::item:selected {
                    background: #2c313c;
                    color: white;
                }
                QStackedWidget, QWidget {
                    color: #e6e6e6;
                    font-size: 13px;
                }
                QLabel#PageTitle {
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#DialogTitle {
                    font-size: 18px;
                    font-weight: 700;
                    color: #ffffff;
                }
                QLabel#InfoBanner {
                    border-radius: 10px;
                    padding: 10px 12px;
                    background: #27324b;
                    color: #d8e5ff;
                    border: 1px solid #3d4f77;
                }
                QLabel#InfoBanner[level="warning"] {
                    background: #4a3420;
                    color: #ffe2b8;
                    border: 1px solid #7d5630;
                }
                QLabel#InfoBanner[level="ok"] {
                    background: #21382b;
                    color: #cff1d7;
                    border: 1px solid #2d5e3d;
                }
                QFrame#StatCard {
                    background: #2a2d35;
                    border: 1px solid #3a3f4b;
                    border-radius: 12px;
                }
                QLabel#CardTitle {
                    color: #b8c1d1;
                    font-size: 12px;
                }
                QLabel#CardValue {
                    font-size: 22px;
                    font-weight: 700;
                    color: white;
                }
                QLineEdit, QPlainTextEdit {
                    background: #242730;
                    border: 1px solid #3a3f4b;
                    border-radius: 8px;
                    padding: 8px;
                    color: #f0f0f0;
                }
                QComboBox {
                    background: #242730;
                    border: 1px solid #3a3f4b;
                    border-radius: 8px;
                    padding: 8px;
                    color: #f0f0f0;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 28px;
                }
                QComboBox::down-arrow {
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background: #242730;
                    color: #f0f0f0;
                    border: 1px solid #3a3f4b;
                    selection-background-color: #3c5ccf;
                    selection-color: #ffffff;
                    outline: 0;
                }
                QTableWidget {
                    background: #242730;
                    border: 1px solid #3a3f4b;
                    border-radius: 8px;
                    color: #f0f0f0;
                    gridline-color: #343846;
                    selection-background-color: #3c5ccf;
                    selection-color: #ffffff;
                    alternate-background-color: #2a2d35;
                }
                QTableWidget::item {
                    padding: 8px;
                }
                QTableWidget::item:selected {
                    background: #3c5ccf;
                    color: #ffffff;
                }
                QTableCornerButton::section {
                    background: #30343f;
                    border: none;
                }
                QPushButton {
                    background: #3c5ccf;
                    border: none;
                    border-radius: 8px;
                    padding: 9px 14px;
                    color: white;
                    font-weight: 600;
                }
                QPushButton:disabled {
                    background: #4b4f58;
                    color: #c1c1c1;
                }
                QGroupBox {
                    border: 1px solid #3a3f4b;
                    border-radius: 12px;
                    margin-top: 8px;
                    padding-top: 14px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 4px;
                }
                QHeaderView::section {
                    background: #30343f;
                    border: none;
                    padding: 8px;
                    font-weight: 600;
                }
                QMenuBar, QMenu, QStatusBar {
                    background: #18191d;
                    color: #e6e6e6;
                }
                QDialog {
                    background: #1f222a;
                    color: #f0f0f0;
                }
                QDialog QLabel {
                    color: #f0f0f0;
                }
                QDialog QPlainTextEdit {
                    background: #242730;
                    border: 1px solid #3a3f4b;
                    border-radius: 8px;
                    padding: 8px;
                    color: #f0f0f0;
                }
                QDialogButtonBox QPushButton {
                    min-width: 110px;
                }
                """
            )

        def _switch_page(self, index: int) -> None:
            self.stack.setCurrentIndex(index)
            titles = {
                0: "仪表盘",
                1: "搜索",
                2: "已安装",
                3: "日志",
                4: "维护",
            }
            # Update status bar with translated current page name
            page_name = titles.get(index, "-")
            self.status_label.setText(f"{tr('当前页面：')}{tr(page_name)}")

        def _append_log(self, text: str) -> None:
            self.status_label.setText(text)

        def _handle_command_error(self, message: str) -> None:
            self.status_label.setText(tr("命令失败"))
            show_result_dialog(
                self,
                f"{APP_TITLE} - {tr("命令失败")}",
                tr("只读操作失败。请查看详细输出。"),
                message,
                success=False,
            )

        def refresh_everything(self) -> None:
            self.dashboard_page.refresh()
            self.installed_page.refresh()
            self.logs_page.refresh()

        def refresh_after_task(self) -> None:
            self.refresh_everything()


def run_gui() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


class SkeletonTests(unittest.TestCase):
    def test_build_command_json(self) -> None:
        args = _build_mja_command(["doctor"], json_mode=True)
        self.assertEqual(args[-2:], ["doctor", "--json"])

    def test_build_command_text(self) -> None:
        args = _build_mja_command(["list"], json_mode=False)
        self.assertEqual(args[-1], "list")
        self.assertNotIn("--json", args)

    def test_build_install_subargs(self) -> None:
        args = build_install_subargs("google-chrome", source="aur", export="desktop", bin_name="")
        self.assertEqual(args, ["install", "google-chrome", "--source", "aur", "--export", "desktop"])

    def test_build_remove_subargs(self) -> None:
        args = build_remove_subargs("nitch", unexport=True)
        self.assertEqual(args, ["remove", "nitch", "--unexport"])

    def test_build_repair_subargs(self) -> None:
        args = build_repair_export_subargs("google-chrome", mode="desktop", bin_name="")
        self.assertEqual(args, ["repair", "export", "google-chrome", "--mode", "desktop"])

    def test_build_update_subargs(self) -> None:
        self.assertEqual(build_update_subargs("all"), ["update", "--all"])

    def test_parse_json_success(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["python", "-m", "mja", "doctor", "--json"],
            returncode=0,
            stdout='{"ok": true}',
            stderr="",
        )
        result = _parse_completed_process(proc, parse_json=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"ok": True})

    def test_parse_nonzero_failure(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["python", "-m", "mja", "doctor"],
            returncode=2,
            stdout="",
            stderr="boom",
        )
        result = _parse_completed_process(proc, parse_json=False)
        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)

    def test_classify_environment_arch_like(self) -> None:
        with unittest.mock.patch(
            "builtins.open",
            unittest.mock.mock_open(read_data='ID=arch\nPRETTY_NAME="Arch Linux"\n'),
        ):
            level, text = classify_environment([
                {"name": "pacman", "ok": True},
                {"name": "pamac", "ok": False},
            ])
        self.assertEqual(level, "warning")
        self.assertIn("Arch Linux", text)

    def test_classify_environment_manjaro_missing_container(self) -> None:
        with unittest.mock.patch(
            "builtins.open",
            unittest.mock.mock_open(read_data='ID=manjaro\nPRETTY_NAME="Manjaro Linux"\n'),
        ):
            level, text = classify_environment([
                {"name": "pamac", "ok": True},
                {"name": "distrobox", "ok": False},
                {"name": "container-runtime", "ok": False},
            ])
        self.assertEqual(level, "info")
        self.assertIn("Manjaro Linux", text)

    def test_parse_numbered_options_inline(self) -> None:
        text = "1) linuxqq 2) linuxqq-appimage 3) linuxqq-nt-bwrap"
        self.assertEqual(
            parse_numbered_options(text),
            ["linuxqq", "linuxqq-appimage", "linuxqq-nt-bwrap"],
        )

    def test_detect_provider_prompt_english(self) -> None:
        sample = "There are 3 providers available for linuxqq:\n1) linuxqq 2) linuxqq-appimage 3) linuxqq-nt-bwrap"
        result = detect_interaction_prompt(sample)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "provider_select")
        self.assertEqual(result["options"], ["linuxqq", "linuxqq-appimage", "linuxqq-nt-bwrap"])

    def test_detect_provider_prompt_chinese(self) -> None:
        sample = "软件库 linuxqq 有 3 个提供者：\n1) linuxqq 2) linuxqq-appimage 3) linuxqq-nt-bwrap"
        result = detect_interaction_prompt(sample)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "provider_select")
        self.assertEqual(result["options"], ["linuxqq", "linuxqq-appimage", "linuxqq-nt-bwrap"])

    def test_detect_yes_no_prompt(self) -> None:
        result = detect_interaction_prompt(":: Proceed with installation? [Y/n]")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "yes_no")

    def test_detect_password_prompt_plain_english(self) -> None:
        result = detect_interaction_prompt("Password:\n")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "password")

    def test_detect_password_prompt_sudo(self) -> None:
        result = detect_interaction_prompt("[sudo] password for molang:\n")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "password")

    def test_detect_password_prompt_chinese(self) -> None:
        result = detect_interaction_prompt("密码:\n")
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "password")

    def test_filter_installed_rows_default(self) -> None:
        rows = [
            {"name": "a", "install_status": "installed"},
            {"name": "b", "install_status": "removed"},
        ]
        filtered = filter_installed_rows(rows, "仅已安装")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "a")

    def test_trim_prompt_buffer(self) -> None:
        trimmed = trim_prompt_buffer("a" * 4000, "b" * 200, max_len=4096)
        self.assertEqual(len(trimmed), 4096)
        self.assertTrue(trimmed.endswith("b" * 200))


def main() -> int:
    if "--self-test" in sys.argv:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SkeletonTests)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1

    if not PYSIDE6_AVAILABLE:
        return FallbackConsoleApp().run()

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
