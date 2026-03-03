# Code Simplification Review

Review changed code for reuse, quality, and efficiency, then fix any issues found.

## Trigger
Run this review:
- After completing a significant implementation (multiple modules or 100+ lines)
- Before committing code at the end of a phase
- When the user asks for a code quality pass
- After integration test failures that suggest coupling issues

## Scope
Focus on recently changed or newly created files. Use `git diff --stat HEAD~1` or the user-specified scope.

## Checks to Perform (in order)

### 1. Duplication Detection
Scan the changed files for:
- Functions or methods with >80% structural similarity to existing code elsewhere in the codebase
- Copy-pasted logic blocks (>5 lines) that could be extracted into a shared helper
- Constants or magic numbers defined in multiple places
- Search for existing utilities before introducing new ones — check `core/`, module-level helpers, and `tests/conftest.py`

For each duplicate found, determine whether consolidation is appropriate. Sometimes duplication is acceptable (e.g., different modules with similar but independently-evolving logic). Flag it either way.

### 2. Complexity Reduction
For each changed function/method:
- Count branches (if/elif/else). Flag functions with >5 branches — consider breaking them up
- Check nesting depth. Flag >3 levels of nesting — consider early returns or extraction
- Look for multi-step imperative blocks that could be split into well-named helper functions
- Identify god functions (>50 lines) that do too many things

Do NOT add complexity to reduce complexity. If simplifying would add more code than it removes, note it but don't fix.

### 3. Performance Patterns
Check for known anti-patterns in the simulation codebase:
- Python loops over numpy arrays (should be vectorized)
- Repeated construction of identical objects in hot loops (should be hoisted)
- Brute-force spatial queries where indexing exists (KDTree, STRtree)
- Per-call computation of constants (should be module-level or cached)
- Unnecessary object allocation in inner loops (Position, dict, list)
- Set construction inside loops (should use frozenset at module level)
- Sorting inside tick loops (should be pre-sorted at setup)

### 4. Interface Quality
For public APIs in changed files:
- Are parameter types clear? (pydantic config vs raw dict)
- Are return types explicit? (NamedTuple/dataclass vs raw tuple/dict)
- Is the function doing one thing? (single responsibility)
- Could a caller misuse the API easily? (e.g., wrong argument order for similar types)

### 5. Test Quality
For test files in the changed set:
- Are helper functions using shared fixtures from `tests/conftest.py` where available?
- Are assertions specific? (`assert x == 5` vs `assert x`)
- Do tests test behavior, not implementation? (mock internals are a smell)
- Are edge cases covered? (empty lists, zero values, None inputs)

### 6. Convention Compliance
Quick check against project conventions:
- PRNG discipline (no bare random, all via Generator)
- Deterministic iteration (no set() in sim logic)
- Logging (no bare print)
- Type hints on public APIs
- Config classes use pydantic BaseModel

This overlaps with `/validate-conventions` but catches issues in the context of the specific changes being reviewed. For a full audit, use `/validate-conventions` instead.

## Output Format

For each issue found:
- **File:line** — location
- **Category** — Duplication / Complexity / Performance / Interface / Test / Convention
- **Severity** — HIGH (fix now), MEDIUM (should fix), LOW (optional improvement)
- **Issue** — what's wrong
- **Fix** — concrete suggestion (code snippet if appropriate)

## After the Review

1. Present findings grouped by severity (HIGH first)
2. For HIGH items: fix them immediately
3. For MEDIUM items: ask user which to fix now vs defer
4. For LOW items: note them but do not fix unless user asks
5. If no issues found, report "Clean — no simplification needed"
