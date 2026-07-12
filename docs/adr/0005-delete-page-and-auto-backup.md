# ADR-0005: `delete_page` and auto-backup-on-overwrite

**Status:** Accepted
**Date:** 2026-07-12

## Context

markdown-graph-mcp had no delete or rename tool at all. Every planned migration that moves pages between graphs (splitting a `dnd` graph and a `bff` knowledge graph out of the overloaded `daddipedia` graph — see the Sèvo PKM-format plan) needed to "read the page, write it to the new location, then manually delete the original file" — with the deletion step happening outside the server, unprotected by any of the safety patterns (read-only checks, atomic writes) the rest of the tool surface already has. `write_page(mode="overwrite")` also had no safety net at all against an accidental clobber beyond the explicit `mode="create"` guard from ADR-0003 — which only helps if the caller thinks to use it.

## Decision

**`delete_page(title, graph=None)`** — a new tool that never hard-deletes. It moves the target file to `<graph_path>/.trash/<timestamp>-<filename>.md`, preserving the existing triple-underscore namespace-filename encoding unchanged, and respects `read_only` exactly like `write_page`/`set_property` (ADR-0003). Returns the trash path so a caller can verify or restore.

**Auto-backup on overwrite** — `write_page(mode="overwrite")` now stashes the pre-overwrite content into the same `.trash/` location, timestamped, *before* replacing it, whenever the target page already existed. `mode="create"` never triggers this (there's nothing to back up — the page didn't exist).

**`.trash/` is a dotdir, which already made it free to implement**: every existing read/search tool (`list_pages`, `search_pages`, `search_content`, `find_backlinks`, `find_entity_pages`, `list_entity_pages`) already skips any path component starting with `.` (originally to skip `logseq/`/`.logseq/`). Trashed and backed-up pages are therefore automatically invisible to every other tool with zero additional filtering code.

**No auto-purge.** `.trash/` grows unbounded for now; an expiry policy is a reasonable future TODO, not needed to unblock the migrations this was built for.

## Consequences

- **Every migration step now has a built-in undo path**, independent of whether the graph happens to be git-tracked at the time (several planned graphs — `sevo`, `dnd`, `bff` — start life with no git history at all).
- **`write_page`'s overwrite path is no longer a silent one-way door.** Combined with `mode="create"` (ADR-0003), there are now two independent safety nets against accidental data loss on write: refuse the write (`create`), or keep a recoverable copy (`overwrite`'s new default backup behavior).
- **No new dependencies, no new config surface** — `.trash/` needs no `config.json` entry; it's created on first use, per graph, exactly like `pages/`/`journals/` are.
- **`.trash/` counts as graph data, not scratch state** — it lives inside the graph directory and gets backed up/synced with everything else, which is the point: recoverability shouldn't depend on a separate, easy-to-forget backup mechanism.
- **This is a soft-delete, not a rename.** Moving a page across *graphs* (the actual migration use case) is still `read_page` → `write_page(mode="create")` → `delete_page` on the source — three calls, not one atomic "move" tool. A dedicated cross-graph move tool was considered and rejected for now: the three-call sequence lets the caller verify the new copy before removing the old one, which matters more here than atomicity.
