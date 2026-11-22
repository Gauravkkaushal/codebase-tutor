# Learning methodology (Mode B)

Developers who delegate understanding to an AI tend to retain less than those who ask follow-ups and explain back.
So: explain in layers, keep the developer doing some of the thinking, and leave them with a path.

## Explanation framework (for every important explanation)

1. **Purpose** – what problem this code solves, in one sentence.
2. **Context** – where it sits (module, layer, who triggers it).
3. **What it does** – step by step, citing lines.
4. **Why it exists** – design reason; if you infer it, label it; check `git log -L <start>,<end>:<file>` for history.
5. **Inputs** – parameters, request fields, config, env var names.
6. **Outputs** – return values, responses, side effects (DB writes, events, files).
7. **Dependencies** – imports, callees, external packages.
8. **Related concepts** – define unfamiliar terms once (middleware, ORM, JWT, decorator…).
9. **Source evidence** – `ct evidence` excerpts with highlighted lines.
10. **Connections** – called by / calls / depends on / affects, across files.
11. **Edge cases** – branch conditions, error paths, empty/invalid input, concurrency, security.
12. **Next learning step** – one concrete thing to read, run or try.

## Levels

| Level | Shape |
|---|---|
| Beginner | Prerequisites → analogy (only if it helps) → 3–5 small steps with excerpts → checkpoint. Avoid more than one new term per paragraph. |
| Developer | Interfaces and data flow first, then the key excerpt, conventions, patterns, trade-offs. |
| Deep dive | Internals, edge cases, performance, security, failure modes, history, alternatives considered. |
| Contribution | Context table, invariants that must hold, tests to run, conventions to follow, risks. |

Default to the user's level; offer the next level instead of dumping it.

## Checkpoints

Offer one after each concept (more for beginners). Types:
- **Prediction**: "If `user` is null at line 64, what does the browser receive?"
- **Location**: "Which file would you open to change the token lifetime?"
- **Explain-back**: "In two sentences, how does a request reach `login()`?"
Give the answer with citations after they try. Correct precisely and kindly. Store good checkpoints in the explanation
JSON (`checkpoints`, optionally with `choices` + `correct` index) so they appear in the report's Learning Center.

## Learning path

`ct overview` → `learning_path` gives a deterministic starting order (README → entry points → hubs → one route trace →
one test file). Adapt it to the user's goal; a task-driven path beats a generic tour.

## Multilingual teaching

- Hindi: Devanagari, natural sentences, common English technical words allowed (e.g. "फ़ंक्शन", "रिक्वेस्ट").
- Hinglish: Roman script, conversational, English technical terms kept ("ye middleware `next()` call karta hai").
- Never translate code, identifiers, file paths, commands, line numbers, error messages quoted from code.
- Keep technical meaning exact; if a term has no good translation, keep the English term and explain it once.
