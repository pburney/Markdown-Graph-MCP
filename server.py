#!/usr/bin/env python3
"""markdown-graph-mcp — pure stdlib, no external dependencies. Reads/writes Logseq-format markdown graphs."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import logseq_graphs as lg

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_graphs",
        "description": "List all configured Logseq graphs with their filesystem paths.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "capture_to_journal",
        "description": (
            "Append one or more bullets to a Logseq journal page. "
            "Creates the journal file if it doesn't exist. "
            "Safe to use while Logseq is open — appends without reading the full file. "
            "All captured content is grouped under a single top-level MCP tracking tag block (default: #🦾). "
            "Use Logseq task keywords (TODO, DONE, LATER, NOW, DOING) for task items, not Markdown checkboxes. "
            "Blocked if the graph is configured read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Text to capture. Multi-line strings become multiple bullets grouped under the MCP tag. "
                        "Lines not starting with '- ' are auto-prefixed. "
                        "Preserve tab indentation for nested child blocks."
                    ),
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name (optional, defaults to your configured default_graph).",
                },
                "date": {
                    "type": "string",
                    "description": "Journal date as YYYY-MM-DD (default: today).",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "get_journal",
        "description": "Read a Logseq journal page. Returns the full content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
                "date": {"type": "string", "description": "Journal date as YYYY-MM-DD (default: today)."},
            },
            "required": [],
        },
    },
    {
        "name": "read_page",
        "description": (
            "Read a Logseq page by title. "
            "Use '/' for namespaced pages, e.g. 'AI/Claude' or 'Job Search 2026/Opportunities/Acme'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title. Use '/' for namespaces."},
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "write_page",
        "description": (
            "Write a Logseq page. Creates the page if it doesn't exist. "
            "mode='overwrite' (default) replaces the full content of an existing page — WARNING: destructive. "
            "mode='create' fails instead of overwriting if the page already exists, to avoid clobbering content by mistake. "
            "Blocked if the graph is configured read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title. Use '/' for namespaces."},
                "content": {"type": "string", "description": "Full page content (properties block + bullets)."},
                "mode": {"type": "string", "description": "'overwrite' (default) or 'create' (fails if the page already exists)."},
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "delete_page",
        "description": (
            "Soft-delete a Logseq page: moves it to a `.trash/` directory inside the graph "
            "rather than permanently removing it, so migrations and cleanups have a built-in "
            "undo path. Trashed pages are automatically excluded from every other tool's "
            "searches and listings. Blocked if the graph is configured read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title. Use '/' for namespaces."},
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "search_pages",
        "description": (
            "Search Logseq pages by page-level properties. AND logic across filters. "
            "Returns a table of matching pages with requested properties. "
            "Use 'name' in return_props for the page title, 'file' for the full path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Property filters as 'key=value' strings. AND logic. "
                        "Values are normalized: [[PageRef]] and #Tag prefixes stripped, case-insensitive. "
                        "Example: [\"type=#Opportunity\", \"response=#NoResponse\"]"
                    ),
                },
                "return_props": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Properties to include in results. 'name' = page title stem, 'file' = path.",
                },
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
            },
            "required": ["filters", "return_props"],
        },
    },
    {
        "name": "list_pages",
        "description": "List page titles in a Logseq graph, optionally filtered by namespace prefix.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
                "prefix": {
                    "type": "string",
                    "description": "Optional namespace prefix to filter by, e.g. 'Job Search 2026/Opportunities'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_recent_journals",
        "description": "List the N most recent journal entries with a short preview of each.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
                "n": {"type": "integer", "description": "Number of entries to return (default: 7)."},
            },
            "required": [],
        },
    },
    {
        "name": "search_content",
        "description": (
            "Full-text keyword search across all Logseq pages and journal entries. "
            "Searches page titles and content body. Omit 'graph' to search all configured graphs at once. "
            "Returns matching files with surrounding context lines."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for (case-insensitive substring match).",
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name to scope the search (optional, omit to search all configured graphs).",
                },
                "include_journals": {
                    "type": "boolean",
                    "description": "Also search journal entries (default: true).",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of surrounding context to show per match (default: 2).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "set_property",
        "description": (
            "Set or update a single property on a Logseq page. "
            "Adds the property if missing; replaces the value if it already exists. "
            "Property is inserted before the first bullet, or appended to the properties block. "
            "Blocked if the graph is configured read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title. Use '/' for namespaces."},
                "key": {"type": "string", "description": "Property key, e.g. 'resume-version' or 'status'."},
                "value": {"type": "string", "description": "Property value, e.g. 'v4' or '#Complete'."},
                "graph": {"type": "string", "description": "Graph name (optional, defaults to your configured default_graph)."},
            },
            "required": ["title", "key", "value"],
        },
    },
    {
        "name": "get_backlinks",
        "description": (
            "Find every page or journal entry that links to a given page title via [[PageName]] wikilink syntax. "
            "Omit 'graph' to search all configured graphs at once — the target page doesn't need to exist "
            "in every graph searched, it only needs to be referenced."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Target page title to find backlinks to, e.g. 'Poppy Street'. Matched case-insensitively.",
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name to scope the search (optional, omit to search all configured graphs).",
                },
                "include_journals": {
                    "type": "boolean",
                    "description": "Also search journal entries (default: true).",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of surrounding context to show per match (default: 1).",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "find_entity",
        "description": (
            "Locate every page across configured graphs matching an entity name or a 'mistoria-reference' "
            "property value/fragment (e.g. 'Poppy Street' or 'place:90805'). Reports exact entity-page matches "
            "plus related pages that don't carry a mistoria-reference yet. "
            "Use before creating a new entity page, to avoid duplicating the same person/place/object across graphs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Entity name or mistoria-reference value/fragment to look up, e.g. 'Carol' or 'place:90805'.",
                },
                "type": {
                    "type": "string",
                    "description": "Optional entity type filter: person, place, object, event, or chapter.",
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name to scope the lookup (optional, omit to check all configured graphs).",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_entities",
        "description": (
            "List every page across configured graphs carrying a mistoria-reference:: property of a given type "
            "(person, place, object, event, or chapter). Optionally filter by a substring anywhere in the "
            "reference value, e.g. filter_text='90805' to find places in a given zip code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Entity type to list: person, place, object, event, or chapter.",
                },
                "graph": {
                    "type": "string",
                    "description": "Graph name to scope the listing (optional, omit to search all configured graphs).",
                },
                "filter_text": {
                    "type": "string",
                    "description": "Optional substring to match against the mistoria-reference value.",
                },
            },
            "required": ["type"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _read_only_error(graph_name):
    return f"Error: '{graph_name}' is configured read-only. Write operations are disabled."


def _list_graphs(_args):
    graphs = lg.list_graphs()
    default = lg.default_graph()
    lines = ["Configured Logseq graphs:\n"]
    if lg.read_only_mode():
        lines.append("  (global read-only mode is ON — all writes disabled)\n")
    for name, path in graphs.items():
        marker = " (default)" if name == default else ""
        ro = " [read-only]" if lg.graph_is_read_only(name) else ""
        exists = "✓" if Path(path).exists() else "✗ NOT FOUND"
        lines.append(f"  {name}{marker}{ro}: {path}  {exists}")
    return "\n".join(lines)


def _capture_to_journal(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    if lg.graph_is_read_only(graph_name):
        return _read_only_error(graph_name)
    d = lg.parse_date(args.get("date"))
    content = args.get("content")
    if content is None:
        return "Error: 'content' is required."

    journals = lg.journals_dir(graph_root)
    journals.mkdir(parents=True, exist_ok=True)
    journal_file = journals / lg.journal_filename(d)

    bullets = []
    for line in content.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if not stripped.startswith("- "):
            line = indent + "- " + stripped
        bullets.append(line)

    if not bullets:
        return "Nothing to capture (content was empty after processing)."

    # Wrap all bullets under a single MCP tracking tag block
    tag = lg.mcp_tag()
    output_lines = [f"- {tag}"] + ["\t" + b for b in bullets]

    existed = journal_file.exists()
    needs_newline = (
        existed
        and journal_file.stat().st_size > 0
        and _last_byte(journal_file) != b"\n"
    )

    append_text = ("\n" if needs_newline else "") + "\n".join(output_lines) + "\n"
    with open(journal_file, "a", encoding="utf-8") as f:
        f.write(append_text)

    action = "Created" if not existed else "Appended to"
    return (
        f"{action} {graph_name} journal for {d.isoformat()} ({lg.journal_filename(d)}).\n"
        f"Added {len(bullets)} bullet(s) under {tag}:\n" + "\n".join(output_lines)
    )


def _last_byte(path):
    with open(path, "rb") as f:
        f.seek(-1, 2)
        return f.read(1)


def _get_journal(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    d = lg.parse_date(args.get("date"))
    journal_file = lg.journals_dir(graph_root) / lg.journal_filename(d)
    if not journal_file.exists():
        return f"No journal entry found for {d.isoformat()} in {graph_name}."
    content = journal_file.read_text(encoding="utf-8")
    return f"# {graph_name} journal — {d.isoformat()}\nFile: {journal_file}\n\n{content}"


def _read_page(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    title = args.get("title")
    if not title:
        return "Error: 'title' is required."
    page_file = lg.find_page(graph_root, title)
    if page_file is None:
        return f"Page {title!r} not found in {graph_name}."
    content = page_file.read_text(encoding="utf-8")
    display_title = lg.filename_to_title(page_file.stem)
    return f"# {display_title} ({graph_name})\nFile: {page_file}\n\n{content}"


def _write_page(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    if lg.graph_is_read_only(graph_name):
        return _read_only_error(graph_name)
    title = args.get("title")
    if not title:
        return "Error: 'title' is required."
    content = args.get("content")
    if content is None:
        return "Error: 'content' is required."
    mode = args.get("mode", "overwrite")
    if mode not in ("overwrite", "create"):
        return f"Error: invalid mode {mode!r}. Use 'overwrite' or 'create'."

    pages = lg.pages_dir(graph_root)
    pages.mkdir(parents=True, exist_ok=True)
    page_file = lg.page_path(graph_root, title)
    existed = page_file.exists()

    if mode == "create" and existed:
        return (
            f"Error: page {title!r} already exists in {graph_name}. "
            f"Use mode='overwrite' to replace it, or read_page/set_property for targeted edits."
        )

    backup_note = ""
    if existed:
        backup_path = lg.backup_page_file(page_file, graph_root)
        backup_note = f" Previous content backed up to {backup_path}."

    page_file.write_text(content, encoding="utf-8")
    action = "Created" if not existed else "Updated"
    return f"{action} page {title!r} in {graph_name} ({page_file.name}).{backup_note}"


def _delete_page(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    if lg.graph_is_read_only(graph_name):
        return _read_only_error(graph_name)
    title = args.get("title")
    if not title:
        return "Error: 'title' is required."
    page_file = lg.find_page(graph_root, title)
    if page_file is None:
        return f"Page {title!r} not found in {graph_name}."
    trash_path = lg.delete_page_file(page_file, graph_root)
    return f"Moved {title!r} to trash in {graph_name}: {trash_path}"


def _search_pages(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    raw_filters = args.get("filters", [])
    return_props = args.get("return_props", ["name"])

    # Accept list of "key=value" strings or a single comma-joined string
    if isinstance(raw_filters, str):
        raw_filters = [f.strip() for f in raw_filters.split(",")]

    filters = []
    for f in raw_filters:
        if "=" not in f:
            return f"Invalid filter {f!r} — must be 'key=value'."
        key, _, val = f.partition("=")
        filters.append((key.strip().lower(), val.strip()))

    results = lg.search_pages(graph_root, filters, return_props)

    if not results:
        return f"No pages matched in {graph_name}."

    # Format as aligned table
    cols = return_props
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in results)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    rows = [header, sep]
    for r in results:
        rows.append("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
    rows.append(f"\n{len(results)} page(s) found in {graph_name}.")
    return "\n".join(rows)


def _list_pages(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    prefix = args.get("prefix")
    titles = lg.list_page_titles(graph_root, prefix)
    if not titles:
        label = f"with prefix '{prefix}' " if prefix else ""
        return f"No pages {label}found in {graph_name}."
    header = f"{len(titles)} page(s) in {graph_name}"
    if prefix:
        header += f" under '{prefix}'"
    return header + ":\n" + "\n".join(titles)


def _list_recent_journals(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    n = int(args.get("n", 7))
    entries = lg.list_recent_journals(graph_root, n)
    if not entries:
        return f"No journal entries found in {graph_name}."
    lines = [f"Recent journals in {graph_name}:\n"]
    for date_str, path, preview in entries:
        lines.append(f"  {date_str} ({path.name})")
        for p in preview:
            lines.append(f"    {p}")
        if not preview:
            lines.append("    (empty)")
    return "\n".join(lines)


def _search_content(args):
    query = args.get("query", "").strip()
    if not query:
        return "Error: 'query' is required."

    include_journals = bool(args.get("include_journals", True))
    context_lines = int(args.get("context_lines", 2))
    graph_param = args.get("graph")

    if graph_param:
        graph_name, graph_root = lg.resolve_graph(graph_param)
        graphs_to_search = [(graph_name, graph_root)]
    else:
        graphs_to_search = _all_graphs()

    all_results = []
    graphs_searched = []
    for graph_name, graph_root in graphs_to_search:
        graphs_searched.append(graph_name)
        for hit in lg.search_content(graph_root, query, include_journals=include_journals, context_lines=context_lines):
            hit["graph"] = graph_name
            all_results.append(hit)

    if not all_results:
        return f"No matches for {query!r} in: {', '.join(graphs_searched)}."

    lines = [
        f"Search: {query!r}",
        f"Graphs searched: {', '.join(graphs_searched)}",
        f"Files with matches: {len(all_results)}",
        "",
    ]
    for hit in all_results:
        lines.append(f"## [{hit['graph']}] {hit['type'].upper()}: {hit['title']}")
        lines.append(f"   File: {hit['file']}")
        for m in hit["matches"]:
            for c in m["context_before"]:
                lines.append(f"     | {c}")
            lines.append(f"   > L{m['line_number']}: {m['line']}")
            for c in m["context_after"]:
                lines.append(f"     | {c}")
        lines.append("")
    return "\n".join(lines)


def _set_property(args):
    graph_name, graph_root = lg.resolve_graph(args.get("graph"))
    if lg.graph_is_read_only(graph_name):
        return _read_only_error(graph_name)
    title = args.get("title")
    if not title:
        return "Error: 'title' is required."
    key = args.get("key")
    if not key:
        return "Error: 'key' is required."
    key = key.lower().strip()
    value = args.get("value")
    if value is None:
        return "Error: 'value' is required."

    page_file = lg.find_page(graph_root, title)
    if page_file is None:
        page_file = lg.page_path(graph_root, title)

    old_value, action = lg.set_page_property(page_file, key, value)

    if action == "updated":
        return f"Updated '{key}' on '{title}' in {graph_name}: '{old_value}' → '{value}'."
    else:
        return f"Added '{key}:: {value}' to '{title}' in {graph_name}."


def _all_graphs():
    return [(name, Path(path)) for name, path in lg.list_graphs().items()]


def _get_backlinks(args):
    title = args.get("title", "").strip()
    if not title:
        return "Error: 'title' is required."

    include_journals = bool(args.get("include_journals", True))
    context_lines = int(args.get("context_lines", 1))
    graph_param = args.get("graph")

    if graph_param:
        graph_name, graph_root = lg.resolve_graph(graph_param)
        graphs_to_search = [(graph_name, graph_root)]
    else:
        graphs_to_search = _all_graphs()

    all_results = []
    graphs_searched = []
    for graph_name, graph_root in graphs_to_search:
        graphs_searched.append(graph_name)
        for hit in lg.find_backlinks(graph_root, title, include_journals=include_journals, context_lines=context_lines):
            hit["graph"] = graph_name
            all_results.append(hit)

    if not all_results:
        return f"No backlinks to {title!r} found in: {', '.join(graphs_searched)}."

    lines = [
        f"Backlinks to {title!r}:",
        f"Graphs searched: {', '.join(graphs_searched)}",
        "",
    ]
    for hit in all_results:
        lines.append(f"## [{hit['graph']}] {hit['type'].upper()}: {hit['title']}")
        lines.append(f"   File: {hit['file']}")
        for m in hit["matches"]:
            for c in m["context_before"]:
                lines.append(f"     | {c}")
            lines.append(f"   > L{m['line_number']}: {m['line']}")
            for c in m["context_after"]:
                lines.append(f"     | {c}")
        lines.append("")
    return "\n".join(lines)


def _find_entity(args):
    name = args.get("name", "").strip()
    if not name:
        return "Error: 'name' is required."
    type_filter = args.get("type")
    graph_param = args.get("graph")

    if graph_param:
        graph_name, graph_root = lg.resolve_graph(graph_param)
        graphs_to_search = [(graph_name, graph_root)]
    else:
        graphs_to_search = _all_graphs()

    header = f"Entity lookup: {name!r}"
    if type_filter:
        header += f" (type: {type_filter})"
    lines = [header]
    found_any = False

    for graph_name, graph_root in graphs_to_search:
        result = lg.find_entity_pages(graph_root, name, type_filter)
        entity_pages = result["entity_pages"]
        related_pages = result["related_pages"]
        if not entity_pages and not related_pages:
            continue
        found_any = True
        lines.append(f"\n## {graph_name}")
        for p in entity_pages:
            ref = p.get("mistoria-reference", "")
            icon = p.get("icon", "")
            prefix = f"{icon} " if icon else ""
            lines.append(f"   {prefix}{p.get('name', '')}  [{ref}]")
        if related_pages:
            lines.append(f"   No entity page found, but {len(related_pages)} related page(s) exist:")
            for p in related_pages:
                lines.append(f"     {p.get('name', '')}")

    if not found_any:
        searched = ", ".join(g for g, _ in graphs_to_search)
        return f"No matches for {name!r} in: {searched}."
    return "\n".join(lines)


def _list_entities(args):
    type_filter = args.get("type", "").strip()
    if not type_filter:
        return "Error: 'type' is required."
    filter_text = args.get("filter_text")
    graph_param = args.get("graph")

    if graph_param:
        graph_name, graph_root = lg.resolve_graph(graph_param)
        graphs_to_search = [(graph_name, graph_root)]
    else:
        graphs_to_search = _all_graphs()

    header = f"Entities of type {type_filter!r}"
    if filter_text:
        header += f" matching {filter_text!r}"
    lines = [header + ":"]
    total = 0

    for graph_name, graph_root in graphs_to_search:
        results = lg.list_entity_pages(graph_root, type_filter, filter_text)
        if not results:
            continue
        lines.append(f"\n## {graph_name} ({len(results)})")
        for p in results:
            ref = p.get("mistoria-reference", "")
            icon = p.get("icon", "")
            prefix = f"{icon} " if icon else ""
            lines.append(f"   {prefix}{p.get('name', '')}  [{ref}]")
        total += len(results)

    if total == 0:
        searched = ", ".join(g for g, _ in graphs_to_search)
        return f"No {type_filter!r} entities found in: {searched}."
    return "\n".join(lines)


HANDLERS = {
    "list_graphs": _list_graphs,
    "search_content": _search_content,
    "capture_to_journal": _capture_to_journal,
    "get_journal": _get_journal,
    "read_page": _read_page,
    "write_page": _write_page,
    "delete_page": _delete_page,
    "search_pages": _search_pages,
    "list_pages": _list_pages,
    "list_recent_journals": _list_recent_journals,
    "set_property": _set_property,
    "get_backlinks": _get_backlinks,
    "find_entity": _find_entity,
    "list_entities": _list_entities,
}

# ---------------------------------------------------------------------------
# Minimal MCP / JSON-RPC server (stdio, no external deps)
# ---------------------------------------------------------------------------

def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")

    # Notifications — no response
    if msg_id is None:
        return

    if method == "initialize":
        _send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "markdown-graph-mcp", "version": "1.0"},
            },
        })

    elif method == "tools/list":
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})

    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = HANDLERS.get(name)
        if handler is None:
            _send({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name!r}"},
            })
            return
        try:
            text = handler(arguments)
        except Exception as e:
            text = f"Error in {name!r}: {type(e).__name__}: {e}"
        _send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": text}]},
        })

    else:
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method!r}"},
        })


async def main():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    while True:
        try:
            line = await reader.readline()
        except Exception:
            break
        if not line:
            break
        line = line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            _handle(msg)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
