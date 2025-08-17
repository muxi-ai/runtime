# Dead Code Removal Implementation Plan

## Overview
This plan outlines the safe removal of 6 verified dead classes from the MUXI runtime codebase.

## Classes to Remove

### Verified Dead Classes (Actually Exist)
1. **MultiLLMCircuitBreaker** - `src/muxi/services/scheduler/circuit_breaker.py`
2. **MultiModalWorkflowIntegrator** - `src/muxi/services/multimodal/fusion_engine.py`
3. **ToolCallResult** - `src/muxi/datatypes/clarification.py`
4. **ClarificationContext** - `src/muxi/datatypes/clarification.py`
5. **ContextAnalysis** - `src/muxi/datatypes/clarification.py`
6. **ParameterMapping** - `src/muxi/datatypes/clarification.py`

## Removal Process

### Phase 1: Import Analysis
For each dead class:
1. Search for any imports of the class across the entire codebase
2. Document any import statements found (there shouldn't be any)
3. If imports exist, investigate why they're not being used

### Phase 2: File Analysis
1. **circuit_breaker.py**:
   - Check if file contains other classes/functions
   - Remove only MultiLLMCircuitBreaker class
   - Keep file as it contains active LLMCircuitBreaker class

2. **fusion_engine.py**:
   - Check if file contains other classes/functions
   - Remove only MultiModalWorkflowIntegrator class
   - Keep file as it contains active MultiModalFusionEngine and other classes

3. **clarification.py**:
   - Check what other classes/functions exist in the file
   - Remove the 4 dead classes: ToolCallResult, ClarificationContext, ContextAnalysis, ParameterMapping
   - Keep file if it contains other active code

### Phase 3: Export Statement Cleanup
1. Check each file's `__all__` export list
2. Remove dead classes from export lists if present
3. Update any module-level documentation

### Phase 4: Test Impact Analysis
1. Run existing tests to ensure nothing breaks
2. Check for any dynamic imports or getattr() usage
3. Verify no string-based class references exist

### Phase 5: Documentation Update
1. Remove any references from documentation files
2. Update CLAUDE.md if these classes are mentioned
3. Add removal notes to changelog if applicable

## Implementation Steps

### Step 1: Create Backup
```bash
# Create backup branch
git checkout -b remove-dead-code-backup
git add .
git commit -m "Backup before dead code removal"
```

### Step 2: Check Import Usage
For each class, run:
```bash
# Check for imports
grep -r "from .* import.*MultiLLMCircuitBreaker" src/
grep -r "import.*MultiLLMCircuitBreaker" src/
grep -r "MultiLLMCircuitBreaker" src/ --include="*.py" | grep -v "class MultiLLMCircuitBreaker"

# Repeat for other classes
grep -r "MultiModalWorkflowIntegrator" src/ --include="*.py" | grep -v "class MultiModalWorkflowIntegrator"
grep -r "ToolCallResult" src/ --include="*.py" | grep -v "class ToolCallResult"
grep -r "ClarificationContext" src/ --include="*.py" | grep -v "class ClarificationContext"
grep -r "ContextAnalysis" src/ --include="*.py" | grep -v "class ContextAnalysis"
grep -r "ParameterMapping" src/ --include="*.py" | grep -v "class ParameterMapping"
```

### Step 3: Remove Classes

#### 3.1 Remove from circuit_breaker.py
- Remove MultiLLMCircuitBreaker class (lines 257+)
- Keep all other classes

#### 3.2 Remove from fusion_engine.py
- Remove MultiModalWorkflowIntegrator class (lines 1149+)
- Keep all other classes

#### 3.3 Remove from clarification.py
- Remove ToolCallResult dataclass
- Remove ClarificationContext dataclass
- Remove ContextAnalysis dataclass
- Remove ParameterMapping dataclass
- Keep other clarification-related classes that are in use

### Step 4: Clean Up Exports
Check and update `__all__` lists in:
- `src/muxi/services/scheduler/__init__.py`
- `src/muxi/services/multimodal/__init__.py`
- `src/muxi/datatypes/__init__.py`

### Step 5: Run Tests
```bash
# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run specific service tests
pytest tests/unit/test_circuit_breaker.py
pytest tests/unit/test_multimodal.py
pytest tests/unit/test_clarification.py
```

### Step 6: Final Verification
```bash
# Verify classes are removed
grep -r "class MultiLLMCircuitBreaker" src/
grep -r "class MultiModalWorkflowIntegrator" src/
grep -r "class ToolCallResult" src/
grep -r "class ClarificationContext" src/
grep -r "class ContextAnalysis" src/
grep -r "class ParameterMapping" src/

# These should return nothing
```

## Safety Checks

### Pre-removal Checklist
- [ ] All classes verified as unused
- [ ] No imports found across codebase
- [ ] No string-based references found
- [ ] Backup branch created
- [ ] Team notified of removal plan

### Post-removal Checklist
- [ ] All tests pass
- [ ] No import errors
- [ ] Application starts successfully
- [ ] Documentation updated
- [ ] Commit with clear message about what was removed

## Rollback Plan
If issues arise:
1. `git checkout remove-dead-code-backup`
2. Investigate the specific issue
3. Update removal plan
4. Retry with more careful approach

## Expected Outcome
- Cleaner codebase with ~200-300 lines of unused code removed
- No functional impact on the system
- Improved maintainability
- Reduced cognitive load for developers

## Notes
- These classes appear to be abandoned features or over-engineered components
- MultiLLMCircuitBreaker was likely replaced by single LLMCircuitBreaker
- Clarification dataclasses were designed but replaced with simpler approach
- MultiModalWorkflowIntegrator was never integrated into workflow system