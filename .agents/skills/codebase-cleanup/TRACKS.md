# Track Details

Detailed instructions for each of the 7 cleanup tracks. Every track follows the same loop: **Inspect → Assess → Rank → Implement → Verify**.

---

## Track 1: Deduplication

### Goal
Consolidate repeated logic, copy-pasted functions, and redundant abstractions. Apply DRY **only where it genuinely simplifies** — never merge code that merely looks similar but serves different purposes.

### Inspect

1. **Textual duplicates** — Search for repeated function bodies:
   ```bash
   # Find functions/methods with similar names
   grep -rn "def \|function \|const .* = " --include="*.py" --include="*.ts" | sort
   ```
2. **Semantic duplicates** — Use semantic search to find functions that do the same thing with different names or signatures.
3. **Copy-paste patterns** — Look for blocks of 5+ lines that appear in multiple files. Pay attention to:
   - Utility functions reimplemented in different modules
   - Similar validation logic across endpoints
   - Repeated DB query patterns
   - Configuration/setup code copied between files

### Assess — Questions to Answer

- Does merging these reduce **total complexity**, or just move it?
- Do the "duplicates" actually handle edge cases differently?
- Would a shared abstraction need parameters/flags that make it harder to understand than two simple copies?
- Is this duplication **accidental** (copy-paste debt) or **intentional** (independent evolution)?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Exact or near-exact copies, same intent, no edge-case divergence |
| **MEDIUM** | Similar structure, but slight behavioral differences that might be intentional |
| **LOW** | Looks similar but serves fundamentally different domains or consumers |

### Implement Rules

- Extract shared logic into a clearly-named utility in the most logical shared location.
- If merging requires adding flags or mode parameters, reconsider — the abstraction may not be worth it.
- Update all call sites. Do not leave stale imports or aliases.
- Preserve all existing tests. Add tests for the new shared function if none existed.

---

## Track 2: Type Consolidation

### Goal
Find all type definitions scattered across files. Consolidate duplicated or drifted types into a single source of truth. Detect types defined in multiple places that have quietly gone out of sync.

### Inspect

1. **Find all type definitions:**
   ```bash
   # Python
   grep -rn "class .*:" --include="*.py" | grep -v "__pycache__" | grep -v "test_"
   grep -rn "TypedDict\|NamedTuple\|dataclass\|BaseModel" --include="*.py"

   # TypeScript
   grep -rn "^export \(type\|interface\)" --include="*.ts" --include="*.tsx"
   ```
2. **Find duplicated type names:**
   ```bash
   # Extract type names and find duplicates
   grep -rohn "class \w\+" --include="*.py" | awk -F: '{print $2}' | sort | uniq -d
   ```
3. **Compare drifted types** — When two types share a name, diff their fields. Look for:
   - Fields added in one location but not the other
   - Optional vs required mismatches
   - Different default values
   - Renamed fields that broke the contract

### Assess — Questions to Answer

- Which definition is the **canonical** one? (Usually the one closest to the domain model.)
- Are consumers importing from a consistent location, or is import chaos hiding the drift?
- Would consolidation require a migration or data transformation?
- Are any of these types actually **distinct domain concepts** that happen to share a name?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Same name, same intent, field drift is clearly accidental |
| **MEDIUM** | Same name, mostly same fields, but used in different contexts (API vs DB) |
| **LOW** | Same name but legitimately different concepts across bounded contexts |

### Implement Rules

- Create a canonical location (e.g., `app/types/`, `src/types/`, or domain-specific `models.py`).
- Merge fields, taking the **superset** where safe, or the **stricter** definition where validation matters.
- Update all imports to point to the canonical source.
- Run type-checker after every file change — drift often hides type errors.

---

## Track 3: Dead Code Removal

### Goal
Find all unused exports, unreferenced functions, and orphaned files. **Verify manually before removing.** Static analysis misses dynamic imports, config references, framework conventions, and code generation.

### Inspect

1. **Run static analysis:**
   ```bash
   # Python
   vulture . --min-confidence 80

   # TypeScript/JavaScript
   npx knip
   ```
2. **Find orphaned files** — Files not imported anywhere:
   ```bash
   # List all source files, then check which are never imported
   find . -name "*.py" -not -path "./.venv/*" | while read f; do
     base=$(basename "$f" .py)
     if ! grep -rq "import.*$base\|from.*$base" --include="*.py" .; then
       echo "ORPHAN: $f"
     fi
   done
   ```
3. **Check for false positives** before removing ANYTHING:
   - [ ] Is this referenced in config files? (`alembic.ini`, `docker-compose.yml`, `.env`)
   - [ ] Is this a framework convention? (e.g., `__init__.py`, migration files, `conftest.py`)
   - [ ] Is this loaded dynamically? (`importlib`, `__import__`, `require()`)
   - [ ] Is this referenced in CI/CD configs?
   - [ ] Is this an entry point registered in `setup.py` / `pyproject.toml` / `package.json`?
   - [ ] Is this used by code generation or template engines?

### Assess — Questions to Answer

- When was this code last modified? (Recent = higher risk of removal being wrong.)
- Does this file have a clear purpose that might be activated by configuration?
- Is there a TODO/FIXME indicating planned future use?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Zero references, no dynamic loading patterns, not a framework convention, untouched for months |
| **MEDIUM** | Zero static references but could be dynamically loaded or config-activated |
| **LOW** | Referenced indirectly, or recently modified, or purpose is unclear |

### Implement Rules

- Remove one file/function at a time.
- Run full test suite after each removal.
- If tests pass but you're unsure, **comment out** instead of deleting — revisit in a follow-up.
- Remove associated tests for deleted code (dead tests for dead code are also dead).
- Clean up any imports that referenced the removed code.

---

## Track 4: Circular Dependencies

### Goal
Map the full dependency graph. Identify every circular import. Prioritize cycles that affect maintainability, testability, or correctness. Untangle by extracting shared logic into neutral modules. **Do not introduce new abstractions just to break a cycle.**

### Inspect

1. **Map the dependency graph:**
   ```bash
   # Python
   pydeps app/ --no-output --show-cycles
   # or
   python -c "import importlib; import sys; [print(m) for m in sorted(sys.modules.keys()) if 'app' in m]"

   # TypeScript/JavaScript
   npx madge --circular --extensions ts,js src/
   npx madge --image graph.svg src/  # visual graph
   ```
2. **Manual detection** — Look for:
   - `TYPE_CHECKING` imports (often a sign of existing circular dependency workarounds)
   - Lazy imports inside functions (`from x import y` inside a function body)
   - `# noqa` or `# type: ignore` on imports

### Assess — Questions to Answer

- Is this cycle **real** (runtime import order matters) or **type-only** (only for annotations)?
- Does the cycle cause actual bugs, or just make the code harder to understand?
- What is the **shared concept** that both sides of the cycle depend on?
- Can the shared concept be extracted to a neutral module without creating a pointless pass-through?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Runtime cycle causing import errors or requiring workarounds; clear shared concept to extract |
| **MEDIUM** | Type-only cycle with `TYPE_CHECKING` workaround already in place |
| **LOW** | Cycle exists but is stable, well-understood, and changing it risks regression |

### Implement Rules

- Extract the **shared dependency** into a new module at the appropriate level (e.g., `app/types/`, `app/shared/`).
- Both sides of the cycle should import from the new module — neither should import from the other.
- Do NOT create wrapper classes, abstract base classes, or dependency injection frameworks just to break a cycle.
- Verify the cycle is actually broken after your change:
  ```bash
  # Re-run cycle detection
  npx madge --circular src/
  pydeps app/ --show-cycles
  ```

---

## Track 5: Type Strengthening

### Goal
Find every instance of `any`, `unknown`, `Any`, `object`, and other weak/placeholder types. Research the real types by inspecting the codebase, related packages, and runtime usage. Replace with strong types. **Preserve legitimate boundary types where `unknown` is correct.**

### Inspect

1. **Find weak types:**
   ```bash
   # Python
   grep -rn "Any\|object\|Dict\[str, Any\]\|# type: ignore" --include="*.py" | grep -v "__pycache__"

   # TypeScript
   grep -rn ": any\|: unknown\|as any\|@ts-ignore\|@ts-expect-error" --include="*.ts" --include="*.tsx"
   ```
2. **Categorize each instance:**
   - **Placeholder** — AI or developer left `Any` because they didn't know the real type
   - **Boundary** — Legitimately untyped data (external API responses, user input, deserialised JSON)
   - **Escape hatch** — Used to silence a type error that should be fixed properly

### Assess — Questions to Answer

- What does the code **actually do** with this value? (The operations reveal the real type.)
- Does the upstream library provide proper types? Check `@types/` packages or `.pyi` stubs.
- Would strengthening this type catch real bugs, or just add noise?
- Is `unknown` the correct answer here? (It's correct at trust boundaries — e.g., webhook payloads.)

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Usage clearly reveals the type; library types available; strengthening catches real bugs |
| **MEDIUM** | Type is inferrable but requires understanding multiple call sites |
| **LOW** | Legitimately dynamic data, or type is too complex to express without major refactoring |

### Implement Rules

- Fix one file at a time. Run type-checker after each file.
- For `Dict[str, Any]` / `Record<string, any>`, define a proper interface or TypedDict.
- For function parameters, trace all call sites to determine the actual type.
- For return types, trace all consumers.
- Do NOT replace `unknown` at trust boundaries — that's correct defensive typing.
- Do NOT add `# type: ignore` to suppress new errors — fix the root cause.

---

## Track 6: Error Handling Cleanup

### Goal
Find all try/catch blocks and defensive patterns. Remove those that silently swallow errors, hide failures, or fall back to defaults that mask real problems. **Keep error handling that serves a real boundary:** recovery, logging, cleanup, or user-facing error reporting.

### Inspect

1. **Find all error handling:**
   ```bash
   # Python
   grep -rn "except:\|except Exception\|pass$\|\.get(\|or None\|or \[\]\|or {}" --include="*.py" | grep -v "__pycache__"

   # TypeScript/JavaScript
   grep -rn "catch\|\.catch\|try {" --include="*.ts" --include="*.tsx" --include="*.js"
   ```
2. **Classify each handler:**
   - **Silent swallow** — `except: pass`, `catch(e) {}`, or logging at DEBUG level
   - **Default masking** — Returning `[]`, `None`, `{}`, `0` instead of propagating the error
   - **Legitimate** — Logging at ERROR/WARNING, user-facing error, cleanup/rollback, retry logic

### Assess — Questions to Answer

- What fails silently if this error is swallowed? (Trace the impact.)
- Does the caller expect this function can fail, or does the catch hide a contract violation?
- Is the fallback value (`None`, `[]`) creating downstream `NoneType` errors that are harder to debug?
- Would removing this handler cause a crash that reveals a **real bug**?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Bare `except: pass`, empty catch blocks, or fallbacks that clearly mask bugs |
| **MEDIUM** | Fallback to default values where the impact is unclear |
| **LOW** | Handler at a genuine boundary (HTTP endpoint, queue consumer, CLI entry point) |

### Implement Rules

- Replace silent handlers with proper logging at WARNING or ERROR level.
- Replace default-value fallbacks with explicit error propagation unless the caller genuinely handles the None/empty case.
- At HTTP boundaries, convert to proper error responses with status codes.
- At queue/worker boundaries, ensure errors are logged AND retried or dead-lettered.
- Do NOT remove error handling at genuine system boundaries — these are load-bearing.
- After each change, verify no test depends on the silent-fail behavior.

---

## Track 7: Deprecated Code and AI Slop

### Goal
Two sub-goals:
1. **Deprecated code** — Remove legacy, deprecated, and fallback code paths that are clearly obsolete.
2. **AI slop** — Remove stubs, placeholder logic, and comments that narrate edit history instead of explaining intent.

### Inspect — Deprecated Code

1. **Find deprecation markers:**
   ```bash
   grep -rn "deprecated\|DEPRECATED\|@deprecated\|TODO.*remove\|FIXME.*remove\|HACK\|LEGACY\|COMPAT" --include="*.py" --include="*.ts"
   ```
2. **Find unused compatibility code:**
   - Version checks that reference old versions
   - Feature flags that are always on/off
   - Migration code that has already run
   - Fallback implementations for removed dependencies

### Inspect — AI Slop

1. **Find AI-generated comments:**
   ```bash
   grep -rn "# This function\|// This function\|# We need to\|// We need to\|# Now we\|// Now we\|# First,\|// First,\|# Updated\|# Modified\|# Added\|# Changed" --include="*.py" --include="*.ts"
   ```
2. **AI slop patterns to detect:**
   - Comments that narrate **what** the code does instead of **why**
   - Edit-history comments (`# Added error handling`, `# Updated to use new API`)
   - Placeholder implementations (`pass`, `TODO: implement`, `throw new Error("not implemented")`)
   - Overly defensive code that handles impossible states
   - Redundant variable assignments that add no clarity
   - Comments restating the function name as documentation

### Assess — Questions to Answer

**For deprecated code:**
- Is there any active code path that still reaches this?
- Is there a config flag or environment variable that enables it?
- Would removing it break backward compatibility for current users?
- Is this migration code that still needs to run on existing deployments?

**For AI slop:**
- Does this comment explain **why**, or just restate **what**?
- Is this placeholder hiding unfinished work, or is it genuinely unused?
- Would a new engineer understand the code better with or without this comment?

### Rank

| Confidence | Criteria |
|------------|----------|
| **HIGH** | Clearly obsolete code with no active references; narrating/edit-history comments |
| **MEDIUM** | Deprecated but with unclear active-user impact; comments that are redundant but harmless |
| **LOW** | Compatibility code where removal impact is uncertain; defensive code at boundaries |

### Implement Rules

**Deprecated code:**
- Remove one code path at a time.
- Run tests after each removal.
- If removing deprecated code requires updating a public API, flag it as MEDIUM risk and defer.

**AI slop:**
- Delete comments that restate the code or narrate edit history.
- **Rewrite** comments worth keeping: a new engineer should understand **why** the code exists, not the change history.
- Remove placeholder implementations only if the feature is not needed.
- Remove defensive code that handles impossible states — unless you cannot prove the state is impossible.

**Comment rewrite formula:**
```
BAD:  # Added retry logic to handle network errors (updated 2024-03-15)
GOOD: # External API is unreliable under load — retry with backoff to avoid cascading failures

BAD:  # This function processes the data
GOOD: # (delete — the function name already says this)

BAD:  # We need to validate the input first
GOOD: # Upstream callers may pass unsanitised user input — validate before DB query
```
