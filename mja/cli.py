from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .doctor import format_doctor, run_doctor
from .errors import MjaError
from .install import install
from .models import ExportMode, ResolveSource
from .search import format_search, search, to_jsonable
from .list_cmd import list_packages, format_list
from .remove import remove as remove_package
from .repair import repair_export
from .state_rebuild import rebuild_state
from .update_cmd import update_packages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mja",
        # Reflect the current release version in the CLI description.  Keep this
        # string in sync with the version defined in __init__.py and
        # pyproject.toml when bumping releases.
        # Keep the CLI description aligned with the unified version.  Using
        # v1.0 here avoids confusion with older patch identifiers.
        description="Manjaro AUR isolation orchestrator (v1.0)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="search repo and/or AUR")
    search_parser.add_argument("query")
    search_parser.add_argument("--repo", action="store_true", help="search repo only")
    search_parser.add_argument("--aur", action="store_true", help="search AUR only")
    search_parser.add_argument("--json", action="store_true", help="emit JSON")

    install_parser = subparsers.add_parser("install", help="install from repo or AUR container")
    install_parser.add_argument("name")
    install_parser.add_argument(
        "--source",
        choices=[item.value for item in ResolveSource],
        default=ResolveSource.AUTO.value,
    )
    install_parser.add_argument(
        "--export",
        choices=[item.value for item in ExportMode],
        default=ExportMode.AUTO.value,
    )
    install_parser.add_argument("--bin", dest="selected_bin")
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.add_argument("--json", action="store_true", help="emit JSON")

    doctor_parser = subparsers.add_parser("doctor", help="verify local prerequisites")
    doctor_parser.add_argument("--fix", action="store_true")
    doctor_parser.add_argument("--json", action="store_true", help="emit JSON")

    list_parser = subparsers.add_parser("list", help="list recorded packages")
    list_parser.add_argument("--json", action="store_true", help="emit JSON")

    remove_parser = subparsers.add_parser("remove", help="remove an installed package")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--unexport", action="store_true", help="remove exported apps/binaries")
    remove_parser.add_argument("--json", action="store_true", help="emit JSON")

    # repair subcommands
    repair_parser = subparsers.add_parser("repair", help="repair recorded information")
    repair_sub = repair_parser.add_subparsers(dest="repair_command", required=True)
    repair_export_parser = repair_sub.add_parser("export", help="re-export desktop entries or binaries")
    repair_export_parser.add_argument("name")
    repair_export_parser.add_argument(
        "--mode",
        choices=[ExportMode.AUTO.value, ExportMode.DESKTOP.value, ExportMode.BIN.value],
        default=ExportMode.AUTO.value,
        help="export mode: auto, desktop, or bin",
    )
    repair_export_parser.add_argument("--bin", dest="selected_bin")
    repair_export_parser.add_argument("--json", action="store_true", help="emit JSON")

    # state subcommands
    state_parser = subparsers.add_parser("state", help="inspect or rebuild state")
    state_sub = state_parser.add_subparsers(dest="state_command", required=True)
    state_rebuild_parser = state_sub.add_parser("rebuild", help="rebuild state for recorded packages")
    state_rebuild_parser.add_argument("--json", action="store_true", help="emit JSON")

    # update command
    update_parser = subparsers.add_parser("update", help="update host and/or container packages")
    update_parser.add_argument("--host", action="store_true", help="update host repository packages")
    update_parser.add_argument("--container", action="store_true", help="update container packages")
    update_parser.add_argument("--all", action="store_true", help="update both host and container packages")
    update_parser.add_argument("--json", action="store_true", help="emit JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "search":
            repo_only = args.repo and not args.aur
            aur_only = args.aur and not args.repo
            results = search(
                args.query,
                include_repo=not aur_only,
                include_aur=not repo_only,
            )
            if args.json:
                print(json.dumps(to_jsonable(results), ensure_ascii=False, indent=2))
            else:
                print(format_search(results, query=args.query))
            return 0

        if args.command == "install":
            result = install(
                args.name,
                source=ResolveSource(args.source),
                export=ExportMode(args.export),
                selected_bin=args.selected_bin,
                dry_run=args.dry_run,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(format_install_result(result))
            return 0

        if args.command == "doctor":
            report = run_doctor(fix=args.fix)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(format_doctor(report))
            return 0

        if args.command == "list":
            packages = list_packages()
            if args.json:
                print(json.dumps(packages, ensure_ascii=False, indent=2))
            else:
                print(format_list(packages))
            return 0

        if args.command == "remove":
            result = remove_package(args.name, unexport=getattr(args, "unexport", False))
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(format_remove_result(result))
            return 0

        if args.command == "repair":
            if args.repair_command == "export":
                result = repair_export(
                    args.name,
                    mode=ExportMode(args.mode),
                    selected_bin=getattr(args, "selected_bin", None),
                )
                if args.json:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    print(format_install_result(result))
                return 0
            parser.error(f"unknown repair subcommand: {args.repair_command}")
            return 2

        if args.command == "state":
            if args.state_command == "rebuild":
                results = rebuild_state()
                if args.json:
                    print(json.dumps(results, ensure_ascii=False, indent=2))
                else:
                    print(format_rebuild_results(results))
                return 0
            parser.error(f"unknown state subcommand: {args.state_command}")
            return 2

        if args.command == "update":
            # Determine which side(s) to update. --all overrides individual flags.
            update_host = args.host or args.all
            update_container = args.container or args.all
            result = update_packages(update_host=update_host, update_container=update_container)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(format_update_result(result))
            return 0

        parser.error(f"unknown command: {args.command}")
        return 2
    except KeyboardInterrupt:
        # Gracefully handle Ctrl+C without a traceback
        print("Interrupted", file=sys.stderr)
        return 1
    except MjaError as exc:
        payload = {
            "error": {"code": exc.code, "message": exc.message, "details": exc.details}
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
            if exc.details is not None:
                if isinstance(exc.details, (dict, list)):
                    print(json.dumps(exc.details, ensure_ascii=False, indent=2), file=sys.stderr)
                else:
                    print(exc.details, file=sys.stderr)
        return 1


def format_install_result(result: dict[str, Any]) -> str:
    if result.get("dry_run"):
        return (
            "Dry run:\n"
            + json.dumps(result, ensure_ascii=False, indent=2)
        )

    lines = [
        f"package: {result['package']}",
        f"source: {result['source']}",
        f"install_status: {result['install_status']}",
        f"export_status: {result['export_status']}",
    ]
    if "container" in result:
        lines.append(f"container: {result['container']}")
    if result.get("desktop_entries"):
        lines.append("desktop_entries:")
        lines.extend([f"  - {item}" for item in result["desktop_entries"]])
    if result.get("binaries"):
        lines.append("binaries:")
        lines.extend([f"  - {item}" for item in result["binaries"]])
    return "\n".join(lines)


def format_remove_result(result: dict[str, Any]) -> str:
    """Format the output of a remove operation.

    Mirrors the style of :func:`format_install_result` but includes only
    the fields relevant for removal. Missing values are omitted.
    """
    lines = [
        f"package: {result['package']}",
        f"source: {result['source']}",
        f"install_status: {result['install_status']}",
        f"export_status: {result['export_status']}",
    ]
    if result.get("container"):
        lines.append(f"container: {result['container']}")
    return "\n".join(lines)


def format_rebuild_results(results: list[dict[str, Any]]) -> str:
    """Format the output of a state rebuild operation.

    The output iterates over each reconciled package and prints its
    salient fields. Nested items (desktop entries and binaries) are
    indented to improve readability.
    """
    if not results:
        return "No packages recorded."
    lines: list[str] = []
    for item in results:
        lines.append(f"package: {item['package']}")
        lines.append(f"  source: {item['source']}")
        lines.append(f"  install_status: {item['install_status']}")
        lines.append(f"  export_status: {item['export_status']}")
        if item.get("container"):
            lines.append(f"  container: {item['container']}")
        if item.get("desktop_entries"):
            lines.append("  desktop_entries:")
            for entry in item["desktop_entries"]:
                lines.append(f"    - {entry}")
        if item.get("binaries"):
            lines.append("  binaries:")
            for entry in item["binaries"]:
                lines.append(f"    - {entry}")
    return "\n".join(lines)


def format_update_result(result: dict[str, Any]) -> str:
    """Format the output of an update operation.

    The result dictionary contains an entry for the host update and a
    mapping of container names to their respective update outcomes. This
    function produces a concise summary suitable for terminal output.
    """
    lines: list[str] = []
    host = result.get("host")
    if host is not None:
        status = "ok" if host.get("ok") else "failed"
        lines.append(f"host: {status}")
        if not host.get("ok") and host.get("error"):
            lines.append(f"  error: {host['error']}")
    containers = result.get("containers", {})
    for name, res in containers.items():
        status = "ok" if res.get("ok") else "failed"
        lines.append(f"container {name}: {status}")
        if not res.get("ok") and res.get("error"):
            lines.append(f"  error: {res['error']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
