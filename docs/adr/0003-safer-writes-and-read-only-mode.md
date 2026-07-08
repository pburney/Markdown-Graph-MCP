# ADR-0003: Safer writes and read-only mode

**Status:** Accepted
**Date:** 2026-07-07

## Context

ADR-0001 flagged two write-safety gaps alongside cross-graph linking: `write_page` silently overwrites existing content with no guard against accidental clobbering, and there was no way to make a graph read-only once it's shared with a collaborator (Jess, or others down the line). Both were deferred until cross-graph linking (ADR-0002) shipped.

## Decision

**Read-only mode**, at two levels of granularity:
- **Per-graph**: a `graphs` entry can be a plain path string (writable, unchanged) or an object `{"path": ..., "read_only": true}`.
- **Global**: a top-level `"read_only": true` in `config.json` forces every configured graph read-only regardless of per-graph settings.

`graph_is_read_only(name)` in `logseq_graphs.py` is the single source of truth (global OR per-graph). `capture_to_journal`, `write_page`, and `set_property` all check it first and return a plain-text error — `"Error: '{graph}' is configured read-only. Write operations are disabled."` — before touching the filesystem. `list_graphs` surfaces the setting with a `[read-only]` marker per graph and a banner line when global mode is on, so it's visible without reading `config.json`.

**Safer writes**: `write_page` gained a `mode` argument — `"overwrite"` (default, existing behavior, unchanged) or `"create"` (fails with a clear error, no write, if the page already exists). Default stays `"overwrite"` rather than flipping to the safer option, to avoid silently changing behavior for any existing caller relying on overwrite semantics — `"create"` is opt-in.

Both features apply only at the three write entry points (`capture_to_journal`, `write_page`, `set_property`); read tools are never blocked by read-only mode.

## Consequences

- **Backward compatible.** Existing `config.json` files with plain path strings and no `read_only` key behave identically — verified against the real 6-graph `config.json`.
- **No new dependencies, no new tools.** Both features extend existing config/tool surface rather than adding new MCP tools, consistent with ADR-0001's zero-dependency, minimal-surface premise.
- **Enables sharing graphs with Jess or other collaborators** without risking accidental writes — a read-only LogseqMCP instance (or a read-only entry for a specific shared graph) can now be configured.
- **`mode="create"` gives agents (Claude, in practice) a way to guarantee non-destructive page creation** — useful when scripting bulk imports or when uncertain whether a page already exists, without needing a separate `find_entity`/`read_page` check first.
- **Global read-only is coarser than per-graph** — if only one of several configured graphs needs to be locked down, per-graph `read_only: true` on that entry is the right tool; global `read_only` is for a fully locked-down "viewer" instance where nothing should ever be written.
