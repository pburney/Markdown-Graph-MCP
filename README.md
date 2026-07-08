# markdown-graph-mcp

A Model Context Protocol server that gives Claude direct read/write access to Logseq-format markdown knowledge graphs — no external dependencies beyond Python itself, no Logseq app required.

Not affiliated with, and not a competitor to, the similarly-scoped [mcp-logseq](https://github.com/ergut/mcp-logseq) project (which talks to Logseq's live app API). This one operates purely on the files — see [docs/adr/0001-file-based-positioning.md](docs/adr/0001-file-based-positioning.md).

## What it does

Point it at one or more Logseq graph directories and Claude gains thirteen tools for working with your notes: capturing thoughts to journals, reading and writing pages, searching by content or properties, listing recent entries, maintaining page metadata, and resolving entity references and backlinks *across* graphs — all against the same `.md` files Logseq reads.

| Tool | What it does |
|------|-------------|
| `list_graphs` | Show all configured graphs and confirm paths exist |
| `capture_to_journal` | Append bullets to a journal page — safe to call while Logseq is open |
| `get_journal` | Read a journal page (today by default) |
| `read_page` | Read any page by title, using `/` for namespaces |
| `write_page` | Write or overwrite a page's full content |
| `search_content` | Full-text keyword search across pages and journals in any/all graphs |
| `search_pages` | Filter pages by property values, return selected fields |
| `list_pages` | List page titles, optionally filtered by namespace prefix |
| `list_recent_journals` | List the N most recent journal entries with a preview |
| `set_property` | Add or update a single property on a page |
| `get_backlinks` | Find every `[[PageName]]` reference to a page, across all configured graphs |
| `find_entity` | Look up an entity by title or `mistoria-reference` value, across all configured graphs |
| `list_entities` | List every entity of a given type (person/place/object/event/chapter) across graphs |

## Quick Start

**Requirements:** Python 3.8+, [Claude Code](https://claude.ai/code)

```bash
git clone https://github.com/pburney/markdown-graph-mcp.git
cd markdown-graph-mcp
cp config.example.json config.json
```

Edit `config.json` to point at your Logseq graph directories (see [Configuration](#configuration)).

Create a virtual environment for the test runner (the server itself needs no packages):

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
```

Register with Claude Code:

```bash
claude mcp add --scope user markdown-graph -- /path/to/markdown-graph-mcp/.venv/bin/python /path/to/markdown-graph-mcp/server.py
```

Verify it's connected:

```bash
claude mcp list
# markdown-graph: ... — ✔ Connected
```

Open a Claude Code session and try it:

```
list my logseq graphs
add this to my journal: MCP server is working
```

## Configuration

`config.json` maps short graph names to filesystem paths:

```json
{
  "default_graph": "notes",
  "graphs": {
    "notes": "/Users/you/Documents/notes",
    "work":  "/Users/you/Documents/work-kb"
  }
}
```

Each key becomes the `graph` argument you (or Claude) use in tool calls. `default_graph` is used when no `graph` argument is provided.

`config.json` is gitignored — copy `config.example.json` to get started. Your graph data never leaves your machine.

### Read-only graphs

A graph entry can be a plain path string (writable, the default) or an object with `read_only: true`:

```json
{
  "graphs": {
    "notes":  "/Users/you/Documents/notes",
    "shared": {"path": "/Users/you/Documents/shared-kb", "read_only": true}
  }
}
```

`capture_to_journal`, `write_page`, and `set_property` return an error and touch nothing when called against a read-only graph. Useful once a graph is shared with a collaborator who shouldn't be able to write to it. A top-level `"read_only": true` forces every configured graph read-only regardless of per-graph settings — handy for a locked-down "viewer" instance.

## Entity conventions

Pages that represent an entity (a person, place, object, event, or chapter) can carry a `mistoria-reference::` property. Its first colon-segment is the type; everything after it is a type-specific key — there's no fixed shape across types. No renaming or namespace is required; the page keeps its natural title.

```
icon:: 🏡
mistoria-reference:: place:90805:Poppy-Street:2308
```

`find_entity`/`list_entities`/`get_backlinks` work whether or not a page has adopted this convention yet — pages without a `mistoria-reference::` still surface as related/near-miss matches by title, so nothing needs to be migrated upfront. See [docs/adr/0002-entity-reference-convention.md](docs/adr/0002-entity-reference-convention.md) for the full rationale.

## Tool Reference

All tools accept an optional `graph` argument (defaults to `default_graph`). Namespace separators in page titles use `/` — the server handles the Logseq triple-underscore filename encoding internally.

### capture_to_journal

```
graph    — graph name (optional)
content  — text to append; lines without "- " are auto-prefixed as bullets
date     — YYYY-MM-DD (optional, defaults to today)
```

Appends to the journal file in append mode — safe to call while Logseq is open and watching the same file.

### read_page / write_page

```
title    — page title, e.g. "Projects/Website Rewrite"
content  — (write_page only) full page content including any properties block
mode     — (write_page only) "overwrite" (default) or "create" (fails if the page already exists)
graph    — graph name (optional)
```

`write_page` with the default `mode="overwrite"` replaces the entire file — use `mode="create"` instead when you want a hard guarantee against clobbering existing content. Use `set_property` for targeted property updates. Blocked on read-only graphs.

### search_content

```
query            — keyword or phrase (case-insensitive substring match)
graph            — graph name (optional, omit to search all configured graphs)
include_journals — also search journal entries (default: true)
context_lines    — lines of surrounding context per match (default: 2)
```

Full-text search across page content and journal entries. Returns matching files with line numbers and surrounding context. Searching all graphs at once is the default — useful when you don't know which graph holds a note.

### search_pages

```
filters      — list of "key=value" strings, AND logic
               e.g. ["type=#Project", "status=#Active"]
return_props — list of property names to include in results
               "name" returns the page title stem, "file" returns the full path
graph        — graph name (optional)
```

Property values are normalized for comparison: `[[PageRef]]` wrappers and `#` prefixes are stripped, matching is case-insensitive.

### list_pages

```
prefix   — optional namespace prefix, e.g. "Projects"
graph    — graph name (optional)
```

### list_recent_journals

```
n      — number of entries to return (default: 7)
graph  — graph name (optional)
```

Returns date, filename, and a short preview of each entry.

### set_property

```
title  — page title
key    — property key, e.g. "status"
value  — property value, e.g. "#Complete"
graph  — graph name (optional)
```

Adds the property if missing; replaces the value if it already exists. Inserted before the first bullet, or appended to the properties block. Written atomically.

### get_backlinks

```
title            — target page title, e.g. "Poppy Street"
graph            — graph name (optional, omit to search all configured graphs)
include_journals — also search journal entries (default: true)
context_lines    — lines of surrounding context per match (default: 1)
```

Finds every page or journal entry that links to `title` via `[[title]]` wikilink syntax. The target doesn't need to exist as a page in every graph searched — it only needs to be referenced.

### find_entity

```
name   — entity name, or a mistoria-reference value/fragment, e.g. "Carol" or "place:90805"
type   — optional entity type filter: person, place, object, event, or chapter
graph  — graph name (optional, omit to check all configured graphs)
```

Reports exact `mistoria-reference::` matches plus related pages that don't carry a reference yet — use before creating a new entity page, to avoid duplicating the same person/place/object across graphs.

### list_entities

```
type         — entity type to list: person, place, object, event, or chapter
graph        — graph name (optional, omit to search all configured graphs)
filter_text  — optional substring to match against the mistoria-reference value
```

Enumerates every entity of a given type. `filter_text` does substring matching only — not geocoding or proximity search.

## Development

```bash
.venv/bin/pytest tests/ -v
```

119 tests across two files:

- `tests/test_logseq_graphs.py` — unit tests for all utility functions, using a minimal fake graph in `tmp_path`
- `tests/test_server.py` — integration tests that run the full MCP protocol over subprocess pipes against the same fixture graph

The server has no runtime dependencies — `pytest` is the only package in `.venv`.

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Server | Pure Python stdlib | No packages to install or version-pin; works in any Python environment |
| Protocol | JSON-RPC over stdio | MCP's stdio transport, implemented directly — no `mcp` SDK or `anyio` |
| Graph access | File I/O on `.md` files | Logseq stores everything as plain markdown; no Logseq process or API needed |
| Tests | pytest | Isolated `tmp_path` fixture graphs; subprocess pipes for end-to-end coverage |

## License

MIT — Copyright (c) 2026 Paul Burney / Burney Web Services
