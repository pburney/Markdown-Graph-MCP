"""Shared utilities for Logseq graph access."""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from markdown_graph_kit import (
    title_to_filename,
    filename_to_title,
    pages_dir,
    journals_dir,
    assets_dir,
    recycle_dir,
    logseq_dir,
    page_path,
    journal_filename,
    parse_page_properties,
    backup_page_file,
    delete_page_file,
    set_page_property,
    ensure_graph_config,
    bootstrap_graph,
)
import markdown_graph_kit as _mgk
_props_from_lines = _mgk._props_from_lines

_CONFIG_PATH = Path(__file__).parent / "config.json"
_config = None


def _load_config():
    global _config
    if _config is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _config = json.load(f)
    return _config


def _graph_path(entry) -> str:
    """A graph's config entry is either a plain path string, or an object
    {"path": ..., "read_only": bool} — normalize either shape to the path string."""
    return entry if isinstance(entry, str) else entry["path"]


def list_graphs() -> dict[str, str]:
    """Return dict of graph_name -> path_string."""
    return {name: _graph_path(entry) for name, entry in _load_config()["graphs"].items()}


def default_graph() -> str:
    return _load_config()["default_graph"]


def resolve_graph(name: str | None) -> tuple[str, Path]:
    """Return (graph_name, graph_root_path) or raise ValueError."""
    cfg = _load_config()
    name = (name or cfg["default_graph"]).lower().strip()
    if name not in cfg["graphs"]:
        available = ", ".join(cfg["graphs"])
        raise ValueError(f"Unknown graph {name!r}. Available: {available}")
    return name, Path(_graph_path(cfg["graphs"][name]))


def read_only_mode() -> bool:
    """Global read_only flag from config.json (default False). Forces every graph read-only."""
    return bool(_load_config().get("read_only", False))


def graph_is_read_only(name: str) -> bool:
    """True if this graph is read-only, either globally (read_only_mode) or per-graph."""
    if read_only_mode():
        return True
    entry = _load_config()["graphs"].get(name)
    return isinstance(entry, dict) and bool(entry.get("read_only", False))


# Primitives (title_to_filename, filename_to_title, pages_dir, journals_dir,
# journal_filename, DEFAULT_CONFIG_SETTINGS, ensure_graph_config) are now
# imported from markdown_graph_kit above.


def mcp_tag() -> str:
    """Return the MCP tracking tag (e.g. '#🦾'). Configurable via config.json 'mcp_tag' key."""
    tag = _load_config().get("mcp_tag", "#🦾")
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag


def parse_date(date_str: str | None) -> date:
    """Parse 'YYYY-MM-DD' or return today if None."""
    if date_str is None:
        return date.today()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


_SKIP_DIRS = {"logseq", ".logseq"}


def find_page(graph_root: Path, title: str) -> Path | None:
    """Find a page file by title (case-insensitive). Returns Path or None."""
    stem = title_to_filename(title).lower()
    pg_dir = pages_dir(graph_root)
    if not pg_dir.exists():
        return None
    for f in pg_dir.rglob("*.md"):
        rel = f.relative_to(pg_dir)
        if rel.parts[0] in _SKIP_DIRS or any(p.startswith(".") for p in rel.parts):
            continue
        if f.stem.lower() == stem:
            return f
    return None


# ---------------------------------------------------------------------------
# Stage 2: search, list, property management
# ---------------------------------------------------------------------------

import re as _re

_SKIP_FIRST = {"logseq", ".logseq"}


# Property parsing (_props_from_lines, parse_page_properties) is now imported
# from markdown_graph_kit above.

def _normalize_prop(value: str) -> str:
    """Strip [[...]] wrappers and leading # for comparison; lowercase."""
    value = value.strip()
    value = _re.sub(r"^\[\[(.+)\]\]$", r"\1", value)
    value = _re.sub(r"^#", "", value)
    return value.lower()


def _matches_filter(prop_value: str, filter_value: str) -> bool:
    """True if any comma-separated part of prop_value matches filter_value."""
    target = _normalize_prop(filter_value)
    for part in prop_value.split(","):
        if _normalize_prop(part) == target:
            return True
    return False


def search_pages(graph_root: Path, filters: list, return_props: list) -> list:
    """
    Search pages by property filters (AND logic).
    filters: list of (key, value) tuples.
    return_props: list of property names to include in results.
    Returns list of dicts.
    """
    results = []
    for e in _page_entries_sorted(refresh_graph(graph_root)):
        props = e.props
        if all(
            key in props and _matches_filter(props[key], val)
            for key, val in filters
        ):
            results.append({p: props.get(p.lower(), "") for p in return_props})
    return results


def search_content(
    graph_root: Path,
    query: str,
    include_journals: bool = True,
    context_lines: int = 2,
) -> list[dict]:
    """
    Full-text search across pages and (optionally) journals.
    Returns list of {type, title, file, matches: [{line_number, line, context_before, context_after}]}.
    """
    results = []
    query_lower = query.lower()
    idx = refresh_graph(graph_root)

    entries = list(_page_entries_sorted(idx))
    if include_journals:
        entries.extend(_journal_entries_sorted(idx))

    for e in entries:
        lines = e.lines
        matches = []
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                matches.append({
                    "line_number": i + 1,
                    "line": line,
                    "context_before": lines[max(0, i - context_lines):i],
                    "context_after": lines[i + 1:i + 1 + context_lines],
                })
        if matches:
            results.append({"type": e.kind, "title": e.title, "file": str(e.path), "matches": matches})

    return results


def list_page_titles(graph_root: Path, prefix: str | None = None) -> list:
    """Return sorted list of human-readable page titles, optionally filtered by namespace prefix."""
    pages = pages_dir(graph_root)
    if not pages.exists():
        return []
    titles = []
    for md_file in pages.rglob("*.md"):
        rel = md_file.relative_to(pages)
        if rel.parts[0] in _SKIP_FIRST or any(p.startswith(".") for p in rel.parts):
            continue
        title = filename_to_title(md_file.stem)
        if prefix:
            p = prefix.lower()
            t = title.lower()
            if not (t == p or t.startswith(p + "/")):
                continue
        titles.append(title)
    return sorted(titles)


def list_recent_journals(graph_root: Path, n: int = 7) -> list:
    """
    Return list of (date_str, path, preview_lines) for the N most recent journals.
    preview_lines is a list of up to 3 non-empty content lines.
    """
    jdir = journals_dir(graph_root)
    if not jdir.exists():
        return []
    files = sorted(jdir.glob("*.md"), reverse=True)[:n]
    results = []
    for f in files:
        # filename is YYYY_MM_DD.md → date string YYYY-MM-DD
        date_str = f.stem.replace("_", "-")
        preview = []
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("collapsed::"):
                    preview.append(stripped)
                if len(preview) >= 3:
                    break
        except (OSError, UnicodeDecodeError):
            pass
        results.append((date_str, f, preview))
    return results


# set_page_property is now imported from markdown_graph_kit above.


# ---------------------------------------------------------------------------
# Stage 3: cross-graph entity linking
# ---------------------------------------------------------------------------

_WIKILINK_RE = _re.compile(r"\[\[([^\[\]]+)\]\]")


def extract_wikilinks(text: str) -> list:
    """Return page titles referenced via [[PageName]] syntax in text, in order, deduped."""
    seen = set()
    out = []
    for m in _WIKILINK_RE.finditer(text):
        title = m.group(1).strip()
        key = title.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(title)
    return out


# ---------------------------------------------------------------------------
# In-memory content index
#
# The MCP server is a long-lived process, so an in-memory index of parsed pages
# persists across tool calls within a session. Five read tools (search_content,
# find_backlinks, search_pages, find_entity_pages, list_entity_pages) previously
# re-walked the graph and re-parsed every file on every call, fanning out across
# all configured graphs when unscoped. The index caches the per-file parse
# (lines, page properties, wikilink targets) so a cache hit skips read+parse+regex.
#
# Correctness discipline (non-negotiable): mgm is NOT the only writer — Logseq and
# the user edit files directly — so every access re-walks the directory (to catch
# new/deleted files) and re-stats each file, rebuilding any entry whose
# (st_mtime_ns, st_size) stamp changed. We never trust a prior call's entry
# without re-stat. No persistent store; the index is a ~few-MB derived cache.
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    path: Path                 # the file as walked (unresolved), so str(path) == old "file" value
    kind: str                  # "page" | "journal"
    stem: str
    title: str                 # page: filename_to_title(stem); journal: stem with _ -> -
    stamp: tuple               # (st_mtime_ns, st_size) — the change key
    props: dict                # parse_page_properties() output
    lines: list                # splitlines() of file content
    link_targets: frozenset    # lowercased [[targets]] union (backlink prefilter)


@dataclass
class GraphIndex:
    entries: dict = field(default_factory=dict)   # str(md_file) -> Entry


_INDEX: dict = {}   # resolved-graph-root str -> GraphIndex


def _walk_pages_and_journals(graph_root: Path):
    """Yield (kind, md_file) for every page and top-level journal .md file,
    applying the same skip rules the direct-walk tools used: pages skip
    logseq/.logseq and any dotted path component; journals are the flat top-level
    *.md set (matching the old jdir.glob('*.md'))."""
    pages = pages_dir(graph_root)
    if pages.exists():
        for md_file in pages.rglob("*.md"):
            rel = md_file.relative_to(pages)
            if rel.parts[0] in _SKIP_FIRST or any(p.startswith(".") for p in rel.parts):
                continue
            yield "page", md_file
    journals = journals_dir(graph_root)
    if journals.exists():
        for md_file in journals.glob("*.md"):
            yield "journal", md_file


def _build_entry(md_file: Path, kind: str, stamp: tuple) -> Entry:
    """Read and parse a file into an Entry (called only on a cache miss)."""
    stem = md_file.stem
    title = filename_to_title(stem) if kind == "page" else stem.replace("_", "-")
    file_str = str(md_file)
    try:
        text = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable: matches old behavior — minimal props, no lines/links, so it
        # never contributes content/backlink matches and carries no filterable props.
        return Entry(md_file, kind, stem, title, stamp,
                     {"name": stem, "file": file_str}, [], frozenset())
    lines = text.splitlines()
    props = _props_from_lines(stem, file_str, lines)
    link_targets = frozenset(t.lower() for t in extract_wikilinks(text))
    return Entry(md_file, kind, stem, title, stamp, props, lines, link_targets)


def refresh_graph(graph_root: Path) -> GraphIndex:
    """Reconcile the in-memory index for one graph against the filesystem and
    return it. Always re-walks + re-stats; rebuilds only changed/new files."""
    key = str(graph_root.resolve())
    idx = _INDEX.setdefault(key, GraphIndex())
    current = set()
    for kind, md_file in _walk_pages_and_journals(graph_root):
        # str(md_file), not resolve(): the walk always yields the same stable path
        # string for a given file within a session, so it's a valid cache key
        # without a per-file realpath() syscall (that dominated the warm path).
        ekey = str(md_file)
        current.add(ekey)
        try:
            st = md_file.stat()
        except OSError:
            current.discard(ekey)
            continue
        stamp = (st.st_mtime_ns, st.st_size)
        e = idx.entries.get(ekey)
        if e is None or e.stamp != stamp or e.kind != kind:
            idx.entries[ekey] = _build_entry(md_file, kind, stamp)
    for stale in set(idx.entries) - current:
        del idx.entries[stale]
    return idx


def _page_entries_sorted(idx: GraphIndex):
    """Page entries in path order (reproduces the old sorted(pages.rglob(...)))."""
    return sorted((e for e in idx.entries.values() if e.kind == "page"),
                  key=lambda e: e.path)


def _journal_entries_sorted(idx: GraphIndex):
    """Journal entries in path order (reproduces the old sorted(jdir.glob(...)))."""
    return sorted((e for e in idx.entries.values() if e.kind == "journal"),
                  key=lambda e: e.path)


def _iter_pages(graph_root: Path):
    """Yield every page .md file under graph_root/pages, skipping logseq/.logseq and
    dotfiles. Index-backed; still yields Path objects for callers that want them."""
    for e in _page_entries_sorted(refresh_graph(graph_root)):
        yield e.path


def find_backlinks(
    graph_root: Path,
    title: str,
    include_journals: bool = True,
    context_lines: int = 1,
) -> list:
    """
    Find every page/journal entry in this graph that references `title` via [[title]].
    Returns list of {type, title, file, matches: [{line_number, line, context_before, context_after}]}.
    """
    results = []
    target = title.strip().lower()
    idx = refresh_graph(graph_root)

    entries = list(_page_entries_sorted(idx))
    if include_journals:
        entries.extend(_journal_entries_sorted(idx))

    for e in entries:
        if target not in e.link_targets:   # prefilter: no [[target]] anywhere in file
            continue
        matches = []
        for i, line in enumerate(e.lines):
            if any(link.lower() == target for link in extract_wikilinks(line)):
                matches.append({
                    "line_number": i + 1,
                    "line": line,
                    "context_before": e.lines[max(0, i - context_lines):i],
                    "context_after": e.lines[i + 1:i + 1 + context_lines],
                })
        if matches:
            results.append({"type": e.kind, "title": e.title, "file": str(e.path), "matches": matches})

    return results


def find_entity_pages(graph_root: Path, name: str, type_filter: str | None = None) -> dict:
    """
    Look up an entity by page title or mistoria-reference value/fragment.
    Returns {"entity_pages": [...], "related_pages": [...]}:
      - entity_pages: pages carrying a mistoria-reference:: property matching `name`
        (by exact title, or substring match against the reference value), optionally
        filtered to a given entity type (the reference's first colon-segment).
      - related_pages: other pages whose title contains `name` but have no
        mistoria-reference property yet (near-misses / conversion candidates).
    Each entry is the dict returned by parse_page_properties.
    """
    name_lower = name.strip().lower()
    type_lower = type_filter.strip().lower() if type_filter else None

    entity_pages = []
    related_pages = []

    for e in _page_entries_sorted(refresh_graph(graph_root)):
        props = e.props
        title = e.title
        ref = props.get("mistoria-reference", "")

        if ref:
            ref_type = ref.split(":", 1)[0].strip().lower()
            if type_lower and ref_type != type_lower:
                continue
            if title.lower() == name_lower or name_lower in ref.lower():
                entity_pages.append(dict(props))
            continue

        if type_lower is None and name_lower in title.lower():
            related_pages.append(dict(props))

    return {"entity_pages": entity_pages, "related_pages": related_pages}


def list_entity_pages(graph_root: Path, type_filter: str, filter_text: str | None = None) -> list:
    """
    List every page in this graph carrying a mistoria-reference:: property of the given type.
    filter_text, if given, must appear as a substring anywhere in the reference value.
    Returns list of props dicts (from parse_page_properties), sorted by title.
    """
    type_lower = type_filter.strip().lower()
    filter_lower = filter_text.strip().lower() if filter_text else None
    results = []

    for e in _page_entries_sorted(refresh_graph(graph_root)):
        props = e.props
        ref = props.get("mistoria-reference", "")
        if not ref:
            continue
        ref_type = ref.split(":", 1)[0].strip().lower()
        if ref_type != type_lower:
            continue
        if filter_lower and filter_lower not in ref.lower():
            continue
        results.append(dict(props))

    return sorted(results, key=lambda p: p.get("name", ""))
