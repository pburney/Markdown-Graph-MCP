# ADR-0002: `mistoria-reference::` entity convention for cross-graph linking

**Status:** Accepted
**Date:** 2026-07-07

## Context

ADR-0001 named cross-graph linking/backlinks the flagship feature to build before open-sourcing LogseqMCP — the one capability that actually delivers on "lots of small interconnected knowledge graphs" rather than parallel silos, and something neither LogseqMCP nor the public `mcp-logseq` project had.

This feature also connects to Mistoria, a much larger planned personal life-data architecture (`~/.claude/plans/i-m-realizing-that-herencia-merry-harbor.md`) with an entity model (person/place/object/event/chapter) spanning per-family-member SQLite databases. That plan left cross-database linking explicitly unsolved: "Cross-links between databases use shared entity slugs (e.g., `entity:carol:madrina`). No central registry yet — convention-based." LogseqMCP's file-based, multi-graph architecture is well-positioned to be the first working implementation of that convention-based idea, ahead of Mistoria's own Phase 1/2 build-out.

An initial design draft proposed a `Type/Slug` Logseq namespace (`Person/Carol`) plus a `mistoria-slug::` property keyed `entity:type:slug`. Before implementing it, a check of real data showed the draft was already obsolete: a `Person`/`Place` page had independently been created at `/data/PERSONAL/Daddipedia/pages/Poppy Street.md` with:
```
icon:: 🏡
mistoria-reference:: place:90805:Poppy-Street:2308
```
No `type::` property, no namespace rename — a natural page title plus one property. This settled the design in favor of real usage over the draft.

## Decision

Entity pages use their natural, un-renamed title. A `mistoria-reference::` property is the sole marker of an entity page, with its **first colon-segment naming the type** (`person`, `place`, `object`, `event`, `chapter`) and everything after it a type-specific composite key — not a single fixed shape across types. Places key on address components (`place:{zip}:{street-slug}:{number}`); people would key on name (`person:carol`, or `person:carol-madrina` if disambiguation is needed). There is no requirement that every type share the same number of segments.

This supersedes both the initial draft's `Type/Slug` namespace idea and the Mistoria plan's own original example (`entity:carol:madrina`, an `entity:name:qualifier` shape) — "reference," not "slug," and "type-specific composite key," not a flat slug, are now the standard terms and shape going forward.

Three new MCP tools implement this, sitting alongside the existing `search_content` (free-text) and `find_page` (internal single-graph lookup) rather than replacing them:
- **`get_backlinks(title, graph=None, ...)`** — finds every `[[PageName]]` wikilink reference to a page, across all configured graphs by default.
- **`find_entity(name, type=None, graph=None)`** — existence/reconciliation lookup by title or `mistoria-reference` value/fragment; surfaces near-miss related pages that don't have a `mistoria-reference::` yet, so nothing needs to be pre-migrated before it becomes discoverable.
- **`list_entities(type, graph=None, filter_text=None)`** — enumerates every entity of a given type across graphs, optionally substring-filtered against the reference value (e.g. `filter_text="90805"` for a zip code). This is what a query like "what places does Dad have data on in LA" actually needs — `find_entity`/`get_backlinks` alone only answer "does this one specific thing exist."

## Consequences

- **No forced renames, no migration required.** Existing pages (`David.md`, `Madrina Carol.md` with `type:: #Person`/`alias:: Carol` but no `mistoria-reference::`) keep working today via `find_entity`'s near-miss matching, and can adopt `mistoria-reference::` later with a single `set_property` call whenever Paul chooses to.
- **Piloted in `daddipedia` only** (the default graph, with the most existing person/place pages) — not rolled out to all 6 configured graphs yet.
- **LogseqMCP stays a dumb, syntactic layer.** It parses wikilinks and one property; it does not assign semantics to what an entity *means* (visibility, memories, provenance). That remains Mistoria's job once it exists — see the companion edit to the Mistoria plan file reframing LogseqMCP as a read peer for entity-existence/backlink queries, not purely a downstream renderer.
- **Real gap in test coverage before this ADR:** the type-specific composite key means `list_entities`/`find_entity` can't reuse `search_pages`'s existing exact-match filter semantics (`_matches_filter`) — a full-value exact match would miss `place:90805:...` when filtering on just `type="place"`. New substring-based matching was required (`find_entity_pages`, `list_entity_pages` in `logseq_graphs.py`) rather than reusing `search_pages`.
- **Geographic/proximity queries are explicitly out of scope.** `list_entities`' `filter_text` only does substring matching against whatever's embedded in the reference value — true geocoding/distance logic belongs to Mistoria/Casastoria once that system exists, not to this file-based layer.
