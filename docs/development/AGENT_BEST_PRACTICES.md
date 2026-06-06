# Agent Best Practices

Guidelines for AI agents (Claude Code, overnight agents) working on this codebase to prevent common pitfalls and ensure high-quality automated changes.

## Function Signature Modifications

**Problem:** When modifying function signatures (adding/removing/changing parameters), agents may miss updating all callers, especially test mocks.

**Common Scenario:** Agent removes unused parameters from a function but doesn't update test mocks that call it with the old signature, causing CI test failures.

### Safe Refactoring Workflow

When modifying any function signature, **ALWAYS** follow these steps:

#### 1. Make the Signature Change
```python
# Before
def process_data(data, cache, score, metadata, options):
    ...

# After
def process_data(data, options):
    ...
```

#### 2. Find ALL Callers (Critical Step)
Use Grep to search the **entire codebase** (both `src/` and `tests/`):

```bash
# Search for function name across all source files
grep -r "process_data" src/ tests/ --include="*.py"  # Python
grep -r "processData" src/ tests/ --include="*.ts"   # TypeScript
grep -r "processData" src/ tests/ --include="*.js"   # JavaScript
```

**Key points:**
- Search in **both** `src/` AND `tests/` directories
- Don't assume you know all callers - search comprehensively
- Check for partial matches (e.g., method calls, imports, mocks)

#### 3. Update Each Caller
Review **every** match from grep and update to match new signature:

```python
# Test mock - BEFORE
processor.process_data(
    data=data,
    cache=cache,  # ← REMOVE
    score=75,  # ← REMOVE
    metadata={...},  # ← REMOVE
    options=options,
)

# Test mock - AFTER
processor.process_data(
    data=data,
    options=options,
)
```

#### 4. Run Affected Tests
**Before committing**, run tests for the modified module:

```bash
# Python projects
pytest tests/unit/test_<module>.py -v

# JavaScript/TypeScript projects
npm test -- test/<module>.test.ts

# Generic pattern: run tests for modified module
<test-command> <test-file-pattern>
```

**Success criteria:**
- All tests must pass (exit code = 0)
- No TypeErrors about unexpected arguments
- No missing required parameter errors

#### 5. Commit Only If Tests Pass
```bash
# Only commit if step 4 succeeded
git add <files>
git commit -m "refactor: Update function signature and all callers"
```

## Common Grep Patterns for Refactoring

### Finding Function Callers
```bash
# Direct function calls
grep -r "function_name(" src/ tests/ --include="*.py"

# Method calls (instance.method)
grep -r "\\.method_name(" src/ tests/ --include="*.py"

# Imports
grep -r "from .* import.*function_name" src/ tests/ --include="*.py"
```

### Finding Class References
```bash
# Class instantiation
grep -r "ClassName(" src/ tests/ --include="*.py"

# Class inheritance
grep -r "class.*ClassName" src/ tests/ --include="*.py"
```

### Finding Variable/Constant References
```bash
# All references to a constant
grep -r "CONSTANT_NAME" src/ tests/ --include="*.py"
```

## Parameter Removal Checklist

When removing function parameters, verify:

- [ ] Function signature updated in source file
- [ ] Grep search performed for all callers (src/ + tests/)
- [ ] All callers updated to match new signature
- [ ] Default parameter values removed if no longer needed
- [ ] Docstring updated to reflect new parameters
- [ ] Tests run successfully for modified module
- [ ] Type hints updated (if applicable)
- [ ] No TypeErrors in test output

## Test Mock Best Practices

### When Mocking Functions with Changed Signatures

**Always update mock calls** to match the current function signature:

```python
# ✅ GOOD - Mock matches actual signature
mocker.patch.object(processor, 'process_data')
processor.process_data(data=data, options=options)

# ❌ BAD - Mock includes removed parameters
processor.process_data(
    data=data,
    cache=cache,  # Parameter no longer exists!
    options=options
)
```

### Test Discovery Pattern

When modifying a function, find its tests:

```bash
# Find test files that test the modified module
ls tests/unit/test_<module_name>.*

# Search for test methods that call the function
grep -r "def test.*" tests/ | grep -i <function_name>
```

## Refactoring Safety Principles

1. **Search First, Change Second** - Always grep for references before modifying signatures
2. **Tests Are Callers Too** - Don't forget test mocks and fixtures
3. **Verify Before Commit** - Run affected tests locally before pushing
4. **Fail Fast** - If tests fail, investigate immediately - don't skip or ignore
5. **Document Changes** - Include "Updated all callers" in commit messages

## Why This Matters

**Without this workflow:**
- ❌ Test failures in CI (discovered late)
- ❌ Manual cleanup required
- ❌ Additional PR iterations
- ❌ Wasted time debugging

**With this workflow:**
- ✅ Issues caught before CI
- ✅ Clean, passing PRs on first push
- ✅ Fewer manual interventions
- ✅ Higher confidence in automated changes

## Example: Complete Refactoring Workflow

```bash
# 1. Modify function signature in src/processor.py
#    Remove unused parameters from process_data()

# 2. Find all callers
grep -r "process_data" src/ tests/ --include="*.py"
# Output:
# src/processor.py:42:    def process_data(data, options):
# tests/unit/test_processor.py:123:    processor.process_data(

# 3. Update test mock (line 123 in test file)
#    Remove: cache, score, metadata parameters

# 4. Run tests
pytest tests/unit/test_processor.py -v
# Output: 8 passed ✅

# 5. Commit
git add src/processor.py tests/unit/test_processor.py
git commit -m "refactor: Remove unused params from process_data

Removed unused parameters: cache, score, metadata
Updated all callers including test mocks.
All tests passing."
```

## Language-Specific Notes

### Python
- Use `pytest` to run tests
- Watch for `TypeError: got an unexpected keyword argument` errors
- Remember to update type hints in function signature

### TypeScript/JavaScript
- Use `npm test` or `jest` to run tests
- Watch for argument count mismatches
- Update interface definitions if function is part of an interface

### General
- The grep → update → test pattern works across all languages
- Adjust file extensions in grep patterns (`.py`, `.ts`, `.js`, `.go`, etc.)
- Use your language's test runner for step 4

## Revision History

- 2026-02-18: Initial version (generalized best practices for all projects)
