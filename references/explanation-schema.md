# Explanation JSON schema (`ct explain add <file>`)

Explanations are agent-authored, language-separated content tied to evidence. The engine validates them: every
`evidence` entry must point to an existing, non-secret file and an in-range line span; claims without evidence must be
marked `not-verified` or `partially-verified`. On success it stores the document under
`.codebase-tutor/knowledge/explanations/<id>.json`, adds a text hash to each evidence ref, and registers the refs for
staleness tracking.

```jsonc
{
  "id": "auth-login",                 // lowercase, digits, - _ .  (unique; re-adding replaces)
  "type": "explanation",              // explanation | flow-notes | concept | contribution-plan | review
  "level": "beginner",                // beginner | developer | deep-dive | contribution (optional)
  "topic": "feature",                 // free text; "architecture" or id "overview" shows on the Overview page
  "title":   {"en": "How login works", "hi": "…", "hinglish": "…"},   // "en" required
  "summary": {"en": "…markdown…"},
  "sections": [
    {
      "heading": {"en": "1. The route"},
      "body": {"en": "markdown; `path.js:12` citations become links"},
      "evidence": [{"file": "src/app.js", "lines": "10-18", "highlight": "12,14-15", "symbol": "login"}],
      "status": "verified-source",    // verification level for this section
      "kind": "concept"               // optional: concept | analogy | general  (no evidence expected)
    }
  ],
  "claims": [{"text": {"en": "…"}, "evidence": [ … ], "status": "structurally-inferred"}],
  "concepts": [{"term": "middleware", "definition": {"en": "…"}}],
  "checkpoints": [{
    "question": {"en": "…"},
    "choices": {"en": ["A", "B", "C"]},  // optional multiple choice
    "correct": 1,                        // index into choices
    "answer": {"en": "…"},
    "evidence": [ … ]
  }],
  "next_steps": {"en": ["…", "…"]},
  "flow": "flow-id"                    // optional link to a saved flow
}
```

## Flow narration (`type: "flow-notes"`)

```jsonc
{"id": "login-notes", "type": "flow-notes", "flow": "<flow id from ct trace>",
 "title": {"en": "Narration: login"},
 "step_notes": {"4": {"en": "Guard clause…", "hi": "…"}, "7": {"en": "…"}},
 "evidence": [{"file": "src/app.js", "lines": "10-30"}]}
```
Step numbers are the `n` values printed by `ct trace --text`. If you re-trace with a different depth the numbering
changes — update the notes.

## Contribution plans and reviews

Use `type: "contribution-plan"` (implementation plan, concepts, tests, readiness) or `type: "review"` (findings
ordered: blocking correctness → design → style; each with evidence). They appear in the report's Contribution Center.

## Validation without storing

`ct explain validate <file>` returns errors/warnings without writing anything.
