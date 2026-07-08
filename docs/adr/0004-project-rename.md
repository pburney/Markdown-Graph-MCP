# ADR-0004: Rename LogseqMCP to markdown-graph-mcp

**Status:** Accepted
**Date:** 2026-07-08

## Context

The project was originally named LogseqMCP. Two independent problems surfaced with that name once open-sourcing got closer:

1. **Direct naming collision.** A completely different, unrelated, actively-maintained public project exists at `github.com/ergut/mcp-logseq` — same two words, reversed order. It has a different architecture (talks to Logseq's live app API; see ADR-0001) and a different feature set. A near-identical name invites exactly the "which one do I install" confusion a prospective user shouldn't have to resolve, and undersells the architectural difference ADR-0001 spent a whole document establishing.
2. **The name no longer described the project.** ADR-0001 already committed to positioning this as a headless, file-based knowledge-graph substrate rather than a Logseq app companion — per Paul's stated vision, some graphs built with this tool may never be opened in the Logseq app at all. "LogseqMCP" implies the opposite: that Logseq the application is the point.

Before renaming, two research questions were checked rather than assumed:
- **Was the file-format handling actually correct**, or had it just been reverse-engineered from whatever existing graphs looked like? Checked against official Logseq documentation (via the `logseq/docs` GitHub repo) — confirmed the required layout is `pages/`, `journals/`, `logseq/` (`config.edn`, `metadata.edn`, `custom.css`, `custom.js`), with `assets/` optional. All six of Paul's real graphs match this, and this project's page/journal handling, namespace encoding, and directory-skip logic all line up correctly. The one gap: nothing bootstraps a brand-new graph's `logseq/` directory, because no "new graph" tool exists yet (tracked in `TODO.md`).
- **Should the project instead generalize to `LocalKnowledgeGraphMCP`**, supporting Obsidian/Foam/Dendron-style markdown too? Rejected for now: those tools use YAML frontmatter, not Logseq's `key:: value` block properties, and have no outliner/block model (which `capture_to_journal`'s indentation handling depends on) — real engineering cost with no current need (all of Paul's graphs are Logseq). Separately, "knowledge graph MCP" is already a crowded, differently-scoped category (in-memory entity/relation stores for AI persistent memory — `mcp-knowledge-graph`, `knowledgegraph-mcp`, `graphiti`, etc., none of them file-based) — going fully generic would trade one naming collision for a worse one. The architecture doesn't preclude adding other markdown formats later if a real need arises; nothing here was built to make that harder.

## Decision

Renamed to **markdown-graph-mcp** — plain and descriptive rather than evocative, per Paul's preference ("this is more of a utility"). No format-support broadening; still Logseq-format only.

Renamed as part of this change:
- Project directory: `/data/BUSINESS/Burnilab/LogseqMCP/` → `/data/BUSINESS/Burnilab/markdown-graph-mcp/`
- MCP protocol `serverInfo.name`: `logseq-mcp` → `markdown-graph-mcp`
- Claude Code MCP registration key: `logseq` → `markdown-graph` (re-registered via `claude mcp remove`/`claude mcp add`, since `~/.claude.json` should be managed through the CLI, not hand-edited)
- README title, clone URL, and registration example
- `TODO.md` heading and GitHub URL reference

Not renamed: ADR-0001 through ADR-0003 keep referring to "LogseqMCP" in their own prose. ADRs are point-in-time decision records — rewriting them to say "markdown-graph-mcp" would misrepresent what the project was called when those decisions were made. This ADR is the pointer from the old name to the new one.

## Consequences

- **No functional changes** — this is a pure rename; all 119 tests pass unchanged from the new location.
- **Live MCP registration was updated**, not just the repo — anyone (any session, on this or other machines) referencing the old `logseq` registration key needs to pick up the new `markdown-graph` key. BFF's planned integration (`TODO.md`'s "BFF integration" section) was never wired up yet, so no other project's config needed fixing.
- **The mcp-logseq collision is resolved** — the names no longer read as variants of each other.
- **"Logseq" still appears throughout** — in the README's description, in tool names like nothing (none of the 13 tools have "logseq" in their name), in `mistoria-reference::`'s design rationale, and in this ADR's own text — intentionally. The project still only supports Logseq's file format; the rename fixes the identity confusion, not the scope.
