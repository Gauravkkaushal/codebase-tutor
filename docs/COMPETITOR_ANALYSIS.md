# Competitor Analysis — Codebase Tutor

Research date: 2026-11-20. Sources are linked inline; claims about third-party tools reflect their public
documentation and reviews on that date and may change. Benchmarks quoted by vendors were **not** reproduced.

## 1. Summary

The structural problem ("parse a repo into a graph an agent can query") is largely solved and commoditised:
several MIT/Apache tools parse with Tree-sitter into SQLite or JSON and expose the graph to agents.
What is **not** solved well:

1. **Line-level evidence with verification status.** Most tools show a node's code or a wiki page with links, but
   do not attach every claim to an exact, hash-checked line range, nor label *how* a relationship is known
   (parsed vs. inferred vs. test-observed vs. runtime-observed).
2. **Teaching, not summarising.** Wikis and graphs describe what exists. Few tools sequence learning
   (prerequisites → walkthrough → checkpoint) or measure whether the developer understood.
3. **The loop after the change.** "What did my change do?" — symbol-level diff, behaviour signals,
   affected callers/routes/tests, and *real* test execution with honest pass/fail — is rare outside
   heavyweight enterprise tooling.
4. **Indian-language learners.** Localisation, where present, targets en/zh/ja/ko/ru/vi; none found for Hindi or Hinglish.

Codebase Tutor therefore differentiates on **evidence-backed interactive learning + contribution preparation +
post-change verification**, and reuses the commodity idea (deterministic parsing into a local SQLite graph)
rather than competing on it.

## 2. Tool-by-tool

### Understand Anything (Egonex-AI / Lum1104) — MIT
- Claude Code plugin (also Codex, Cursor, Copilot, Gemini CLI…) that turns a repo into an interactive knowledge graph.
  ([GitHub](https://github.com/Egonex-AI/Understand-Anything))
- Five-agent pipeline (scanner, file analyzer, architecture analyzer, tour builder, graph reviewer). Tree-sitter
  does deterministic parsing (imports, exports, definitions, call sites); the LLM does summaries, layers, tours.
- Incremental re-runs via fingerprints; optional post-commit hook; `/understand-diff` shows impact of uncommitted changes.
- Dashboard with layers, search, clickable nodes, persona levels; `--language` supports en, zh, zh-TW, ja, ko, ru, vi.
- Limits stated by the project: large token cost on first run for big repos; huge monorepos should be scoped;
  graphs > 10 MB suggested for git-lfs. Its README does not describe line-level citations.
- **Takeaway:** strongest direct competitor for "graph + tour". Gaps we target: per-claim line evidence with
  hash staleness, verification taxonomy, test/runtime-backed simulation, Hindi/Hinglish, contribution readiness.

### DeepWiki (Cognition / Devin) — proprietary; free for public repos
- Auto-indexes repos into wikis with architecture diagrams, source links and summaries; "Ask Devin" Q&A uses the wiki.
  ([Devin docs](https://docs.devin.ai/work-with-devin/deepwiki))
- Large repos hit built-in limits; `.devin/wiki.json` steers which pages get written.
- Public version + DeepWiki MCP give basic docs and Q&A; full experience in the Devin app.
- **Takeaway:** excellent breadth, hosted. Not local/offline, not change-aware for your working tree, no
  execution-backed verification, documentation-first rather than learning-first.

### RepoPrompt (CE: Apache-2.0)
- Builds focused context from files, CodeMaps (signatures), repo structure and git diffs, handed to agents; has an
  MCP server. ([README](https://raw.githubusercontent.com/repoprompt/repoprompt-ce/main/README.md))
- Context Builder: discovery agent → token-budgeted file selection → structured prompt.
  ([review](https://rywalker.com/research/repo-prompt))
- **Takeaway:** best-in-class *context selection* for agents; it does not teach or visualise flows. We borrow the
  idea of signature-level "codemaps" and token budgets for targeted retrieval.

### CodeGraph (colbymchenry) and similar graph MCP servers — MIT
- Tree-sitter AST → symbols, call graphs, imports, references in local SQLite + FTS5; no embeddings; exposed via MCP.
  ([review](https://dev.to/andrew-ooo/codegraph-review-pre-indexed-knowledge-graph-for-ai-agents-af1),
  [site](https://colbymchenry.github.io/codegraph/))
- Related: codebase-memory-mcp (single Go binary, Tree-sitter, persistent graph, no built-in LLM —
  [pkg.go.dev](https://pkg.go.dev/github.com/DeusData/codebase-memory-mcp@v0.3.1)); the Codebase-Memory paper
  (66 languages, SQLite, multi-strategy call resolution — [arXiv 2603.27277](https://arxiv.org/pdf/2603.27277)).
- **Takeaway:** validates our storage choice (local SQLite, deterministic parsing, LLM only as the explanation layer).
  These are agent back-ends; none target human learning or report generation.

### Sourcegraph — commercial (precise nav on Enterprise)
- Precise code navigation via SCIP indexes (compiler-accurate go-to-definition / find-references, cross-repo);
  falls back to search-based navigation. ([docs](https://sourcegraph.com/docs/code-navigation/precise-code-navigation))
- **Takeaway:** the accuracy ceiling for references. Our Tree-sitter resolution is heuristic by comparison, so we
  label it honestly and design an optional SCIP import path (roadmap) rather than claiming precision.

### "Codebase Explorer"-style skills (several, mostly prompt-only)
- e.g. quicksilversurfer's *codebase-explorer* (vertical slices, "trust the trace" philosophy —
  [skills.sh](https://skills.sh/quicksilversurfer)), Correctless `/cexplain` (Mermaid + prose, HTML export,
  grep fallback without Serena — [docs](https://joshft.github.io/correctless/skills/cexplain)), SocratiCode
  (hybrid search + graph, offline HTML explorer — [skills.sh](https://skills.sh/giancarloerra/socraticode/codebase-exploration)),
  codebase-visualizer (HTML tree maps — [mcpmarket](https://mcpmarket.com/tools/skills/codebase-visualizer-1)).
- **Takeaway:** good pedagogy ideas (vertical slices, guided drill-down) but rely on the model reading files;
  little persistence, no change intelligence, no verification taxonomy.

### The user's earlier `codebase-mentor` skill (v0.1, in this Project)
- Strong pedagogy: layered explanations, checkpoints, learner profile, `path:line` citations with a verifier,
  Verified/Inferred/Unknown labels. Codebase Tutor keeps these principles and adds the deterministic engine,
  persistent knowledge base, interactive report, change intelligence and simulation lab.

## 3. Capability matrix

| Capability | Understand Anything | DeepWiki | RepoPrompt | CodeGraph-class | Sourcegraph | **Codebase Tutor (this release)** |
|---|---|---|---|---|---|---|
| Deterministic parsing | Tree-sitter | undisclosed | CodeMaps | Tree-sitter | SCIP (precise) | Tree-sitter + Python `ast` |
| Persistent local index | JSON graph | hosted | app state | SQLite | server | SQLite + content-addressed snapshots |
| Incremental updates | yes | re-index | n/a | yes | CI upload | hash-based, resumable |
| Line-level evidence w/ staleness check | not stated | links | slices | snippets | precise ranges | **yes (hash-verified)** |
| Verification taxonomy (parsed/inferred/test/runtime) | no | no | no | no | precise vs search | **yes** |
| Execution-flow playback | tours | diagrams | no | trace tool | no | **static flows w/ branches; runtime events** |
| Test-backed verification | no | no | no | no | no | **approval-gated runs, honest results** |
| Change impact | `/understand-diff` | no | git diff context | impact tool | refs | **symbol diff + behaviour signals + callers/routes/tests** |
| Standalone HTML report | dashboard (Node) | web | no | no | web | **single folder, opens from file://** |
| Hindi / Hinglish | no | no | no | no | no | **yes (UI + templated text; agent-authored content per language)** |
| Licence | MIT | proprietary | Apache-2.0 | MIT | commercial | MIT |

## 4. What remains hard (honest)

- Dynamic dispatch, dependency injection, reflection, config-driven routing and metaprogramming defeat static call
  resolution. We mark such edges *structurally inferred* or *unresolved* and surface the count.
- Precise cross-language and cross-service tracing needs build-aware indexers (SCIP, LSP). Planned as optional input.
- Runtime instrumentation is language-specific; this release ships Python (`sys.setprofile`) and Node (require-hook)
  tracers marked **experimental**.
- Measuring learning requires real learners; the protocol is in `VALIDATION.md` but no learner study has been run yet.
