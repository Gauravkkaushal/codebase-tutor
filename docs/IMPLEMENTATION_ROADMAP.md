# Implementation Roadmap

| Phase | Scope | Status in v0.1 |
|---|---|---|
| 0 Research & spec | Competitor analysis, agent skill formats, architecture, risks | Done |
| 1 Repository intelligence MVP | Inventory, detection, entry points, Tree-sitter/AST symbols, imports, calls, routes, git snapshots, evidence | Done (JS/TS/Python) |
| 2 Learning & evidence | Overview, architecture facts, symbol/feature exploration, static tracing, explanation framework, evidence-validated explanations | Done |
| 3 Interactive reports | report.md, standalone HTML: architecture explorer, code evidence, flow playback, learning center, language switch | Done |
| 4 Contribution workflow | Context expansion + coverage table, test discovery/planning, review guidance | Done |
| 5 Persistent knowledge & change intelligence | SQLite KB, hash-incremental, snapshots w/ blobs, symbol/behaviour/architecture diffs | Done |
| 6 Simulation lab | L1 inferred flows, L2 test-backed runs, L3 runtime tracing | L1/L2 done, L3 experimental |
| 7 Multilingual & cross-agent | en/hi/hinglish; Claude Code, Codex, Antigravity install docs | Done (Codex/Antigravity untested in-product) |

## Next (v0.2+)

1. Symbol extractors for Go, Java, Rust, C# (Tree-sitter grammars available on PyPI).
2. Optional SCIP index import for compiler-accurate references; LSP fallback.
3. Type-aware TS resolution (TypeScript compiler API via a small Node helper) for method calls on typed objects.
4. Framework plugins: NestJS decorators, Next.js app/pages routes, Django CBVs and URL includes, Spring.
5. Before/after simulation comparison (run the same scenario on baseline and working tree in a git worktree).
6. Runtime tracer: argument/return shape capture (redacted), request lifecycle for HTTP servers.
7. Learner study with real beginners (protocol in VALIDATION.md).
8. Embeddings-based semantic retrieval as an *optional* add-on, justified only if lexical+graph retrieval underperforms.

## Risks

| Risk | Mitigation |
|---|---|
| Static call resolution wrong on dynamic code | Labels + unresolved counts; never draw unresolved edges as verified |
| Large repos slow to parse | Hash incremental, process pool, exclusions, `--paths` scoping |
| Agent writes ungrounded prose | `ct explain add` rejects missing/out-of-range evidence; `ct verify` for Markdown citations |
| Executing repo code is risky | Explicit `--yes` + agent must ask; timeouts; never deploy/publish |
| Translations drift from technical meaning | Identifiers/code/paths never translated; i18n parity test |
