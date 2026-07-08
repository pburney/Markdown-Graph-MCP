# ADR-0001: File-based, headless positioning (vs. mcp-logseq's live-API integration)

**Status:** Accepted
**Date:** 2026-07-07

## Context

Before open-sourcing LogseqMCP, we compared it against `mcp-logseq` (github.com/ergut/mcp-logseq), a public, actively maintained MCP server occupying similar ground: giving an LLM agent access to a Logseq graph.

The two projects turned out to be architecturally different, not just different in scope:

- **LogseqMCP** reads/writes a graph's `.md` files directly. No dependency on the Logseq app being open. Zero runtime dependencies (pure Python stdlib), hand-rolled JSON-RPC/stdio. Natively supports multiple named graphs from one config file. 10 tools at page/journal granularity. 70 tests, no CI, not yet a public git history.
- **mcp-logseq** talks to Logseq's live local HTTP API (the app must be running with its API server enabled and a token generated). Uses the official `mcp` SDK plus `requests`/`starlette`/`uvicorn`. One graph per process (with an HTTP "multi-profile" workaround for scoped access to a single graph). 16+ tools including block-level CRUD by UUID, namespace trees, backlinks, raw Datascript queries, and optional semantic/vector search (LanceDB + Ollama) and Logseq DB-mode support. 105 commits since Dec 2024, active contributors, changelog/roadmap, 226 tests.

On feature count and maturity alone, mcp-logseq is well ahead — it has roughly 18 months and multiple contributors behind it. Trying to open-source LogseqMCP as a competing, feature-equivalent alternative would mean playing catch-up in a space someone else already occupies well.

Full comparison detail: `~/.claude/projects/-data-BUSINESS-Burnilab/memory/reference_mcp_logseq_comparison.md`.

## Decision

Open-source LogseqMCP as what it already is architecturally, not as a feature-competitive alternative: a **zero-dependency, file-based tool for using Logseq's markdown + `key:: value` format as a headless knowledge-graph substrate for AI agents** — including graphs that may never be opened in the Logseq app at all.

This reframes the pitch from "Logseq MCP server, but simpler" to "Logseq's file format as a lightweight, greppable, git-friendly knowledge-graph format for agents," aimed at a use case mcp-logseq's live-API design structurally can't serve: many small, scriptable, possibly-headless graphs, read/written directly by Claude.

Concretely, this means:
- Leading the README with the headless/no-app-required framing, not a tool-for-tool comparison table
- Prioritizing features that serve *this* use case (cross-graph linking, safer writes, read-only mode — see `TODO.md`) over chasing mcp-logseq's feature list
- Explicitly not building vector search, DB-mode support, or a networked transport — each would compromise the zero-dependency, local-first, file-based premise that is the actual differentiator

## Consequences

- **Lower maintenance burden**: no SDK version churn, no dependency on Logseq's API stability across app versions, no auth/token management.
- **Works in more places**: cron jobs, headless machines, CI, or any context where Logseq isn't installed or running — this is the capability mcp-logseq cannot offer by design.
- **Real capability gaps remain**: no block-level editing precision, no ACL/privacy controls, no semantic search, no DB-mode graphs. These are accepted trade-offs, not oversights — see "Explicitly not planned" in `TODO.md`. If a use case genuinely needs live-app integration or semantic search, mcp-logseq is the better tool, and that's fine.
- **Cross-graph linking becomes the flagship feature to build**, since it's the one capability that directly serves the "lots of small interconnected knowledge graphs" vision and doesn't exist in either project today.
- **No urgency to match mcp-logseq's release cadence** — the two projects now have different audiences and different jobs to be done, so its roadmap isn't a competitive threat to track.
