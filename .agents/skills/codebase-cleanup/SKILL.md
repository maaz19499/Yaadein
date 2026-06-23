---
name: codebase-cleanup
description: Perform a structured, low-risk codebase cleanup across 7 tracks — deduplication, type consolidation, dead code removal, circular dependencies, type strengthening, error handling, and deprecated/AI-slop removal. Use when the user wants to clean up code, improve code quality, remove dead code, fix types, or do a hygiene pass.
---

# Codebase Cleanup

Systematic, low-risk cleanup in 7 focused tracks. Each track follows the same discipline: inspect → assess → rank → implement only high-confidence fixes → verify.

## Principles

1. **Conservative by default.** If a change is ambiguous, skip it.
2. **Rank every change** as HIGH / MEDIUM / LOW confidence before touching code.
3. **Implement only HIGH confidence, LOW risk** changes per track.
4. **Run all checks** (lint, type-check, tests) after each track completes.
5. **Never merge code that merely looks similar** — intent matters more than shape.

## Quick Start

```
1. Pick a track (or run all 7 in order)
2. Follow the track workflow in TRACKS.md
3. Use the checklist in CHECKLISTS.md to verify
4. Commit after each track passes all checks
```

## Track Overview

| # | Track | Goal | Key Tool |
|---|-------|------|----------|
| 1 | [Deduplication](TRACKS.md#track-1-deduplication) | Consolidate repeated logic | grep / semantic search |
| 2 | [Type Consolidation](TRACKS.md#track-2-type-consolidation) | Single source of truth for types | grep `type\|interface\|class` |
| 3 | [Dead Code Removal](TRACKS.md#track-3-dead-code-removal) | Remove confirmed-unused code | knip / vulture |
| 4 | [Circular Dependencies](TRACKS.md#track-4-circular-dependencies) | Break import cycles | madge / pydeps |
| 5 | [Type Strengthening](TRACKS.md#track-5-type-strengthening) | Replace weak types with strong | grep `any\|Any\|unknown` |
| 6 | [Error Handling](TRACKS.md#track-6-error-handling-cleanup) | Stop silent error swallowing | grep `except:\|catch` |
| 7 | [Deprecated & AI Slop](TRACKS.md#track-7-deprecated-code-and-ai-slop) | Remove obsolete code and AI artifacts | manual review |

## Per-Track Workflow

Every track follows this loop:

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌─────────┐
│ INSPECT │───▶│ ASSESS   │───▶│ RANK     │───▶│ IMPLEMENT │───▶│ VERIFY  │
│ the code│    │ critically│    │ by risk  │    │ HIGH only │    │ all     │
└─────────┘    └──────────┘    └──────────┘    └───────────┘    │ checks  │
                                                                └─────────┘
```

1. **Inspect** — Scan using tools and manual review. See [TRACKS.md](TRACKS.md) for track-specific commands.
2. **Assess** — Write a critical assessment of what you found. No fixes yet.
3. **Rank** — Classify every candidate change as HIGH / MEDIUM / LOW confidence.
4. **Implement** — Apply only HIGH-confidence, LOW-risk changes.
5. **Verify** — Run lint, type-check, and tests. See [CHECKLISTS.md](CHECKLISTS.md).

## Language-Specific Commands

### Python
```bash
# Type check
mypy . --strict
# Lint
ruff check .
# Tests
pytest -x
# Dead code
vulture . --min-confidence 80
# Circular deps
pydeps --no-output --show-cycles app/
```

### TypeScript / JavaScript
```bash
# Type check
npx tsc --noEmit
# Lint
npx eslint .
# Tests
npx jest --passWithNoTests
# Dead code
npx knip
# Circular deps
npx madge --circular --extensions ts,js src/
```

## Output

After all tracks complete, produce a summary artifact with:
- Changes made per track (with file links)
- Changes deferred (MEDIUM/LOW confidence, with rationale)
- Check results (pass/fail)

See [TRACKS.md](TRACKS.md) for detailed per-track instructions.
See [CHECKLISTS.md](CHECKLISTS.md) for verification checklists.
