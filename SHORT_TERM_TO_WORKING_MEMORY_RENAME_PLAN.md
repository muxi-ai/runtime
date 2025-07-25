# Implementation Plan: Rename WorkingMemory to WorkingMemory

## Overview

This implementation plan details the comprehensive renaming of `WorkingMemory` to `WorkingMemory` throughout the MUXI Runtime codebase. The rename is necessary because "working memory" no longer accurately reflects the component's role - it now holds knowledge, runtime context, and other persistent information beyond just working conversation history.

## Scope Analysis

### Files to be Modified

#### 1. Core Implementation Files
- **Primary Class File**: `src/muxi/services/memory/working.py`
  - Rename file to: `src/muxi/services/memory/working.py`
  - Rename class: `WorkingMemory` → `WorkingMemory`
  - Update all docstrings and comments

#### 2. Module Exports
- **Memory Package Init**: `src/muxi/services/memory/__init__.py`
  - Update import: `from .working import WorkingMemory` → `from .working import WorkingMemory`
  - Update export: `"WorkingMemory"` → `"WorkingMemory"` in `__all__`
  - Update all comments and docstrings

#### 3. Core Usage Files
- **Formation Initialization**: `src/muxi/formation/initialization.py`
  - Update import: `from ..services.memory.working import WorkingMemory` → `from ..services.memory.working import WorkingMemory`
  - Update instantiation calls

- **Overlord**: `src/muxi/formation/overlord/overlord.py`
  - Update import: `from ...services.memory.working import WorkingMemory` → `from ...services.memory.working import WorkingMemory`
  - Update type hints and instantiation

- **Agent**: `src/muxi/formation/agents/agent.py`
  - Update any references to WorkingMemory

- **Knowledge Handler**: `src/muxi/formation/agents/knowledge/handler.py`
  - Update import: `from ....services.memory.working import WorkingMemory` → `from ....services.memory.working import WorkingMemory`

#### 4. Supporting Components
- **Buffer Memory Document Storage**: `src/muxi/formation/documents/storage/buffer_memory.py`
  - Update import: `from ....services.memory.working import WorkingMemory` → `from ....services.memory.working import WorkingMemory`
  - Update inheritance comments

- **Memory User Context**: `src/muxi/formation/memory/user_context.py`
  - Update any references

- **Buffer Manager**: `src/muxi/formation/memory/buffer_manager.py`
  - Update any references

- **Config Loader**: `src/muxi/formation/config/loader.py`
  - Update any references

- **Workflow Synthesizer**: `src/muxi/formation/clarification/workflow_synthesizer.py`
  - Update any references

#### 5. Data Types
- **Memory Datatypes**: `src/muxi/datatypes/memory.py`
  - Update class docstring: "buffer memory (working memory)" → "buffer memory (working memory)"
  - Update comments throughout

- **Observability Datatypes**: `src/muxi/datatypes/observability.py`
  - Update event names if any contain "WORKING"

#### 6. Test Files (30+ files)
All test files need import updates:
- `tests/agents/test_programmatic_agent.py`
- `tests/memory/test_*.py` (all memory test files)
- `tests/overlord/test_*.py` (overlord test files)
- `tests/knowledge/test_knowledge_handler.py`
- `tests/day_2/test_*.py` (all day 2 test files)
- `tests/day_6/test_*.py` (relevant day 6 tests)
- `tests/test_user_id_enhancement*.py`

Special attention for:
- `tests/memory/test_memory.py` - Contains `TestWorkingMemory` class
- `tests/memory/test_buffer_integration.py` - Contains `TestWorkingMemory` subclass
- `tests/overlord/test_overlord.py` - Contains `MockWorkingMemory` class

#### 7. Documentation Files
- **README.md**
  - Update example code blocks
  - Update architecture descriptions
  - Update comment: "Working FIFO + vector memory" → "Working memory (FIFO + vector)"

- **Memory Systems Documentation**: `docs/memory-systems.md`
  - Update buffer memory description: "(Working, Fast Access, Recent Context)" → "(Working Memory, Fast Access, Recent Context)"

- **Knowledge System Documentation**: `docs/knowledge-system.md`
  - Update references: "WorkingMemory" → "WorkingMemory"

- **Testing Guide**: `MUXI_Runtime_Testing_Guide.md`
  - Update references to WorkingMemory class
  - Update event name: `MEMORY_WORKING_UPDATED` → `MEMORY_WORKING_UPDATED`

- **Development Notes**: `CLAUDE.md`
  - Update references to working memory

- **Overlord System Message**: `src/muxi/formation/overlord/system_message.md`
  - Update: "working buffer memory" → "working buffer memory"

#### 8. Example Files
- `examples/simple_agent.py`
- `examples/multi_agent.py`
- Update imports and usage

#### 9. Test Reports and Documentation
- `tests/reports/*.md` - Update any references in test reports
- `tests/day_2/TEST_MAPPING.md` - Update helper descriptions
- `tests/TEST_ORGANIZATION_SUMMARY.md` - Update references

#### 10. Generated Files (Do not edit, will be regenerated)
- `src/muxi.egg-info/PKG-INFO`
- `src/muxi.egg-info/SOURCES.txt`
- Python cache files (`__pycache__`)

## Implementation Steps

### Phase 1: Core Renaming
1. **Rename the main file**:
   ```bash
   git mv src/muxi/services/memory/working.py src/muxi/services/memory/working.py
   ```

2. **Update the class definition** in `working.py`:
   - Change `class WorkingMemory:` to `class WorkingMemory:`
   - Update all docstrings mentioning "working memory"
   - Update the frontmatter title and description

3. **Update imports in memory package** (`src/muxi/services/memory/__init__.py`):
   - Change import statement
   - Update `__all__` export list
   - Update package docstring

### Phase 2: Update Core Dependencies
4. **Update formation initialization** (`src/muxi/formation/initialization.py`)
5. **Update overlord** (`src/muxi/formation/overlord/overlord.py`)
6. **Update agent framework** files
7. **Update knowledge handler** (`src/muxi/formation/agents/knowledge/handler.py`)

### Phase 3: Update Supporting Components
8. **Update document storage components**
9. **Update data type definitions**
10. **Update configuration loaders**

### Phase 4: Update Tests
11. **Batch update test imports** using search and replace
12. **Update test class names** (TestWorkingMemory, MockWorkingMemory)
13. **Update test helper files**

### Phase 5: Update Documentation
14. **Update main README.md**
15. **Update all documentation files** in `docs/`
16. **Update example files**
17. **Update test reports and summaries**

### Phase 6: Update Comments and Strings
18. **Search and replace remaining references**:
    - "working memory" → "working memory"
    - "Working memory" → "Working memory"
    - "WORKING" → "WORKING" (in event names)

### Phase 7: Validation
19. **Run all tests** to ensure nothing is broken
20. **Regenerate egg-info** files
21. **Check for any missed references** using grep

## Search and Replace Patterns

### For Class Names:
- `WorkingMemory` → `WorkingMemory`
- `TestWorkingMemory` → `TestWorkingMemory`
- `MockWorkingMemory` → `MockWorkingMemory`

### For Imports:
- `from .working import` → `from .working import`
- `from ..services.memory.working import` → `from ..services.memory.working import`
- `from ...services.memory.working import` → `from ...services.memory.working import`
- `from ....services.memory.working import` → `from ....services.memory.working import`
- `from src.muxi.services.memory.working import` → `from src.muxi.services.memory.working import`
- `from src.muxi.memory.working import` → `from src.muxi.memory.working import`
- `from muxi.memory import WorkingMemory` → `from muxi.memory import WorkingMemory`

### For File Names:
- `working.py` → `working.py`

### For Comments and Documentation:
- `working memory` → `working memory`
- `Working memory` → `Working memory`
- `WORKING` → `WORKING` (in constants/events)
- `working memory` → `working memory`
- `Short Term Memory` → `Working Memory`

### For Event Names:
- `MEMORY_WORKING_UPDATED` → `MEMORY_WORKING_UPDATED`

## Validation Checklist

- [ ] All imports updated and working
- [ ] All tests passing
- [ ] No references to "WorkingMemory" class remain (except in git history)
- [ ] No references to "working.py" file remain
- [ ] Documentation accurately reflects the new naming
- [ ] Example code runs correctly
- [ ] Event names updated if applicable
- [ ] Comments and docstrings updated

## Notes

1. **Backward Compatibility**: This is a breaking change. Any external code depending on `WorkingMemory` will need to be updated.

2. **Git History**: The rename preserves git history when using `git mv`.

3. **Import Aliases**: Consider adding temporary import aliases during migration:
   ```python
   # Temporary backward compatibility
   WorkingMemory = WorkingMemory  # Remove after migration
   ```

4. **Event Names**: Check if any observability events use "WORKING" in their names and update accordingly.

5. **Configuration**: The configuration keys in YAML files may use "buffer" terminology which is fine to keep as-is since "buffer memory" is still an accurate description.

## Estimated Time

- Core renaming: 30 minutes
- Test updates: 45 minutes
- Documentation updates: 30 minutes
- Validation and testing: 30 minutes
- **Total**: ~2-3 hours

## Risk Assessment

- **Low Risk**: This is primarily a naming change with no functional modifications
- **Main Risk**: Missing some references could cause import errors
- **Mitigation**: Comprehensive grep searches and full test suite execution

---

**Author**: MUXI Framework Team
**Date**: January 2025
**Status**: Ready for Implementation
