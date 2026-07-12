"""Shared utilities for Logseq graph access."""

import json
from datetime import date, datetime
from pathlib import Path

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


def title_to_filename(title: str) -> str:
    """Convert a page title to its Logseq triple-lowbar filename stem."""
    return title.replace("/", "___")


def filename_to_title(stem: str) -> str:
    """Convert a triple-lowbar filename stem to a page title."""
    return stem.replace("___", "/")


def pages_dir(graph_root: Path) -> Path:
    return graph_root / "pages"


def journals_dir(graph_root: Path) -> Path:
    return graph_root / "journals"


def journal_filename(d: date) -> str:
    """Return the journal filename for a given date: YYYY_MM_DD.md"""
    return d.strftime("%Y_%m_%d") + ".md"


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
    pages = pages_dir(graph_root)
    if not pages.exists():
        return None
    for f in pages.rglob("*.md"):
        rel = f.relative_to(pages)
        if rel.parts[0] in _SKIP_DIRS or any(p.startswith(".") for p in rel.parts):
            continue
        if f.stem.lower() == stem:
            return f
    return None


def page_path(graph_root: Path, title: str) -> Path:
    """Return the canonical path for a page (may or may not exist)."""
    return pages_dir(graph_root) / (title_to_filename(title) + ".md")


def trash_dir(graph_root: Path) -> Path:
    return graph_root / ".trash"


def _backup_timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def backup_page_file(page_file: Path, graph_root: Path) -> Path:
    """Copy page_file's current content into .trash/<timestamp>-<filename>, creating
    .trash/ if needed. The original file is left in place. Returns the backup path.
    .trash/ is a dotdir, so it's already excluded from every read/search tool's
    rglob (they all skip any path component starting with '.')."""
    trash = trash_dir(graph_root)
    trash.mkdir(parents=True, exist_ok=True)
    backup_path = trash / f"{_backup_timestamp()}-{page_file.name}"
    backup_path.write_bytes(page_file.read_bytes())
    return backup_path


def delete_page_file(page_file: Path, graph_root: Path) -> Path:
    """Soft-delete: move page_file into .trash/<timestamp>-<filename>, creating .trash/
    if needed. Never a hard delete — the file is fully recoverable from .trash/.
    Returns the trash path."""
    trash = trash_dir(graph_root)
    trash.mkdir(parents=True, exist_ok=True)
    trash_path = trash / f"{_backup_timestamp()}-{page_file.name}"
    page_file.rename(trash_path)
    return trash_path


# ---------------------------------------------------------------------------
# Stage 2: search, list, property management
# ---------------------------------------------------------------------------

import re as _re

_SKIP_FIRST = {"logseq", ".logseq"}


def parse_page_properties(filepath: Path) -> dict:
    """Return dict of page-level properties from a Logseq .md file."""
    props = {"name": filepath.stem, "file": str(filepath)}
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return props
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            break
        m = _re.match(r"^([a-zA-Z0-9_-]+)::\s*(.*)", stripped)
        if m:
            props[m.group(1).lower()] = m.group(2).strip()
    return props


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
    root = graph_root.resolve()
    pages = pages_dir(graph_root)
    if not pages.exists():
        return results
    for md_file in sorted(pages.rglob("*.md")):
        rel = md_file.resolve().relative_to(root / "pages")
        if rel.parts[0] in _SKIP_FIRST or any(p.startswith(".") for p in rel.parts):
            continue
        props = parse_page_properties(md_file)
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
    candidates = []

    pdir = pages_dir(graph_root)
    if pdir.exists():
        for md_file in sorted(pdir.rglob("*.md")):
            rel = md_file.relative_to(pdir)
            if rel.parts[0] in _SKIP_FIRST or any(p.startswith(".") for p in rel.parts):
                continue
            candidates.append(("page", filename_to_title(md_file.stem), md_file))

    if include_journals:
        jdir = journals_dir(graph_root)
        if jdir.exists():
            for md_file in sorted(jdir.glob("*.md")):
                candidates.append(("journal", md_file.stem.replace("_", "-"), md_file))

    for ftype, title, filepath in candidates:
        try:
            lines = filepath.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
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
            results.append({"type": ftype, "title": title, "file": str(filepath), "matches": matches})

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


def set_page_property(page_path: Path, key: str, value: str) -> tuple:
    """
    Set or update a property on a page.
    Returns (old_value_or_None, 'added' | 'updated').
    Writes atomically via a temp file.
    """
    import tempfile, os
    key_lower = key.lower().strip()
    prop_pattern = _re.compile(rf"^{_re.escape(key_lower)}\s*::", _re.IGNORECASE)

    if page_path.exists():
        lines = page_path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []

    new_line = f"{key_lower}:: {value}\n"
    old_value = None
    action = None

    # Try to find and replace existing property
    for i, line in enumerate(lines):
        if prop_pattern.match(line):
            m = _re.match(r"^[^:]+::\s*(.*)", line.rstrip())
            old_value = m.group(1) if m else ""
            lines[i] = new_line
            action = "updated"
            break

    if action is None:
        # Insert before first bullet, or append
        insert_at = len(lines)
        for i, line in enumerate(lines):
            if line.lstrip().startswith(("- ", "* ")):
                insert_at = i
                break
        lines.insert(insert_at, new_line)
        action = "added"

    # Atomic write
    dir_ = page_path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.replace(tmp, page_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return old_value, action


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


def _iter_pages(graph_root: Path):
    """Yield every page .md file under graph_root/pages, skipping logseq/.logseq and dotfiles."""
    pages = pages_dir(graph_root)
    if not pages.exists():
        return
    for md_file in sorted(pages.rglob("*.md")):
        rel = md_file.relative_to(pages)
        if rel.parts[0] in _SKIP_FIRST or any(p.startswith(".") for p in rel.parts):
            continue
        yield md_file


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
    candidates = []

    for md_file in _iter_pages(graph_root):
        candidates.append(("page", filename_to_title(md_file.stem), md_file))

    if include_journals:
        jdir = journals_dir(graph_root)
        if jdir.exists():
            for md_file in sorted(jdir.glob("*.md")):
                candidates.append(("journal", md_file.stem.replace("_", "-"), md_file))

    for ftype, ctitle, filepath in candidates:
        try:
            lines = filepath.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        matches = []
        for i, line in enumerate(lines):
            if any(link.lower() == target for link in extract_wikilinks(line)):
                matches.append({
                    "line_number": i + 1,
                    "line": line,
                    "context_before": lines[max(0, i - context_lines):i],
                    "context_after": lines[i + 1:i + 1 + context_lines],
                })
        if matches:
            results.append({"type": ftype, "title": ctitle, "file": str(filepath), "matches": matches})

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

    for md_file in _iter_pages(graph_root):
        props = parse_page_properties(md_file)
        title = filename_to_title(md_file.stem)
        ref = props.get("mistoria-reference", "")

        if ref:
            ref_type = ref.split(":", 1)[0].strip().lower()
            if type_lower and ref_type != type_lower:
                continue
            if title.lower() == name_lower or name_lower in ref.lower():
                entity_pages.append(props)
            continue

        if type_lower is None and name_lower in title.lower():
            related_pages.append(props)

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

    for md_file in _iter_pages(graph_root):
        props = parse_page_properties(md_file)
        ref = props.get("mistoria-reference", "")
        if not ref:
            continue
        ref_type = ref.split(":", 1)[0].strip().lower()
        if ref_type != type_lower:
            continue
        if filter_lower and filter_lower not in ref.lower():
            continue
        results.append(props)

    return sorted(results, key=lambda p: p.get("name", ""))
