# markdown-graph-mcp — To Do

Renamed from LogseqMCP on 2026-07-08 — see [docs/adr/0004-project-rename.md](docs/adr/0004-project-rename.md).

## Open-source prep
- [x] `git init` + first commit — done 2026-07-08
- [x] README leads with the headless/no-app-required positioning and links ADR-0001 — done as part of the rename
- [x] Add a real `LICENSE` file (MIT) — done 2026-07-08
- [x] Confirm `config.json` stays gitignored; `config.example.json` is the only config that ships — verified, already correct
- [x] Scrub hardcoded paths (`/data/BUSINESS/...`, `/data/PERSONAL/...`) from source, tests, and docs — verified clean; only historical mentions remain in TODO.md/ADRs
- [x] Push to GitHub — done 2026-07-08, `github.com/pburney/Markdown-Graph-MCP.git`
- [x] Add CI (pytest on push) — done 2026-07-08, `.github/workflows/tests.yml` matrix over 3.11/3.12/3.13

## Candidate features (from the mcp-logseq comparison — see docs/adr/0001)
- [x] **Cross-graph linking / backlinks** — done. `get_backlinks`, `find_entity`, and `list_entities` tools added, keyed off a `mistoria-reference::` page property (`type:detail...`, e.g. `place:90805:Poppy-Street:2308`) rather than a forced page-title/namespace convention. See [docs/adr/0002-entity-reference-convention.md](docs/adr/0002-entity-reference-convention.md).
- [x] **Read-only mode** — done. A graph entry in `config.json` can be `{"path": ..., "read_only": true}`, or a top-level `"read_only": true` forces every graph read-only. `capture_to_journal`/`write_page`/`set_property` return an error and touch nothing on a read-only graph. See [docs/adr/0003-safer-writes-and-read-only-mode.md](docs/adr/0003-safer-writes-and-read-only-mode.md).
- [x] **Safer writes** — done. `write_page` takes `mode="overwrite"` (default, unchanged) or `mode="create"` (fails without touching the file if the page already exists). See ADR-0003.
- [ ] **New-graph bootstrap command** — no tool creates a graph from scratch today; all tools operate on graphs already listed in `config.json`. Confirmed against official Logseq docs (2026-07-08): a real graph needs `pages/`, `journals/`, and a `logseq/` directory (`config.edn`, `metadata.edn`, `custom.css`, `custom.js`); `assets/` is optional. If a `new_graph` tool is built, decide whether to bootstrap the `logseq/` dir (so the app can open it later) or skip it entirely for graphs that are meant to stay headless forever — needs a decision either way, don't assume.
- [ ] **Block-level addressing** — investigate a lightweight alternative to Logseq's live block UUIDs (e.g. line-number or heading-path addressing) for precise in-page edits without requiring the app to ever assign real block IDs.
- [ ] Tag/namespace exclusion (ACL) — lower priority; revisit only if graphs get shared beyond Paul/Jess.
- [ ] **Concurrent-write safety** — `write_page`/`set_property`/`capture_to_journal` do plain unlocked file writes; two agents (or clients — now that other MCP clients beyond Claude Code can register this server, see README) writing the same page at once can clobber each other. Deferred until there's an actual multi-source setup in use; revisit then rather than pre-building file locking for a currently-single-writer tool.

## Explicitly not planned (see ADR-0001)
- Vector/semantic search (LanceDB + embeddings) — heavy dependency footprint, contradicts the zero-dependency premise
- Logseq DB-mode graph support — requires a running Logseq instance and Datascript queries, contradicts the headless premise
- Networked HTTP/SSE transport — out of scope for a personal/local-first tool

## BFF integration
- [ ] Register in BFF's MCP config
- [ ] Update BFF `CLAUDE.md`
- [ ] Default graph: `daddipedia`
