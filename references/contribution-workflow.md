# Contribution workflow (Mode E)

Input may be an issue/PR URL, bug description, feature request, symbol, file or selected code.

1. **Understand the task.** For URLs, read the issue/PR (e.g. `gh issue view <n> --repo owner/name` or a web fetch).
   Restate the expected behaviour and acceptance criteria in two or three lines; confirm if ambiguous.
2. **Locate.** `ct search` with names from the issue; `ct routes` for HTTP behaviour; `ct trace` to see the path.
3. **Expand context.** `ct context <target> --task "<one line>" --text` returns:
   implementation (exact ranges), direct + transitive callers, callees, imports/importers, related types, routes
   reaching the code, ranked tests (with signals), error-handling points, env-var names, security signals,
   affected modules, sibling files (conventions), branch conditions, and a **coverage table**.
4. **Read before claiming.** Open the implementation, every direct caller (or a representative sample if there are
   many, and say so), the top tests, and error handling. Upgrade coverage rows to `Reviewed` only for what you read.
   Example:

   | Area | Status |
   |---|---|
   | Implementation | Reviewed |
   | Callers | Reviewed (4/4) |
   | Tests | Reviewed |
   | Edge cases | Partially reviewed |
   | Cross-module impact | Not fully verified (7 unresolved calls share the name) |

   Never invent completeness percentages.
5. **Teach required concepts** at the user's level (framework features, patterns used here, domain terms).
6. **Plan** following existing conventions (look at sibling files): files to change, functions, tests to add/update,
   migration/config impact, rollout risks. Save as `contribution-plan` explanation if useful.
7. **Implement with the user.** Prefer the user typing the change when they are learning; otherwise make minimal,
   reviewable edits and explain each one. Never touch unrelated files.
8. **Verify.** `ct changes --text` → `ct tests plan <target>` → show command → user approves →
   `ct tests run --yes -- <cmd>`. If dependencies are missing, ask before installing.
9. **Review** (`type: review`): blocking correctness issues → missing tests → security/performance → design →
   style. Each finding has evidence and a concrete fix. No generic praise.
10. **Readiness checklist** (also in the report): can explain current behaviour with citations; read all direct
    callers; know and ran the covering tests; considered branch conditions and error paths; follows conventions; can
    explain what the change does and why.
