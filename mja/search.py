from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Any

from .errors import MjaError
from .models import SearchResult
from .runtime import require_binary, run
from . import __version__

AUR_BASE = "https://aur.archlinux.org/rpc/v5"


def repo_search(query: str) -> list[SearchResult]:
    require_binary("pacman", "E001 PACMAN_NOT_FOUND")
    result = run(["pacman", "-Ss", "--color", "never", query], check=False)
    if result.returncode not in (0, 1):
        raise MjaError("E001 PACMAN_SEARCH_FAILED", "repo search failed", result.stderr.strip())

    lines = result.stdout.splitlines()
    items: list[SearchResult] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line[:1].isspace():
            i += 1
            continue

        parts = line.split()
        if not parts:
            i += 1
            continue

        repo_name = parts[0]
        version = parts[1] if len(parts) > 1 else ""
        description_parts: list[str] = []
        i += 1
        while i < len(lines) and (lines[i][:1].isspace() or not lines[i].strip()):
            if lines[i].strip():
                description_parts.append(lines[i].strip())
            i += 1

        if "/" not in repo_name:
            continue

        repo, name = repo_name.split("/", 1)
        items.append(
            SearchResult(
                source="repo",
                repo=repo,
                name=name,
                version=version,
                description=" ".join(description_parts),
                exact=(name == query),
            )
        )
    return items


def repo_exact(name: str) -> SearchResult | None:
    require_binary("pacman", "E001 PACMAN_NOT_FOUND")
    result = run(["pacman", "-Si", name], check=False)
    if result.returncode != 0:
        return None

    info = _parse_key_values(result.stdout)
    return SearchResult(
        source="repo",
        repo=info.get("Repository"),
        name=info.get("Name", name),
        version=info.get("Version", ""),
        description=info.get("Description", ""),
        exact=True,
    )


def aur_search(query: str) -> list[SearchResult]:
    payload = _aur_get(f"/search/{urllib.parse.quote(query)}")
    return [_aur_result_to_search_result(item, query=query) for item in payload.get("results", [])]


def aur_exact(name: str) -> SearchResult | None:
    payload = aur_info(name)
    results = payload.get("results", [])
    if not results:
        return None
    item = results[0]
    return _aur_result_to_search_result(item, query=name, exact_override=True)


def aur_info(name: str) -> dict[str, Any]:
    return _aur_get(f"/info/{urllib.parse.quote(name)}")


def search(query: str, include_repo: bool = True, include_aur: bool = True) -> dict[str, list[SearchResult]]:
    """Search packages from the repo and/or AUR.

    Results from each source are sorted according to a unified ranking.  The ranking
    prioritises exact and close matches and then orders by popularity and votes.

    Args:
        query: The package name query supplied by the user.
        include_repo: Whether to include results from the host repository.
        include_aur: Whether to include results from the AUR.

    Returns:
        A mapping containing two lists: ``repo`` and ``aur``.  Each list holds
        ``SearchResult`` objects sorted by relevance.
    """
    if not include_repo and not include_aur:
        include_repo = True
        include_aur = True

    response: dict[str, list[SearchResult]] = {"repo": [], "aur": []}
    if include_repo:
        repo_items = repo_search(query)
        response["repo"] = sort_search_results(repo_items, query)
    if include_aur:
        aur_items = aur_search(query)
        response["aur"] = sort_search_results(aur_items, query)
    return response


def to_jsonable(results: dict[str, list[SearchResult]]) -> dict[str, list[dict[str, Any]]]:
    return {key: [item.to_dict() for item in value] for key, value in results.items()}


def format_search(results: dict[str, list[SearchResult]], query: str = "") -> str:
    """Format search results for CLI output.

    When ``query`` is provided the output uses a single globally ranked list so
    CLI behaviour matches the GUI.  When omitted, the historical sectioned
    output is preserved for compatibility with existing tests and callers.
    """

    if not query:
        lines: list[str] = []
        repo_items = results.get("repo", [])
        aur_items = results.get("aur", [])
        if repo_items:
            lines.append("[repo]")
            for item in repo_items:
                prefix = "=" if item.exact else "-"
                lines.append(f"{prefix} {item.repo}/{item.name} {item.version}".rstrip())
                if item.description:
                    lines.append(f"    {item.description}")
        if aur_items:
            if lines:
                lines.append("")
            lines.append("[aur]")
            for item in aur_items:
                meta: list[str] = []
                if item.votes is not None:
                    meta.append(f"votes={item.votes}")
                if item.popularity is not None:
                    meta.append(f"pop={format_popularity(item.popularity)}")
                suffix = f" ({', '.join(meta)})" if meta else ""
                prefix = "=" if item.exact else "-"
                lines.append(f"{prefix} {item.name} {item.version}{suffix}".rstrip())
                if item.description:
                    lines.append(f"    {item.description}")
        return "\n".join(lines) if lines else "No results."

    items = flatten_sorted_results(results, query)
    lines: list[str] = []
    for item in items:
        meta: list[str] = []
        if item.votes is not None:
            meta.append(f"votes={item.votes}")
        if item.popularity is not None:
            meta.append(f"pop={format_popularity(item.popularity)}")
        suffix = f" ({', '.join(meta)})" if meta else ""
        prefix = "=" if item.exact else "-"
        source_prefix = f"{item.repo}/" if item.source == "repo" and item.repo else "aur/" if item.source == "aur" else ""
        lines.append(f"{prefix} {source_prefix}{item.name} {item.version}{suffix}".rstrip())
        if item.description:
            lines.append(f"    {item.description}")

    if not lines:
        lines.append("No results.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions for search result ranking and display.
#
# The GUI and CLI rely on a consistent ordering of search results.  Without
# explicit ordering, repo results are returned in pacman’s arbitrary order and
# AUR results are returned exactly as delivered by the RPC.  To provide a
# better user experience, we score each result based on how well it matches
# the query and then sort by popularity and votes.  We also lightly penalise
# packages that are clearly sub-packages or developer tools so that the
# primary package appears first.

_SUFFIX_KEYWORDS = [
    "-git",
    "-devtools",
    "theme",
    "icon",
    "toggle",
    "backup",
    "devtools",
    "debug",
    "wrapper",
]


def _match_quality(name: str, description: str, query: str) -> int:
    """Return an integer score indicating how closely a result matches the query.

    Higher numbers indicate a better match.  The ranking is designed to
    prioritise exact matches, then case-insensitive matches, then prefix
    matches, then substring matches within the name, then matches only in
    the description.

    Args:
        name: The package name.
        description: The package description (may be empty).
        query: The user’s search query.

    Returns:
        An integer score between 0 and 5 inclusive.  Five represents an
        exact match, while zero represents no meaningful match.
    """
    if not query:
        return 0
    # exact match (case-sensitive)
    if name == query:
        return 5
    lower_name = name.lower()
    lower_query = query.lower()
    # exact match ignoring case
    if lower_name == lower_query:
        return 4
    # prefix match ignoring case
    if lower_name.startswith(lower_query):
        return 3
    # substring match within the name ignoring case
    if lower_query in lower_name:
        return 2
    # match within the description ignoring case
    if description and lower_query in description.lower():
        return 1
    return 0


def _has_suffix(name: str) -> bool:
    """Return True if the name appears to be an auxiliary or development package.

    A list of common suffix keywords (e.g. ``-git``, ``-devtools``) is used to
    detect sub-packages or debugging variants.  These packages should be
    de-prioritised relative to the main package but still included in the
    results.

    Args:
        name: The package name to inspect.

    Returns:
        True if any suffix keyword is present in the name; False otherwise.
    """
    lower = name.lower()
    return any(keyword in lower for keyword in _SUFFIX_KEYWORDS)


def sort_search_results(items: list[SearchResult], query: str) -> list[SearchResult]:
    """Return a sorted copy of ``items`` based on match quality and popularity.

    Results are ordered first by match quality, then by whether they appear
    auxiliary (items containing certain suffix keywords are lightly
    penalised), then by popularity and votes.  When no popularity or vote
    information is available (e.g. repo results), ``None`` values are
    treated as zero for comparison purposes.

    Args:
        items: A list of ``SearchResult`` objects.
        query: The original search query.

    Returns:
        A new list containing the sorted results.
    """

    def _score(item: SearchResult) -> tuple[int, int, float, int, str]:
        # Use explicit ascending sort keys so the final tie-breaker can remain
        # alphabetical while higher quality/popularity/votes still rank first.
        quality = _match_quality(item.name, item.description, query)
        penalty = 1 if _has_suffix(item.name) else 0
        pop = item.popularity if item.popularity is not None else 0.0
        votes = item.votes if item.votes is not None else 0
        return (-quality, penalty, -pop, -votes, item.name.lower())

    return sorted(items, key=_score)


def sort_search_dicts(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Return a globally sorted copy of JSON-serialisable search result dictionaries."""

    def _score(item: dict[str, Any]) -> tuple[int, int, float, int, str]:
        name = str(item.get("name", ""))
        quality = _match_quality(name, str(item.get("description", "")), query)
        penalty = 1 if _has_suffix(name) else 0
        pop = item.get("popularity") if item.get("popularity") is not None else 0.0
        votes = item.get("votes") if item.get("votes") is not None else 0
        return (-quality, penalty, -pop, -votes, name.lower())

    return sorted(items, key=_score)


def flatten_sorted_results(results: dict[str, list[SearchResult]], query: str) -> list[SearchResult]:
    """Return repo and AUR results as a single globally ranked list."""
    combined = [*results.get("repo", []), *results.get("aur", [])]
    return sort_search_results(combined, query)


# Backward-compatible alias for older callers
sort_results = sort_search_results


def format_popularity(value: float) -> str:
    """Format a popularity value into a human-friendly decimal representation.

    The AUR RPC returns popularity as a floating-point number.  By default
    Python may render very small values in scientific notation, which is
    confusing for end users.  This helper formats the number with up to
    six decimal places and falls back to ``<0.000001`` for extremely small
    values.

    Args:
        value: The raw popularity value from the AUR API.

    Returns:
        A string representing the popularity.  Values below 1e-6 are shown as
        ``<0.000001``.
    """
    try:
        if value < 1e-6:
            return "<0.000001"
        return f"{value:.6f}"
    except Exception:
        # Fallback: return the raw value as string
        return str(value)


def _aur_get(path: str) -> dict[str, Any]:
    url = f"{AUR_BASE}{path}"
    # Construct a User-Agent header using the current package version.  This avoids
    # hard-coding an outdated identifier in the AUR RPC requests and ensures
    # consistency with the actual release.  Fallback to a generic token if
    # ``__version__`` is unavailable for some reason.
    try:
        version = __version__  # defined in mja.__init__
    except Exception:
        version = "unknown"
    ua = f"mja/{version} (+https://aur.archlinux.org)"
    request = urllib.request.Request(
        url=url,
        headers={"User-Agent": ua},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise MjaError("E010 AUR_RPC_UNAVAILABLE", "could not reach AUR RPC", str(exc)) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MjaError("E011 AUR_RPC_BAD_RESPONSE", "AUR RPC returned invalid JSON", raw[:500]) from exc

    if "results" not in payload:
        raise MjaError("E011 AUR_RPC_BAD_RESPONSE", "missing 'results' in AUR RPC response", payload)
    return payload


def _aur_result_to_search_result(
    item: dict[str, Any],
    *,
    query: str,
    exact_override: bool = False,
) -> SearchResult:
    name = item.get("Name", "")
    return SearchResult(
        source="aur",
        name=name,
        version=item.get("Version", ""),
        description=item.get("Description", "") or "",
        exact=exact_override or name == query,
        popularity=float(item["Popularity"]) if item.get("Popularity") is not None else None,
        votes=int(item["NumVotes"]) if item.get("NumVotes") is not None else None,
        package_base=item.get("PackageBase"),
    )


def _parse_key_values(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapping[key.strip()] = value.strip()
    return mapping
