# Verification Checklists

Use these checklists after completing each track. **Do not move to the next track until all checks pass.**

---

## Pre-Flight (Before Starting ANY Track)

- [ ] All tests pass on the current branch
- [ ] No uncommitted changes (start from a clean state)
- [ ] Type checker passes cleanly
- [ ] Linter passes cleanly
- [ ] Create a new branch or commit point to roll back to

---

## Track 1: Deduplication

### After Implementation
- [ ] All extracted shared functions have clear, descriptive names
- [ ] No stale imports remain at old call sites
- [ ] No copy of the original duplicated code remains (unless intentionally kept with rationale)
- [ ] Shared functions live in a logical location (not shoved into a random utils file)
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `refactor: deduplicate [description]`

---

## Track 2: Type Consolidation

### After Implementation
- [ ] Each consolidated type has exactly ONE canonical definition
- [ ] All imports point to the canonical location
- [ ] No type name collisions remain
- [ ] Merged types preserve all required fields from all sources
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `refactor: consolidate [type names] into [location]`

---

## Track 3: Dead Code Removal

### Before Removing Each Item
- [ ] Verified: not referenced in any config file
- [ ] Verified: not a framework convention (migration, fixture, hook)
- [ ] Verified: not dynamically imported
- [ ] Verified: not registered as an entry point

### After Implementation
- [ ] All imports to removed code are cleaned up
- [ ] Tests for removed code are also removed
- [ ] No new `ImportError` or `ModuleNotFoundError` at runtime
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `chore: remove dead code [description]`

---

## Track 4: Circular Dependencies

### After Implementation
- [ ] Cycle detection tool reports zero cycles (or fewer than before)
- [ ] Extracted shared modules contain only the shared concept — no extra logic
- [ ] No new pass-through modules or unnecessary abstractions created
- [ ] Both sides of each broken cycle import from the new shared module
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Run: cycle detector → `IMPROVED or CLEAN`
- [ ] Commit with message: `refactor: break circular dependency between [modules]`

---

## Track 5: Type Strengthening

### After Implementation
- [ ] Every replaced `Any`/`any` has a well-researched specific type
- [ ] No new `# type: ignore` or `@ts-ignore` added
- [ ] Legitimate `unknown` at trust boundaries is preserved
- [ ] No runtime behavior change — only type annotations modified
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `types: strengthen [area] types`

---

## Track 6: Error Handling Cleanup

### After Implementation
- [ ] Zero bare `except: pass` or empty `catch {}` blocks remain
- [ ] All removed silent handlers replaced with proper logging or propagation
- [ ] HTTP boundary handlers return proper error responses with status codes
- [ ] Worker/queue handlers log errors AND handle retry/dead-letter
- [ ] No test relies on silent-fail behavior (update tests if needed)
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `fix: improve error handling in [area]`

---

## Track 7: Deprecated Code and AI Slop

### After Implementation — Deprecated Code
- [ ] All removed code has zero active references
- [ ] No feature flags or config options still reference removed code
- [ ] No public API broken by removal

### After Implementation — AI Slop
- [ ] Zero narrating/edit-history comments remain
- [ ] Remaining comments explain **why**, not **what**
- [ ] No placeholder `pass` / `TODO: implement` remains for needed features
- [ ] Run: type-checker → `PASS`
- [ ] Run: linter → `PASS`
- [ ] Run: tests → `PASS`
- [ ] Commit with message: `chore: remove deprecated code and cleanup comments`

---

## Post-Flight (After ALL Tracks Complete)

- [ ] Full test suite passes
- [ ] Type-checker passes with no new suppressions
- [ ] Linter passes with no new suppressions
- [ ] Application starts and runs correctly
- [ ] No new warnings in build output
- [ ] Summary artifact produced with changes per track
