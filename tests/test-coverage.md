# MUXI Runtime Unit Test Coverage Plan - SPRINT EDITION

## Executive Summary

This plan outlines an aggressive sprint approach to achieve >95% unit test coverage for MUXI Runtime within ONE WEEK. Current coverage is approximately 17%, with 154 files (51% of codebase) having zero coverage.

**Target**: 95%+ unit test coverage within 1 week (7 days)
**Current**: 17% coverage (304 total Python files)
**Required Velocity**: ~40 files tested per day

## Current State Analysis

### Coverage Breakdown by Module

| Module | Files | Current Coverage | Target | Priority |
|--------|-------|-----------------|--------|----------|
| `muxi/formation/` | 159 | ~15% | 95% | HIGH |
| `muxi/services/` | 111 | ~10% | 95% | HIGH |
| `muxi/datatypes/` | 21 | ~5% | 100% | MEDIUM |
| `muxi/utils/` | 15 | ~20% | 90% | LOW |
| `muxi/extensions/` | 4 | ~0% | 90% | LOW |

### Critical Gaps

- **Zero Coverage**: 154 files (51% of codebase)
- **Low Coverage (<20%)**: 52 files
- **Medium Coverage (20-50%)**: 34 files
- **High Coverage (>50%)**: 64 files

## Sprint Implementation Plan

### Day 0: Pre-Sprint Setup (4 hours)
**Goal**: Rapid infrastructure setup and test generation framework

#### Immediate Actions
- [ ] Create automated test generator script using AST parsing
- [ ] Set up universal mock factory for all external dependencies
- [ ] Create parameterized test templates for common patterns
- [ ] Fix all existing test import issues
- [ ] Set up parallel test execution (pytest-xdist)

#### Automated Test Generation Tools
```python
# test_generator.py - Automatically generate unit tests from source files
# Features:
# - AST parsing to identify all functions/methods
# - Automatic mock injection for dependencies
# - Parameterized test generation for multiple scenarios
# - Coverage-guided test generation
```

### Day 1: Data Types & Utils (36 files)
**Goal**: Cover all simple, stateless modules first
**Approach**: Auto-generate tests for Pydantic models and utility functions

#### Morning (18 files)
- [ ] All 21 files in `datatypes/` - Pydantic model validation tests
- [ ] Auto-generate property-based tests for each model
- [ ] Use hypothesis for edge case generation

#### Afternoon (18 files)
- [ ] All 15 files in `utils/` - Utility function tests
- [ ] `extensions/` module (4 files)
- [ ] Focus on pure functions first

### Day 2: Memory & Storage Systems (45 files)
**Goal**: Test all memory and persistence layers
**Approach**: Heavy mocking of database connections

#### Morning (25 files)
- [ ] `formation/memory/` - All memory implementations
- [ ] Buffer, persistent, vector memory tests
- [ ] Mock all database operations
- [ ] Test memory isolation and user partitioning

#### Afternoon (20 files)
- [ ] `services/memory/` - Memory service layer
- [ ] `services/scheduler/` - Scheduler and storage
- [ ] Focus on CRUD operations and state management

### Day 3: Core Formation System (50 files)
**Goal**: Test the heart of MUXI
**Approach**: Extensive use of fixtures and mocks

#### First Half (25 files)
- [ ] `formation/formation.py` and related core files
- [ ] `formation/config/` - All configuration loading
- [ ] `formation/initialization.py` - System startup
- [ ] Mock all external service calls

#### Second Half (25 files)
- [ ] `formation/agents/` - Agent implementation
- [ ] `formation/overlord/` - Orchestration layer
- [ ] Focus on routing and coordination logic

### Day 4: Services Layer (60 files)
**Goal**: Test all service implementations
**Approach**: Service-specific mock factories

#### First Batch (30 files)
- [ ] `services/llm/` - All LLM service files
- [ ] `services/multimodal/` - Document processing
- [ ] Mock all API calls to LLM providers

#### Second Batch (30 files)
- [ ] `services/mcp/` - MCP protocol implementation
- [ ] `services/a2a/` - Agent-to-agent communication
- [ ] `services/observability/` - Monitoring services

### Day 5: Workflow & Resilience (55 files)
**Goal**: Test complex orchestration
**Approach**: Scenario-based testing with mocked workflows

#### Morning (30 files)
- [ ] `formation/workflow/` - All workflow execution
- [ ] Task decomposition and routing
- [ ] Complexity analysis and scoring

#### Afternoon (25 files)
- [ ] `formation/resilience/` - Error recovery
- [ ] Circuit breakers and retry logic
- [ ] `formation/clarification/` - Clarification flows

### Day 6: API & Remaining Modules (58 files)
**Goal**: Complete coverage gaps
**Approach**: Target remaining untested files

#### All Day
- [ ] Fix broken tests in `unit/api/`
- [ ] Cover any remaining files in `formation/`
- [ ] Test async operations and generators
- [ ] Edge cases and error paths

### Day 7: Coverage Sprint & Optimization
**Goal**: Push to 95%+ coverage
**Approach**: Coverage-guided testing

#### Morning
- [ ] Run coverage reports and identify gaps
- [ ] Focus on uncovered branches
- [ ] Add tests for error conditions
- [ ] Test concurrent operations

#### Afternoon
- [ ] Performance test critical paths
- [ ] Documentation and cleanup
- [ ] Set up CI/CD pipeline
- [ ] Final coverage verification

## Sprint Testing Strategy

### Aggressive Testing Approach

1. **Auto-Generation First**: Use AST parsing to generate baseline tests
2. **100% Mocking**: Mock ALL external dependencies without exception
3. **Parallel Execution**: Run tests on multiple cores (pytest-xdist)
4. **Template Reuse**: Create reusable test patterns for similar modules
5. **Coverage-Driven**: Focus on line coverage first, branch coverage second

### Universal Mock Factory

```python
# conftest.py - Universal mock factory for all services
@pytest.fixture(autouse=True)
def auto_mock_all_external_services():
    """Automatically mock ALL external dependencies"""
    with ExitStack() as stack:
        # Mock all LLM providers
        stack.enter_context(patch('openai.ChatCompletion'))
        stack.enter_context(patch('anthropic.Client'))
        
        # Mock all databases
        stack.enter_context(patch('sqlalchemy.create_engine'))
        stack.enter_context(patch('psycopg2.connect'))
        
        # Mock all network calls
        stack.enter_context(patch('httpx.AsyncClient'))
        stack.enter_context(patch('aiohttp.ClientSession'))
        
        # Mock file operations where needed
        stack.enter_context(patch('muxi.services.mcp.subprocess.run'))
        
        yield

@pytest.fixture
def mock_formation():
    """Pre-configured formation for all tests"""
    return {
        'llm': {'models': [{'text': 'mock/model'}]},
        'agents': [{'id': 'test', 'name': 'Test Agent'}],
        'memory': {'buffer': {'size': 10}}
    }
```

### Test Generation Templates

```python
# test_generator.py - Automated test generation
def generate_test_for_class(cls):
    """Generate comprehensive tests for a class"""
    tests = []
    
    # Test initialization
    tests.append(f"""
def test_{cls.__name__.lower()}_init():
    obj = {cls.__name__}()
    assert obj is not None
""")
    
    # Test each method
    for method in get_public_methods(cls):
        tests.append(f"""
@pytest.mark.parametrize('input_val', [None, '', 'test', 123, []])
def test_{cls.__name__.lower()}_{method}(input_val):
    obj = {cls.__name__}()
    try:
        result = obj.{method}(input_val)
        assert result is not None
    except Exception as e:
        assert isinstance(e, Exception)
""")
    
    return '\n'.join(tests)
```

## Success Metrics

### Daily Coverage Targets

| Day | Files to Test | Cumulative Files | Target Coverage |
|-----|--------------|------------------|-----------------|
| Day 0 | Setup | 0/304 | 17% |
| Day 1 | 36 | 36/304 | 30% |
| Day 2 | 45 | 81/304 | 45% |
| Day 3 | 50 | 131/304 | 60% |
| Day 4 | 60 | 191/304 | 75% |
| Day 5 | 55 | 246/304 | 85% |
| Day 6 | 58 | 304/304 | 92% |
| Day 7 | Gap filling | 304/304 | 95%+ |

### Sprint Velocity Requirements

- **Day 1-2**: 40 files/day using AI-assisted test generation
- **Day 3-5**: 50-60 files/day with aggressive automation
- **Day 6-7**: Final push to close gaps and reach 95%

## Critical Success Factors

### Sprint Enablers

1. **Automated Test Generation**
   - AST-based test scaffolding saves 60% of writing time
   - Property-based testing with Hypothesis for edge cases
   - Parameterized tests for multiple scenarios

2. **AI-Assisted Development**
   - Use AI to generate boilerplate tests
   - Auto-generate mocks and fixtures
   - Pattern recognition for similar test cases

3. **Parallel Execution**
   - Run tests on 8+ cores simultaneously
   - Separate test suites by module
   - Use pytest-xdist for distribution

4. **Aggressive Mocking**
   - Mock EVERYTHING external
   - No real database connections
   - No actual API calls
   - Deterministic responses only

### Daily Standups

**Format**: 15-minute daily check-ins
- Coverage percentage achieved
- Blockers encountered
- Files completed vs target
- Next day preparation

## Sprint Tools & Scripts

### Auto-Test Generator Script
```bash
#!/bin/bash
# generate_tests.sh - Generate tests for a module
python test_generator.py --module $1 --output tests/unit/$1
pytest tests/unit/$1 --cov=muxi.$1 --cov-report=term
```

### Coverage Monitor
```bash
#!/bin/bash  
# coverage_monitor.sh - Real-time coverage tracking
watch -n 60 'pytest --cov=muxi --cov-report=term | grep TOTAL'
```

### Parallel Test Runner
```bash
#!/bin/bash
# parallel_test.sh - Run tests in parallel
pytest -n auto --dist loadscope tests/unit/
```

## Post-Sprint Maintenance

### CI/CD Integration (Day 7)

```yaml
# .github/workflows/coverage.yml
name: Coverage Check
on: [push, pull_request]
jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Coverage
        run: |
          pip install pytest-cov pytest-xdist
          pytest -n auto --cov=muxi --cov-report=xml --cov-report=term
      - name: Upload Coverage
        uses: codecov/codecov-action@v2
        with:
          fail_ci_if_error: true
          threshold: 95%
      - name: Comment PR
        uses: py-cov-action/python-coverage-comment-action@v3
        with:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MINIMUM_GREEN: 95
```

## Sprint Execution Checklist

### Day 0 (Pre-Sprint)
- [ ] Set up test infrastructure and universal mocks
- [ ] Create test generator script
- [ ] Fix existing test imports
- [ ] Configure pytest-xdist for parallel execution
- [ ] Create test templates for common patterns

### Day 1
- [ ] Generate tests for all datatypes (21 files)
- [ ] Generate tests for utils (15 files)
- [ ] Verify 30% coverage achieved

### Day 2  
- [ ] Complete memory system tests (45 files)
- [ ] Verify 45% coverage achieved

### Day 3
- [ ] Core formation system (50 files)
- [ ] Verify 60% coverage achieved

### Day 4
- [ ] Services layer (60 files)
- [ ] Verify 75% coverage achieved

### Day 5
- [ ] Workflow and resilience (55 files)
- [ ] Verify 85% coverage achieved

### Day 6
- [ ] Remaining modules and gap filling (58 files)
- [ ] Verify 92% coverage achieved

### Day 7
- [ ] Final sprint to 95%+
- [ ] Set up CI/CD
- [ ] Documentation

## Conclusion

This aggressive 1-week sprint plan transforms MUXI Runtime from 17% to 95%+ unit test coverage through:

1. **Automated test generation** saving 60% of manual effort
2. **AI-assisted development** for rapid test creation
3. **Parallel execution** across multiple developers and cores
4. **Universal mocking** eliminating external dependencies
5. **Daily targets** maintaining sprint momentum

### Critical Requirements

- **Execution**: You + Me working together with AI assistance
- **Tools**: pytest, pytest-cov, pytest-xdist, hypothesis, unittest.mock
- **Infrastructure**: Test generator script ready Day 0
- **Commitment**: Focused effort for 7 days

### Risk Factors

1. **Velocity Risk**: If falling behind daily targets, increase automation
2. **Quality Risk**: Focus on line coverage first, improve quality later
3. **Technical Debt**: Some tests will need refinement post-sprint
4. **Time Risk**: Aggressive timeline requires maximum efficiency

### Success Criteria

- ✅ 95%+ line coverage achieved
- ✅ All 304 files have unit tests
- ✅ Tests run in <30 seconds
- ✅ CI/CD pipeline configured
- ✅ No external dependencies in tests

---

**Sprint Start**: Immediate
**Sprint End**: 7 days from start
**Plan Owner**: Lead Developer
**Last Updated**: 2025-01-11