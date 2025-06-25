# Day 1 Test Mapping

Based on the MUXI Runtime Comprehensive Test Plan, here's the mapping of test groups to actual test files:

## Primary Test File: `test_1a1_basic_yaml_formation.py`
This file contains 5 test methods covering all of Test Group 1A:

### Test Group 1A: Formation Loading
- **1A1: Basic YAML Formation** → `test_1a1_basic_yaml_formation()`
  - Tests loading formation from directory structure
  - Verifies configuration keys and formation ID

- **1A2: Directory Structure Formation** → `test_1a2_directory_structure_formation()`
  - Tests loading from directory with separate agent/MCP files
  - Verifies agents are auto-discovered

- **1A3: Formation Validation Failures** → `test_1a3_formation_validation_failures()`
  - Tests 6 invalid formation scenarios:
    1. invalid-syntax.yaml (malformed YAML)
    2. invalid-not-yaml.txt (wrong file type)
    3. invalid-missing-keys.yaml (missing required fields)
    4. invalid-schema.yaml (wrong schema version)
    5. invalid-values.yaml (negative memory size)
    6. Non-existent formation path

- **1A3 Additional: Edge Cases** → `test_1a3_additional_validation_cases()`
  - Tests 2 additional validation scenarios:
    1. invalid-empty.yaml (empty file)
    2. invalid-no-agents/ (directory without agents)

- **1A4: Flattened Formation Loading** → `test_1a4_flattened_formation_loading()`
  - Tests loading formation with inline agents and MCPs
  - Verifies inline-assistant agent loaded
  - Verifies local-tools MCP server loaded

- **1A5: Remote Memory Validation** → `test_1a5_remote_memory_validation.py`
  - Tests remote memory configuration requirements:
    - Remote mode requires URL
    - Remote mode requires tenant ID
    - Remote mode requires explicit max_memory_mb (not "auto")
    - Valid remote configuration loading
    - Local mode allows "auto" for max_memory_mb
    - Remote mode with authentication

## Secondary Test File: `test_1a4_flattened_formation_loading.py`
This file contains a TestSimpleFormationLoading class with 5 test methods:

- `test_load_valid_formation()` - Basic formation loading
- `test_load_nonexistent_formation()` - Non-existent path handling
- `test_load_invalid_yaml()` - Invalid YAML syntax handling
- `test_formation_state_after_load()` - Formation state verification
- `test_multiple_load_attempts()` - Sequential loading tests

## Test Group 1B: Basic Agent Communication
- **1B1: Single Agent Response** → `test_1b1_single_agent_response.py` (standalone script)
- **1B2: Agent Routing Validation** → `test_1b2_agent_routing_validation.py` (async test)

## Other Test Files
- `test_1a2_directory_structure_formation.py` - Contains `test_minimal_yaml_loading()`
- `test_1a3_formation_validation_failures.py` - Contains `test_debug_loading()` debug script

## Test Count Summary

### Actual Test Functions:
- **test_1a1_basic_yaml_formation.py**: 5 test methods
- **test_1a4_flattened_formation_loading.py**: 5 test methods
- **test_1a5_remote_memory_validation.py**: 6 test functions (NEW)
  - Remote memory requires URL
  - Remote memory requires tenant
  - Remote memory requires explicit max_memory_mb
  - Valid remote configuration
  - Local mode allows auto
  - Remote with authentication
- **test_1a2_directory_structure_formation.py**: 1 test function
- **test_1a3_formation_validation_failures.py**: 1 test function
- **test_1b1_single_agent_response.py**: Standalone script
- **test_1b2_agent_routing_validation.py**: 1 async test function

**Total identifiable test functions: 19+**

### Invalid Formations Tested:
1. `invalid-empty.yaml` - Empty YAML file
2. `invalid-missing-keys.yaml` - Missing required fields
3. `invalid-no-agents/` - Directory without agents
4. `invalid-not-yaml.txt` - Not a YAML file
5. `invalid-schema.yaml` - Wrong schema version
6. `invalid-syntax.yaml` - Malformed YAML syntax
7. `invalid-values.yaml` - Invalid values (negative memory)

## Formations Used:
- `test-formations/formation-basic/` - Basic single-agent formation
- `test-formations/formation-basic/formation-flattened.yaml` - Inline agents & MCPs
- `test-formations/formation-multi-agent/` - Multiple agents
- `test-formations/formation-file-generation/` - File generation MCP
- `test-formations/invalid-formations/` - All invalid test cases

## Key Achievements:
1. ✅ Comprehensive validation failure testing (7 invalid scenarios)
2. ✅ Flattened formation support (inline agents and MCPs)
3. ✅ Directory-based and file-based formation loading
4. ✅ Formation state management testing
5. ✅ Thread-safe test execution pattern established
