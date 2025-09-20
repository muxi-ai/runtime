# E2E Test Standardization Plan

## ✅ MIGRATION COMPLETE - ALL TESTS READY (2025-01-20)

### Executive Summary

**Status**: All 215+ E2E tests across 12 areas have been successfully migrated, linted, and are ready for execution in `tests/e2e_new/`.

### Migration Accomplishments

1. **Full Test Suite Migration**: 100% of tests migrated with complete test logic
2. **Standardized Structure**: All tests follow consistent patterns with base classes
3. **Test Isolation**: Each area properly isolated with dedicated base classes
4. **CI/CD Ready**: Uniform output format, error handling, and clean linting
5. **All Syntax Errors Fixed**: Tests compile and are executable
6. **Directory Structure Corrected**: Fixed nesting issues, clean organization

## Final State Analysis

### Test Distribution
- **Total Tests**: 215+ test files successfully migrated
- **Location**: `tests/e2e_new/` (clean structure, no nesting issues)
- **Base Classes**: 12 specialized base classes (one per area)
- **Common Module**: Comprehensive utilities and formatters

### Migration Summary by Area

| Area | Tests | Base Class | Pattern | Status |
|------|-------|------------|---------|--------|
| 1_foundation | 10 | BaseE2ETest | Runtime mod | ✅ Complete |
| 2_memory | 26 | BaseMemoryTest | Shared dir | ✅ Complete |
| 3_multimodal | 38 | BaseMultimodalTest | Shared dir | ✅ Complete |
| 4_mcp | 24 | BaseMCPTest | Shared dir | ✅ Complete |
| 5_artifacts | 15 | BaseArtifactsTest | Runtime mod | ✅ Complete |
| 6_knowledge | 19 | BaseKnowledgeTest | Shared dir | ✅ Complete |
| 7_orchestration | 25 | BaseOrchestrationTest | Separate | ✅ Complete |
| 8_clarification | 49 | BaseClarificationTest | Separate | ✅ Complete |
| 9_async | 12 | BaseAsyncTest | Runtime mod | ✅ Complete |
| 10_streaming | 6 | BaseStreamingTest | Runtime mod | ✅ Complete |
| 11_formatting | 4 | BaseFormattingTest | Runtime mod | ✅ Complete |
| 12_scheduling | 11 | BaseSchedulingTest | Runtime mod | ✅ Complete |

### All Migration Issues Resolved ✅

1. **✅ Formation Isolation**
   - Each area now has proper formation management
   - Base classes handle formation setup/teardown
   - No more interference between parallel tests

2. **✅ Model Fix Applied**
   - All instances of `gpt-5-nano` replaced with `gpt-4o-mini`
   - Applied across all 33+ formation files
   - Tests now use faster, working model

3. **✅ Consistent Loading Patterns**
   - All tests use standardized base classes
   - Uniform `Formation()` + `await formation.load(path)` pattern
   - Consistent path resolution via `Path(__file__).parent`

4. **✅ Proper Test Structure**
   - Base classes provide setup/teardown
   - Consistent error handling and cleanup
   - Standardized output formatting

5. **✅ All Linting Issues Fixed**
   - Fixed malformed class definitions across 7 base test files
   - Corrected 100+ import statements (numeric directory issue)
   - Removed all unused variables
   - All 215+ files now pass linting checks

6. **✅ Directory Structure Corrected**
   - Resolved nesting issue (tests were incorrectly in `tests/e2e_new/tests/e2e_new/`)
   - All areas now properly located in `tests/e2e_new/`
   - Clean, flat structure maintained
   - Removed redundant documentation files

## Current Status & Next Steps

### ✅ Migration Phase Complete
- All 215+ tests migrated with full test logic
- All syntax errors and import issues resolved
- Directory structure cleaned and organized
- Linting complete - all files pass checks

### 🚀 Ready for Validation Phase
Tests are now ready to be executed for functional validation:

```bash
# Run individual test
python tests/e2e_new/2_memory/test_2a1_basic_conversation_context.py

# Run entire area
pytest tests/e2e_new/2_memory/ -v

# Run all tests
pytest tests/e2e_new/ -v

# Use test runner script for detailed logging
bash .claude/scripts/test-and-log.sh tests/e2e_new/2_memory/test_2a1_basic_conversation_context.py
```

### Next Actions
1. **Functional Validation**: Run tests to verify they work with actual services
2. **Fix Functional Issues**: Address any failures due to API changes or service issues
3. **CI/CD Integration**: Set up automated test runs in CI pipeline
4. **Performance Baseline**: Establish execution time benchmarks
5. **Documentation Updates**: Update user guides with new test structure

## Standardization Requirements

### 1. Individual Formation Per Test
Each test must have its own formation directory to ensure:
- Complete isolation
- Parallel execution capability
- No configuration conflicts
- Easy debugging

### 2. Testing Style Guide & Best Practices

#### Core Testing Principles (from Lessons Learned)
1. **Always use real services** - No mocks in e2e tests
2. **Test with production formations** - Real configurations only
3. **Formation-first approach** - All tests through `overlord.chat()` interface
4. **Document test results immediately** - Capture successes and failures with context
5. **Focus tests on specific features** - Don't test unrelated capabilities
6. **Handle async properly** - Track request IDs for result correlation

#### Standardized Output Format
Every test MUST emit this exact format for CI/CD parsing:

```python
# tests/e2e/common/output.py
class TestOutputFormatter:
    """Standardized test output format for all e2e tests."""

    @staticmethod
    def print_test_header(test_name: str, description: str):
        """Print standardized test header."""
        print(f"\n{'='*60}")
        print(f"TEST: {test_name}")
        print(f"Description: {description}")
        print(f"{'='*60}\n")

    @staticmethod
    def print_exchange(user: str, assistant: str, passed: bool, check: str = ""):
        """Print standardized chat exchange."""
        print(f"User: {user}")
        print(f"Assistant: {assistant[:200]}...")
        if passed:
            print(f"✅ PASS: {check}")
        else:
            print(f"❌ FAIL: {check}")
        print()

    @staticmethod
    def print_test_result(test_name: str, success: bool, checks: List[str],
                          transcript: List[Tuple[str, str]], duration: float):
        """Print standardized test result summary."""
        print(f"\n{'='*40}")
        print("\n### Test Result:")
        if success:
            print(f"  🎉 SUCCESS: {test_name}")
            for check in checks:
                print(f"  ✓ {check}")
        else:
            print(f"  ❌ FAILED: {test_name}")
            for check in checks:
                print(f"  ✗ {check}")

        print(f"\n  Duration: {duration:.2f}s")
        print(f"\n{'='*40}")

        print("\n### Chat transcript:")
        for user_msg, system_msg in transcript:
            print(f"User: {user_msg}")
            print(f"System: {system_msg[:500]}...")
            print()
```

#### Dynamic Timeout Management
```python
# tests/e2e/common/timeouts.py
from typing import Dict

class TestTimeouts:
    """Centralized timeout management based on test patterns."""

    # Known test duration patterns (in seconds)
    TIMEOUT_MAP: Dict[str, int] = {
        # Quick tests (10-30s)
        "greeting": 10,
        "simple_chat": 15,
        "memory_recall": 20,
        "clarification": 30,

        # Medium tests (30-60s)
        "mcp_tool_use": 45,
        "file_generation": 60,
        "knowledge_query": 45,
        "scheduling": 40,

        # Long tests (60-180s)
        "workflow_decomposition": 120,
        "multi_agent": 90,
        "large_document": 180,
        "video_processing": 300,

        # Very long tests (3-5 minutes)
        "complex_workflow": 300,
        "recursive_clarification": 180,
        "batch_processing": 240,
    }

    @classmethod
    def get_timeout(cls, test_type: str = None, message: str = None,
                   files: list = None) -> int:
        """Get appropriate timeout based on test characteristics."""
        # Check for known test types
        if test_type and test_type in cls.TIMEOUT_MAP:
            return cls.TIMEOUT_MAP[test_type]

        # Dynamic detection based on content
        if files:
            total_size = sum(len(f.get('content', '')) for f in files)
            if total_size > 100_000_000:  # >100MB
                return 300
            elif total_size > 10_000_000:  # >10MB
                return 180
            elif total_size > 1_000_000:   # >1MB
                return 120

        # Check message complexity
        if message:
            if any(keyword in message.lower() for keyword in
                   ['analyze', 'complex', 'detailed', 'comprehensive']):
                return 120
            elif any(keyword in message.lower() for keyword in
                     ['workflow', 'plan', 'decompose', 'steps']):
                return 180

        # Default timeout
        return 60

    @classmethod
    def with_buffer(cls, base_timeout: int, buffer_percent: int = 20) -> int:
        """Add buffer to timeout for safety."""
        return int(base_timeout * (1 + buffer_percent / 100))
```

#### Event Loop Management Pattern (Critical)
```python
# tests/e2e/common/fixtures.py
from concurrent.futures import ThreadPoolExecutor
import asyncio

def run_test_in_thread(test_func):
    """Run test in separate thread to avoid event loop conflicts."""
    def wrapper(*args, **kwargs):
        with ThreadPoolExecutor() as executor:
            future = executor.submit(test_func, *args, **kwargs)
            return future.result()
    return wrapper

# Usage in tests
@run_test_in_thread
def test_example():
    formation = Formation()
    formation.load("path/to/formation")
    overlord = formation.start_overlord()

    # Use asyncio.run() for each async call
    response = asyncio.run(overlord.chat("Hello"))

    formation.stop_overlord()
```

#### Test Data Fixtures and Seeding
```python
# tests/e2e/common/fixtures/data.py
from typing import List, Dict, Any
import json
import uuid
from datetime import datetime

class TestDataGenerator:
    """Generate consistent test data for reproducible tests."""

    @staticmethod
    def create_test_documents(count: int = 10, prefix: str = "test") -> List[Dict]:
        """Generate consistent test documents for knowledge tests."""
        docs = []
        for i in range(count):
            docs.append({
                "id": f"{prefix}_doc_{i}",
                "title": f"Test Document {i}",
                "content": f"This is test content for document {i}. " * 10,
                "metadata": {
                    "created_at": datetime.utcnow().isoformat(),
                    "tags": ["test", f"category_{i % 3}"],
                    "version": "1.0"
                }
            })
        return docs

    @staticmethod
    def seed_memory_data(overlord, user_id: str, conversations: int = 5):
        """Pre-populate memory with test conversations for recall tests."""
        test_exchanges = [
            ("What's the capital of France?", "The capital of France is Paris."),
            ("Tell me about Python", "Python is a high-level programming language."),
            ("What's 2+2?", "2+2 equals 4."),
            ("Hello", "Hello! How can I help you today?"),
            ("Goodbye", "Goodbye! Have a great day!")
        ]

        for i in range(min(conversations, len(test_exchanges))):
            user_msg, assistant_msg = test_exchanges[i]
            # Simulate conversation to populate memory
            asyncio.run(overlord.chat(user_msg, user_id=user_id))

    @staticmethod
    def create_test_files(file_types: List[str] = ["txt", "json", "md"]) -> Dict[str, str]:
        """Create test files for multimodal and artifact tests."""
        files = {}
        for file_type in file_types:
            if file_type == "txt":
                files["test.txt"] = "This is a test text file.\n" * 5
            elif file_type == "json":
                files["test.json"] = json.dumps({"test": True, "data": [1, 2, 3]})
            elif file_type == "md":
                files["test.md"] = "# Test Markdown\n\n- Item 1\n- Item 2\n"
        return files

    @staticmethod
    def generate_unique_id(prefix: str = "test") -> str:
        """Generate unique ID for test isolation."""
        return f"{prefix}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
```

#### Error Recovery and Retry Logic
```python
# tests/e2e/common/retry.py
from typing import Callable, Any, Optional
import asyncio
import time
from functools import wraps

class RetryConfig:
    """Configuration for retry behavior."""
    DEFAULT_ATTEMPTS = 3
    DEFAULT_DELAY = 1.0  # seconds
    DEFAULT_BACKOFF = 2.0  # exponential backoff multiplier

    TRANSIENT_ERRORS = [
        "Connection reset",
        "Timeout",
        "Rate limit",
        "Service unavailable"
    ]

class TestRetry:
    """Retry logic for handling transient failures in tests."""

    @staticmethod
    def with_retry(
        attempts: int = RetryConfig.DEFAULT_ATTEMPTS,
        delay: float = RetryConfig.DEFAULT_DELAY,
        backoff: float = RetryConfig.DEFAULT_BACKOFF,
        exceptions: tuple = (Exception,)
    ):
        """Decorator for retrying test operations."""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay

                for attempt in range(attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if TestRetry._is_transient(e) and attempt < attempts - 1:
                            print(f"  Retry {attempt + 1}/{attempts} after {current_delay}s: {e}")
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            raise

                raise last_exception

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay

                for attempt in range(attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if TestRetry._is_transient(e) and attempt < attempts - 1:
                            print(f"  Retry {attempt + 1}/{attempts} after {current_delay}s: {e}")
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            raise

                raise last_exception

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator

    @staticmethod
    def _is_transient(exception: Exception) -> bool:
        """Check if exception is likely transient and worth retrying."""
        error_msg = str(exception).lower()
        return any(err.lower() in error_msg for err in RetryConfig.TRANSIENT_ERRORS)

# Circuit breaker for service failures
class CircuitBreaker:
    """Prevent cascading failures by failing fast after threshold."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.is_open:
            if time.time() - self.last_failure_time > self.timeout:
                self.is_open = False
                self.failures = 0
            else:
                raise RuntimeError(f"Circuit breaker open - service failures exceeded {self.failure_threshold}")

        try:
            result = func(*args, **kwargs)
            self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.is_open = True
            raise
```

### 2a. Unified Test Structure via Common Module

#### Core Philosophy: DRY (Don't Repeat Yourself)
Create `tests/e2e/common/` module with reusable components instead of duplicating code across 215 tests.

```python
# tests/e2e/common/__init__.py
from .base import BaseE2ETest, FormationManager
from .fixtures import formation, test_logger
from .assertions import assert_chat_response, assert_scheduling_success
from .utils import wait_for_async_completion

# tests/e2e/common/base.py
class BaseE2ETest:
    """Base class for all E2E tests with common functionality."""

    async def setup_formation(self, template="standard", **overrides):
        """Single method for formation setup with modifications."""
        fm = FormationManager()
        return await fm.create(template, **overrides)

    async def assert_conversation_flow(self, overlord, exchanges):
        """Common assertion for multi-turn conversations."""
        for user_msg, expected_pattern in exchanges:
            response = await overlord.chat(user_msg)
            assert expected_pattern in response.lower()

# tests/e2e/common/formations.py
class FormationManager:
    """Centralized formation management with runtime modifications."""

    BASE_PATH = Path(__file__).parent / "formations"

    TEMPLATES = {
        "standard": "base/standard",
        "minimal": "base/minimal",
        "complex": "base/complex",
    }

    async def create(self, template: str, **overrides):
        """Create formation with runtime modifications."""
        formation = Formation()
        path = self.BASE_PATH / self.TEMPLATES[template]
        await formation.load(str(path))

        # Apply overrides in a type-safe way
        for key, value in overrides.items():
            self._apply_override(formation, key, value)

        return formation

    def _apply_override(self, formation, key, value):
        """Apply configuration override with validation."""
        # Predefined override patterns
        OVERRIDE_PATTERNS = {
            "credential_mode": lambda v: {"user_credentials": {"mode": v}},
            "webhook_url": lambda v: {"async": {"webhook_url": v}},
            "memory_type": lambda v: {"memory": {"type": v}},
            "buffer_size": lambda v: {"memory": {"buffer_size": v}},
            "clarification": lambda v: {"clarification": {"enabled": v}},
        }

        if key in OVERRIDE_PATTERNS:
            config_update = OVERRIDE_PATTERNS[key](value)
            deep_update(formation.config, config_update)
```

#### Standardized Test Implementation Example
```python
# tests/e2e/12_scheduling/test_basic_scheduling.py
from tests.e2e.common import BaseE2ETest, TestOutputFormatter, TestTimeouts
import time

class TestScheduling(BaseE2ETest):
    """Test scheduling functionality."""

    @run_test_in_thread
    def test_12a1_basic_scheduling(self):
        """Test basic scheduling detection and creation."""
        formatter = TestOutputFormatter()
        start_time = time.time()

        # Print header
        formatter.print_test_header(
            test_name="12a1_basic_scheduling",
            description="Test basic scheduling detection and creation"
        )

        # Setup formation
        formation = self.setup_formation("standard")
        overlord = formation.start_overlord()

        # Get appropriate timeout
        timeout = TestTimeouts.get_timeout("scheduling")

        # Test exchanges
        exchanges = [
            ("Schedule a meeting tomorrow at 3pm", "scheduled successfully"),
            ("Show my schedule", "meeting tomorrow at 3pm"),
        ]

        transcript = []
        all_passed = True
        checks_passed = []

        for user_msg, expected in exchanges:
            response = asyncio.run(
                asyncio.wait_for(
                    overlord.chat(user_msg, user_id="test_user"),
                    timeout=timeout
                )
            )

            passed = expected in response.lower()
            all_passed = all_passed and passed

            formatter.print_exchange(user_msg, response, passed, expected)
            transcript.append((user_msg, response))

            if passed:
                checks_passed.append(f"Detected '{expected}' in response")

        # Clean up
        formation.stop_overlord()

        # Print results
        duration = time.time() - start_time
        formatter.print_test_result(
            test_name="12a1_basic_scheduling",
            success=all_passed,
            checks=checks_passed,
            transcript=transcript,
            duration=duration
        )

        assert all_passed, "Test failed - see output above"
```

### 3. Simplified Formation Structure

```
tests/e2e/
├── common/                 # Centralized shared resources
│   ├── __init__.py
│   ├── base.py             # BaseE2ETest class
│   ├── fixtures.py         # Common pytest fixtures
│   ├── formations/
│   │   ├── base/           # 3 base templates
│   │   │   ├── standard.yaml
│   │   │   ├── minimal.yaml
│   │   │   └── complex.yaml
│   │   └── agents/         # Shared agent configs
│   │       ├── assistant.yaml
│   │       ├── researcher.yaml
│   │       └── writer.yaml
│   └── utils.py            # Test utilities
├── [area]/                 # Area-specific tests (1-12)
│   ├── test_*.py           # Test files
│   └── formations/         # Only for specialized (21% of tests)
│       └── [unique_test]/  # Truly unique formations
└── logs/                   # Test execution logs
```

**Key Simplification**: Move ALL common resources to `tests/e2e/common/` instead of duplicating across areas.

### 3a. Formation Sharing Strategy - Three Distinct Patterns

#### Pattern 1: Runtime Parameter Modification (~120 tests, 56%)
Tests that use the **same base formation** and modify 1-2 parameters at runtime.

```python
# Example: Credential mode variations (Area 8)
class TestCredentialModes:
    async def test_credential_flow(self, mode):
        formation = await self.setup_formation("standard")
        # Runtime modification
        formation.config["user_credentials"] = {"mode": mode}
        overlord = await formation.start_overlord()
```

**Use cases:**
- Credential mode changes (dynamic/redirect/inline)
- Async/webhook URL overrides
- Feature toggles (clarification on/off)
- Buffer size adjustments

#### Pattern 2: Shared Directory with Multiple YAMLs (~50 tests, 23%)
Tests that share the **same directory** with common agents/MCP/secrets but use **different formation YAML files**.

**Real Example from Memory Tests:**
```
tests/e2e/2_memory/formations/formation-memory/
├── agents/                           # Shared agents directory
│   └── memory_agent.yaml
├── secrets.enc                       # Shared secrets
├── .key                             # Shared key
├── formation-basic.yaml             # Basic memory test
├── formation-buffer-local.yaml      # Buffer with local storage
├── formation-buffer-remote.yaml     # Buffer with remote storage
├── formation-postgres.yaml          # PostgreSQL memory
├── formation-sqlite.yaml            # SQLite memory
└── formation-auto-extract.yaml      # Auto-extraction test
```

**Loading Example:**
```python
# Each test loads its specific YAML from the shared directory
await formation.load("tests/e2e/2_memory/formations/formation-memory/formation-buffer-local.yaml")
# or
await formation.load("tests/e2e/2_memory/formations/formation-memory/formation-postgres.yaml")
```

**Use cases:**
- Memory tests (different storage backends, same agents)
- MCP tests (different server configs, same directory structure)
- Agent tests (different specializations, shared base configs)
- Knowledge tests (different vector stores, same documents)

```python
# Example: Memory configuration tests (Area 2)
class TestMemoryConfigurations:
    async def test_buffer_memory(self):
        # Load specific YAML from shared directory
        formation = Formation()
        await formation.load("formations/formation-memory/formation-buffer-local.yaml")

    async def test_postgres_memory(self):
        # Same agents/secrets, different YAML
        formation = Formation()
        await formation.load("formations/formation-memory/formation-postgres.yaml")
```

**Use cases:**
- Memory backend variations (buffer/sqlite/postgres/faissx)
- Clarification style variations (brief/conversational/formal)
- Multi-agent configurations with same agents but different orchestration
- Different MCP server combinations

#### Pattern 3: Completely Separate Formations (~45 tests, 21%)
Tests requiring **unique formations** with custom agents/workflows/SOPs.

```
tests/e2e/7_orchestration/formations/
├── formation-workflow-test/      # Unique workflow setup
│   ├── formation.yaml
│   ├── agents/
│   └── sops/
├── formation-a2a/               # Unique A2A configuration
│   ├── formation1/
│   └── formation2/
└── formation-multi-agent-sop/   # Unique SOP setup
```

**Use cases:**
- Complex multi-agent orchestrations
- Custom SOPs and workflows
- Specialized MCP configurations
- Multimodal tests with specific file types
- Clarification tests with unique flows

### 3b. Test Area to Pattern Mapping

| Test Area | Pattern | Rationale |
|-----------|---------|-----------|
| **1_foundation** | Pattern 1 (Runtime) | Basic tests, only differ in params |
| **2_memory** | Pattern 2 (Shared Dir) | Same agents, different memory backends |
| **3_multimodal** | Pattern 3 (Separate) | Each test needs unique files/configs |
| **4_mcp** | Pattern 2 (Shared Dir) | Same MCP tools, different server configs |
| **5_artifacts** | Pattern 1 (Runtime) | Same formation, different file generation params |
| **6_knowledge** | Pattern 2 (Shared Dir) | Same docs, different vector stores |
| **7_orchestration** | Pattern 3 (Separate) | Unique workflows, SOPs, A2A setups |
| **8_clarification** | Pattern 3 (Separate) | Complex flows need isolation |
| **9_async** | Pattern 1 (Runtime) | Toggle async/webhook URLs |
| **10_streaming** | Pattern 1 (Runtime) | Toggle streaming flag |
| **11_formatting** | Pattern 1 (Runtime) | Different format options |
| **12_scheduling** | Pattern 1 (Runtime) | Same scheduler, different schedules |

### 3c. Implementation Examples for Each Pattern

#### Pattern 1 Example: Scheduling Tests
```python
# tests/e2e/12_scheduling/test_12a1_basic_scheduling.py
from tests.e2e.common import BaseE2ETest

class TestBasicScheduling(BaseE2ETest):
    async def run(self):
        # Single shared formation
        formation_path = Path(__file__).parent / "formations" / "formation-scheduling"

        # Test 1: Daily schedule (runtime modification)
        await self.setup_formation(formation_path)
        response = await self.overlord.chat("Schedule daily at 9am")

        # Test 2: Weekly schedule (same formation, different request)
        response = await self.overlord.chat("Schedule weekly on Monday")
```

#### Pattern 2 Example: Memory Tests
```python
# tests/e2e/2_memory/test_2b1_buffer_memory.py
from tests.e2e.common import BaseE2ETest

class TestBufferMemory(BaseE2ETest):
    async def run(self):
        # Shared directory, different YAMLs
        formation_dir = Path(__file__).parent / "formations" / "formation-memory"

        # Test with local buffer
        await self.setup_formation(formation_dir / "formation-buffer-local.yaml")

        # Test with remote buffer (different YAML, same directory)
        await self.cleanup_formation()
        await self.setup_formation(formation_dir / "formation-buffer-remote.yaml")
```

#### Pattern 3 Example: Orchestration Tests
```python
# tests/e2e/7_orchestration/test_7b1_workflow_decomposition.py
from tests.e2e.common import BaseE2ETest

class TestWorkflowDecomposition(BaseE2ETest):
    async def run(self):
        # Completely separate formation with unique workflow
        formation_path = Path(__file__).parent / "formations" / "formation-workflow-complex"

        # This formation has custom SOPs, agents, and workflow configs
        await self.setup_formation(formation_path)
```

#### Tests Requiring Unique Formations (~45 tests, 21%)

1. **Complex Multi-Agent Tests** (Area 7: Orchestration)
   - Different agent combinations
   - Unique SOPs and workflows
   - Custom agent capabilities

2. **Specialized MCP Configurations** (Area 4: MCP)
   - Different MCP server combinations
   - Unique authentication requirements
   - Custom tool configurations

3. **Knowledge Base Tests** (Area 6: Knowledge)
   - Different document sets
   - Unique vector store configurations
   - Custom extraction settings

### 3b. Consolidated Runtime Modification Patterns

Just **3 main patterns** cover all modifications:

| Pattern | Purpose | Tests | Implementation |
|---------|---------|-------|----------------|
| **Config Override** | Modify formation.config values | ~120 | `setup_formation("standard", **config_overrides)` |
| **Resource Injection** | Add secrets, ports, connections | ~35 | `formation.inject_resources(secrets=..., ports=...)` |
| **Feature Toggle** | Enable/disable capabilities | ~25 | `formation.toggle_features(clarification=True, workflow=False)` |

```python
# All 12 categories simplified to 3 method calls
formation = await self.setup_formation("standard",
    # Config overrides (handles 8 of the 12 categories)
    credential_mode="dynamic",
    memory_type="buffer",
    webhook_url="http://localhost:8080",

    # Resource injection (handles 3 categories)
    secrets={"GITHUB_TOKEN": "..."},

    # Feature toggles (handles remaining category)
    features={"clarification": True}
)

### 3c. Shared Formation Templates

#### Template 1: Standard Formation (base/standard/)
```yaml
# Used by 60% of tests
id: standard-test-formation
llm:
  models:
    - text: "openai/gpt-4o-mini"
memory:
  type: buffer
  buffer_size: 10
agents:
  - id: assistant
    path: ../../shared/agents/assistant.yaml
```

#### Template 2: Minimal Formation (base/minimal/)
```yaml
# Used by 20% of tests - simple single-agent
id: minimal-test-formation
llm:
  models:
    - text: "openai/gpt-4o-mini"
agents:
  - id: assistant
    model: inline
```

#### Template 3: Complex Formation (base/complex/)
```yaml
# Used by 10% of tests - multi-agent orchestration
id: complex-test-formation
llm:
  models:
    - text: "openai/gpt-4o-mini"
memory:
  type: persistent
  persistent:
    type: sqlite
agents:
  - path: ../../shared/agents/researcher.yaml
  - path: ../../shared/agents/writer.yaml
  - path: ../../shared/agents/reviewer.yaml
mcp:
  servers:
    - path: ../../shared/mcp/filesystem.yaml
```

### 4. CI/CD Requirements
- Tests must be runnable with `pytest tests/e2e/[area]/test_*.py`
- Each test must clean up resources
- No hardcoded paths or environment dependencies
- Clear success/failure reporting
- All tests must output logs to `tests/logs/` for analysis
- All required services must be running (see Section 4b)

### 4a. Simplified Logging Strategy

#### Universal Approach (Local & CI/CD)
```bash
# Same command for both environments
bash .claude/scripts/test-and-log.sh tests/e2e/[area]/test_*.py

# Script handles environment detection
if [ "$CI" = "true" ]; then
    # CI/CD: JSON output for parsing
    pytest "$@" --json-report --json-report-file=tests/logs/report.json
else
    # Local: Human-readable with timestamps
    pytest "$@" -v | tee tests/logs/$(date +%Y%m%d_%H%M%S).log
fi
```

#### Minimal pytest Configuration
```ini
# pytest.ini - Keep it simple
[tool:pytest]
log_cli = true
log_cli_level = INFO
log_file = tests/logs/pytest.log
addopts = --tb=short --strict-markers

# Markers for test organization
markers =
    serial: Tests that must run sequentially
    rate_limited: Tests with API rate limits
    slow: Tests taking >10 seconds
```

#### GitHub Actions - Simplified
```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run E2E Tests
        run: bash .claude/scripts/test-and-log.sh tests/e2e
        continue-on-error: true

      - name: Upload Logs
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-logs-${{ github.run_id }}
          path: tests/logs/
          retention-days: 7
```

**Key Simplification**: Let `test-and-log.sh` handle all complexity. No custom scripts needed.

### 4b. Required Services for Test Execution

#### Core Services (MUST be running)

| Service | Purpose | Test Areas Affected | Setup Command |
|---------|---------|-------------------|---------------|
| **PostgreSQL** | Persistent memory storage | 2_memory, 6_knowledge | `docker run -p 5432:5432 postgres:15` |
| **FAISSx (no auth)** | Vector search without auth | 2_memory, 6_knowledge | `faissx.server run --port 45678` |
| **FAISSx (with auth)** | Vector search with auth | 2_memory, 7_orchestration | `faissx.server run --port 65432 --enable-auth --auth-file tests/assets/formations/faissx-auth.json` |
| **Webhook Receiver** | Async response handling | 9_async, 12_scheduling | `python utils/webhook_server.py` |
| **A2A Registry** | Agent-to-agent communication | 7_orchestration | `python utils/a2a_registry.py` |

#### Test Credentials Management

All test credentials are **already configured** in:
- **Encrypted secrets**: `tests/assets/formations/secrets.enc`
- **Encryption key**: `tests/assets/formations/.key`

#### Secrets Setup for Standardized Tests

```bash
# Step 1: Copy existing secrets to common directory
cp tests/assets/formations/secrets.enc tests/e2e/common/formations/
cp tests/assets/formations/.key tests/e2e/common/formations/

# Step 2: Create symlinks from each formation directory
cd tests/e2e/common/formations/base/standard/
ln -s ../../secrets.enc secrets.enc
ln -s ../../.key .key

cd tests/e2e/common/formations/base/minimal/
ln -s ../../secrets.enc secrets.enc
ln -s ../../.key .key

cd tests/e2e/common/formations/base/complex/
ln -s ../../secrets.enc secrets.enc
ln -s ../../.key .key
```

#### Formation YAML with Secrets Reference

```yaml
# tests/e2e/common/formations/base/standard/formation.yaml
id: standard-test-formation
secrets_file: secrets.enc  # Automatically decrypted using .key
llm:
  models:
    - text: "openai/gpt-4o-mini"
```

#### Automated Symlink Creation

```python
# scripts/migrate_e2e_tests.py - updated setup_new_structure method
def setup_new_structure(self):
    """Step 2: Create standardized structure with secrets."""
    # Create common module
    common = self.new_path / "common"
    common.mkdir(parents=True, exist_ok=True)

    # Copy secrets to common
    src_secrets = Path("tests/assets/formations/secrets.enc")
    src_key = Path("tests/assets/formations/.key")
    dst_secrets = common / "formations" / "secrets.enc"
    dst_key = common / "formations" / ".key"

    shutil.copy2(src_secrets, dst_secrets)
    shutil.copy2(src_key, dst_key)

    # Create base formations
    for base_type in ["standard", "minimal", "complex"]:
        base_dir = common / "formations" / "base" / base_type
        base_dir.mkdir(parents=True, exist_ok=True)

        # Create symlinks to secrets
        (base_dir / "secrets.enc").symlink_to("../../secrets.enc")
        (base_dir / ".key").symlink_to("../../.key")

    print(f"✓ Created new structure with secrets at {self.new_path}")
```

#### No Mock Services Policy

- **All tests use real services** with dedicated test accounts
- **Rate-limited services** (GitHub, Linear) run sequentially
- **Test data isolation** via unique prefixes (e.g., `test_<timestamp>_`)
- **Automatic cleanup** after test completion


#### Local Development Setup Script
```bash
#!/bin/bash
# scripts/start_test_services.sh
echo "Starting required services for E2E tests..."

# PostgreSQL (via Docker)
docker run -d --name postgres-test -p 5432:5432 \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=muxi_test \
  postgres:15

# FAISSx servers (both auth and no-auth)
faissx.server run --port 45678 &
echo $! > /tmp/faissx_noauth.pid

faissx.server run --port 65432 \
  --enable-auth \
  --auth-file tests/assets/formations/faissx-auth.json &
echo $! > /tmp/faissx_auth.pid

# Webhook receiver
python utils/webhook_server.py &
echo $! > /tmp/webhook_server.pid

# A2A Registry
python utils/a2a_registry.py &
echo $! > /tmp/a2a_registry.pid

# Verify all services are running
sleep 5
nc -z localhost 5432 && echo "✓ PostgreSQL ready" || echo "✗ PostgreSQL failed"
nc -z localhost 45678 && echo "✓ FAISSx (no auth) ready" || echo "✗ FAISSx (no auth) failed"
nc -z localhost 65432 && echo "✓ FAISSx (with auth) ready" || echo "✗ FAISSx (auth) failed"
nc -z localhost 8080 && echo "✓ Webhook server ready" || echo "✗ Webhook failed"
nc -z localhost 8090 && echo "✓ A2A Registry ready" || echo "✗ A2A Registry failed"

echo "All services started. Secrets will be loaded from formation YAML files."
echo "Run tests with: pytest tests/e2e"
```

#### Docker Compose for All Test Services
```yaml
# tests/e2e/docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    container_name: muxi-test-postgres
    environment:
      POSTGRES_PASSWORD: testpass
      POSTGRES_DB: muxi_test
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  faissx-noauth:
    build:
      context: .
      dockerfile: tests/e2e/Dockerfile.faissx
    container_name: muxi-test-faissx-noauth
    command: ["faissx.server", "run", "--port", "45678"]
    ports:
      - "45678:45678"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:45678/health"]
      interval: 5s
      timeout: 5s
      retries: 5

  faissx-auth:
    build:
      context: .
      dockerfile: tests/e2e/Dockerfile.faissx
    container_name: muxi-test-faissx-auth
    command: ["faissx.server", "run", "--port", "65432", "--enable-auth", "--auth-file", "/auth/faissx-auth.json"]
    volumes:
      - ./tests/assets/formations/faissx-auth.json:/auth/faissx-auth.json:ro
    ports:
      - "65432:65432"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:65432/health"]
      interval: 5s
      timeout: 5s
      retries: 5

  webhook:
    build:
      context: .
      dockerfile: tests/e2e/Dockerfile.services
    container_name: muxi-test-webhook
    command: ["python", "utils/webhook_server.py"]
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 5s
      timeout: 5s
      retries: 5

  a2a-registry:
    build:
      context: .
      dockerfile: tests/e2e/Dockerfile.services
    container_name: muxi-test-a2a
    command: ["python", "utils/a2a_registry.py"]
    ports:
      - "8090:8090"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 5s
      timeout: 5s
      retries: 5
```

#### Dockerfile for Test Services
```dockerfile
# tests/e2e/Dockerfile.services
FROM python:3.10-slim

WORKDIR /app

# Copy utils directory
COPY utils/ /app/utils/

# Install dependencies
RUN pip install --no-cache-dir flask requests aiohttp

# Default command (overridden by docker-compose)
CMD ["python", "-m", "http.server", "8000"]
```

#### Dockerfile for FAISSx
```dockerfile
# tests/e2e/Dockerfile.faissx
FROM python:3.10-slim

# Install FAISSx
RUN pip install --no-cache-dir faissx

# Default command (overridden by docker-compose)
CMD ["faissx.server", "run"]
```

#### One-Command Test Environment Setup
```bash
# Start all test services with Docker Compose
docker-compose -f tests/e2e/docker-compose.yml up -d

# Wait for all services to be healthy
docker-compose -f tests/e2e/docker-compose.yml ps

# Run tests
pytest tests/e2e

# Stop all services when done
docker-compose -f tests/e2e/docker-compose.yml down
```

#### Service Health Check
```python
# tests/e2e/common/health_check.py
import time
import socket
from typing import List, Tuple

def wait_for_services(services: List[Tuple[str, int]], timeout: int = 30):
    """Wait for all required services to be available."""
    start_time = time.time()

    for service_name, port in services:
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result == 0:
                    print(f"✓ {service_name} is ready on port {port}")
                    break
            except:
                pass

            time.sleep(1)
        else:
            raise RuntimeError(f"Service {service_name} on port {port} not available after {timeout}s")

# Use in conftest.py
@pytest.fixture(scope="session", autouse=True)
def ensure_services():
    """Ensure all required services are running before tests."""
    required_services = [
        ("PostgreSQL", 5432),
        ("FAISSx (no auth)", 45678),
        ("FAISSx (with auth)", 65432),
        ("Webhook Server", 8080),
        ("A2A Registry", 8090),
    ]

    wait_for_services(required_services)
    yield
    # Cleanup if needed
```

#### Service-Specific Test Markers
```python
# Mark tests that require specific services
@pytest.mark.requires_postgres
async def test_persistent_memory():
    pass

@pytest.mark.requires_faissx
async def test_vector_search():
    pass

@pytest.mark.requires_webhook
async def test_async_execution():
    pass

@pytest.mark.requires_a2a
async def test_agent_communication():
    pass

# Skip tests if service unavailable
@pytest.mark.skipif(not is_service_available("postgres", 5432),
                    reason="PostgreSQL not running")
async def test_database_operations():
    pass
```

#### Test Result Persistence and Tracking
```python
# tests/e2e/common/results.py
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

class TestResultTracker:
    """Track and persist test results for analysis and trending."""

    def __init__(self, db_path: str = "tests/results/test_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize results database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    test_area TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    duration REAL NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    metadata TEXT,
                    git_commit TEXT,
                    environment TEXT
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_test_name ON test_results (test_name)
            ''')

    def record_result(self, test_name: str, test_area: str, duration: float,
                     success: bool, error_message: Optional[str] = None,
                     metadata: Optional[Dict] = None):
        """Record a test result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO test_results
                (test_name, test_area, timestamp, duration, success, error_message, metadata, git_commit, environment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                test_name,
                test_area,
                datetime.utcnow().isoformat(),
                duration,
                success,
                error_message,
                json.dumps(metadata) if metadata else None,
                self._get_git_commit(),
                self._get_environment()
            ))

    def get_performance_trend(self, test_name: str, limit: int = 30) -> List[Dict]:
        """Get performance trend for a test."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT timestamp, duration, success
                FROM test_results
                WHERE test_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (test_name, limit))
            return [
                {"timestamp": row[0], "duration": row[1], "success": row[2]}
                for row in cursor
            ]

    def detect_regression(self, test_name: str, current_duration: float,
                         threshold: float = 1.2) -> bool:
        """Detect if test has regressed (>20% slower by default)."""
        trend = self.get_performance_trend(test_name, limit=10)
        if len(trend) < 5:
            return False  # Not enough history

        # Calculate baseline from successful runs
        baseline = [t["duration"] for t in trend if t["success"]][:5]
        if not baseline:
            return False

        avg_baseline = sum(baseline) / len(baseline)
        return current_duration > avg_baseline * threshold

    @staticmethod
    def _get_git_commit() -> str:
        """Get current git commit hash."""
        try:
            import subprocess
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True
            ).strip()[:8]
        except:
            return "unknown"

    @staticmethod
    def _get_environment() -> str:
        """Detect test environment."""
        import os
        if os.getenv("CI"):
            return "ci"
        elif os.getenv("DOCKER_CONTAINER"):
            return "docker"
        else:
            return "local"
```

#### Formation Validation
```python
# tests/e2e/common/validation.py
import yaml
import socket
from pathlib import Path
from typing import List, Tuple, Dict, Any

class FormationValidator:
    """Validate formations before test execution."""

    REQUIRED_FIELDS = ["id", "llm", "agents"]
    REQUIRED_LLM_FIELDS = ["models"]

    @classmethod
    def validate_formation(cls, formation_path: Path) -> Tuple[bool, List[str]]:
        """Validate formation has required fields and structure."""
        errors = []

        if not formation_path.exists():
            return False, [f"Formation not found: {formation_path}"]

        try:
            if formation_path.is_dir():
                # Look for formation.yaml in directory
                yaml_path = formation_path / "formation.yaml"
                if not yaml_path.exists():
                    return False, [f"No formation.yaml in {formation_path}"]
                formation_path = yaml_path

            with open(formation_path) as f:
                config = yaml.safe_load(f)

            # Check required fields
            for field in cls.REQUIRED_FIELDS:
                if field not in config:
                    errors.append(f"Missing required field: {field}")

            # Validate LLM configuration
            if "llm" in config:
                if "models" not in config["llm"]:
                    errors.append("LLM configuration missing 'models'")
                else:
                    models = config["llm"]["models"]
                    if not models:
                        errors.append("No models configured")
                    else:
                        # Check for text model (required)
                        has_text = any("text" in str(m) for m in models)
                        if not has_text:
                            errors.append("Missing required text model")

            # Validate agents
            if "agents" in config:
                if not config["agents"]:
                    errors.append("No agents configured")
                for i, agent in enumerate(config["agents"]):
                    if isinstance(agent, dict):
                        if "id" not in agent and "path" not in agent:
                            errors.append(f"Agent {i} missing 'id' or 'path'")

            # Check secrets if referenced
            if "secrets_file" in config:
                secrets_path = formation_path.parent / config["secrets_file"]
                if not secrets_path.exists():
                    errors.append(f"Secrets file not found: {secrets_path}")

            return len(errors) == 0, errors

        except Exception as e:
            return False, [f"Failed to parse formation: {e}"]

    @staticmethod
    def validate_services(required_services: List[Tuple[str, int]]) -> Tuple[bool, List[str]]:
        """Verify all required services are accessible."""
        errors = []

        for service_name, port in required_services:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result != 0:
                    errors.append(f"{service_name} not available on port {port}")
            except Exception as e:
                errors.append(f"{service_name} check failed: {e}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_credentials(formation_config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if required credentials are available."""
        errors = []

        # Check for API keys in secrets
        if "secrets" in formation_config:
            required_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
            for key in required_keys:
                if key not in formation_config["secrets"]:
                    errors.append(f"Missing credential: {key}")

        return len(errors) == 0, errors

# Pre-test validation fixture
@pytest.fixture
def validate_before_test(formation_path, required_services=None):
    """Validate formation and services before running test."""
    validator = FormationValidator()

    # Validate formation
    valid, errors = validator.validate_formation(formation_path)
    if not valid:
        pytest.skip(f"Invalid formation: {', '.join(errors)}")

    # Validate services if specified
    if required_services:
        valid, errors = validator.validate_services(required_services)
        if not valid:
            pytest.skip(f"Required services not available: {', '.join(errors)}")

    yield  # Run test

    # Post-test validation could go here
```

#### Teardown and Cleanup
```bash
#!/bin/bash
# scripts/stop_test_services.sh
echo "Stopping test services..."

# Stop background processes
[ -f /tmp/webhook_server.pid ] && kill $(cat /tmp/webhook_server.pid)
[ -f /tmp/a2a_registry.pid ] && kill $(cat /tmp/a2a_registry.pid)
[ -f /tmp/faissx_noauth.pid ] && kill $(cat /tmp/faissx_noauth.pid)
[ -f /tmp/faissx_auth.pid ] && kill $(cat /tmp/faissx_auth.pid)

# Stop Docker containers
docker stop postgres-test && docker rm postgres-test

# Or if using docker-compose:
# docker-compose -f tests/e2e/docker-compose.yml down

# Clean up temp files
rm -f /tmp/*.pid

echo "All test services stopped."
```

#### Performance Benchmarking
```python
# tests/e2e/common/benchmark.py
from typing import Dict, Optional
from datetime import datetime
import json
from pathlib import Path

class PerformanceBenchmark:
    """Track and enforce performance baselines for tests."""

    # Baseline performance expectations (in seconds)
    BASELINE_TIMES: Dict[str, float] = {
        # Quick tests
        "simple_chat": 5.0,
        "greeting": 3.0,
        "memory_recall": 8.0,

        # Medium tests
        "mcp_tool_use": 20.0,
        "file_generation": 25.0,
        "knowledge_query": 15.0,

        # Long tests
        "workflow_decomposition": 30.0,
        "multi_agent": 45.0,
        "video_processing": 120.0,
    }

    REGRESSION_THRESHOLD = 1.2  # 20% slower is considered regression

    @classmethod
    def check_regression(cls, test_name: str, actual_time: float) -> Tuple[bool, str]:
        """Check if test has regressed from baseline."""
        # Extract test type from full test name
        test_type = cls._extract_test_type(test_name)

        if test_type not in cls.BASELINE_TIMES:
            return True, f"No baseline for {test_type}"

        baseline = cls.BASELINE_TIMES[test_type]
        threshold = baseline * cls.REGRESSION_THRESHOLD

        if actual_time > threshold:
            return False, f"Performance regression: {actual_time:.1f}s > {threshold:.1f}s (baseline: {baseline:.1f}s)"

        return True, f"Performance OK: {actual_time:.1f}s <= {threshold:.1f}s"

    @classmethod
    def update_baseline(cls, test_name: str, new_time: float, force: bool = False):
        """Update baseline if significantly improved or forced."""
        test_type = cls._extract_test_type(test_name)
        current = cls.BASELINE_TIMES.get(test_type)

        if force or not current or new_time < current * 0.8:  # 20% improvement
            cls.BASELINE_TIMES[test_type] = new_time
            cls._persist_baselines()

    @staticmethod
    def _extract_test_type(test_name: str) -> str:
        """Extract generic test type from specific test name."""
        # test_1a1_simple_chat -> simple_chat
        parts = test_name.split('_')
        if len(parts) > 2:
            return '_'.join(parts[2:])
        return test_name

    @classmethod
    def _persist_baselines(cls):
        """Save baselines to file."""
        baseline_file = Path("tests/e2e/common/baselines.json")
        baseline_file.write_text(json.dumps(cls.BASELINE_TIMES, indent=2))

    @classmethod
    def load_baselines(cls):
        """Load baselines from file."""
        baseline_file = Path("tests/e2e/common/baselines.json")
        if baseline_file.exists():
            cls.BASELINE_TIMES = json.loads(baseline_file.read_text())
```

#### Environment-Specific Configuration
```python
# tests/e2e/common/env.py
import os
from typing import Dict, Any, Optional
from pathlib import Path

class TestEnvironment:
    """Handle environment-specific test configuration."""

    @property
    def is_ci(self) -> bool:
        """Check if running in CI/CD environment."""
        return os.getenv("CI", "").lower() in ["true", "1", "yes"]

    @property
    def is_docker(self) -> bool:
        """Check if running in Docker container."""
        return (
            os.path.exists("/.dockerenv") or
            os.getenv("DOCKER_CONTAINER", "").lower() in ["true", "1", "yes"]
        )

    @property
    def is_local(self) -> bool:
        """Check if running locally."""
        return not self.is_ci and not self.is_docker

    def get_service_url(self, service: str) -> str:
        """Get service URL based on environment."""
        if self.is_docker:
            # Docker service names
            service_map = {
                "postgres": "postgres:5432",
                "faissx": "faissx:45678",
                "webhook": "webhook:8080",
                "a2a": "a2a-registry:8090",
            }
        elif self.is_ci:
            # CI service URLs (GitHub Actions)
            service_map = {
                "postgres": "localhost:5432",
                "faissx": "localhost:45678",
                "webhook": "localhost:8080",
                "a2a": "localhost:8090",
            }
        else:
            # Local development
            service_map = {
                "postgres": "localhost:5432",
                "faissx": "localhost:45678",
                "webhook": "localhost:8080",
                "a2a": "localhost:8090",
            }

        return service_map.get(service, f"localhost:{self._default_port(service)}")

    def get_timeout_multiplier(self) -> float:
        """Get timeout multiplier based on environment."""
        if self.is_ci:
            return 2.0  # CI runners can be slow
        elif self.is_docker:
            return 1.5  # Docker adds some overhead
        else:
            return 1.0  # Local is baseline

    def get_parallel_workers(self) -> int:
        """Get number of parallel workers based on environment."""
        if self.is_ci:
            # GitHub Actions provides 2 cores
            return 2
        elif self.is_docker:
            # Docker might have resource limits
            return 4
        else:
            # Local can use more
            import multiprocessing
            return min(8, multiprocessing.cpu_count())

    @staticmethod
    def _default_port(service: str) -> int:
        """Get default port for service."""
        ports = {
            "postgres": 5432,
            "faissx": 45678,
            "webhook": 8080,
            "a2a": 8090,
        }
        return ports.get(service, 8000)

    def get_test_config(self) -> Dict[str, Any]:
        """Get complete test configuration for current environment."""
        return {
            "environment": "ci" if self.is_ci else "docker" if self.is_docker else "local",
            "parallel_workers": self.get_parallel_workers(),
            "timeout_multiplier": self.get_timeout_multiplier(),
            "services": {
                "postgres": self.get_service_url("postgres"),
                "faissx": self.get_service_url("faissx"),
                "webhook": self.get_service_url("webhook"),
                "a2a": self.get_service_url("a2a"),
            },
            "features": {
                "verbose_logging": self.is_local,
                "capture_screenshots": self.is_local,
                "performance_tracking": True,
                "cleanup_validation": not self.is_ci,  # Skip in CI for speed
            }
        }

# Global instance
test_env = TestEnvironment()
```

#### Cleanup Verification
```python
# tests/e2e/common/cleanup.py
import psutil
import os
from typing import Dict, Any, List
from pathlib import Path

class CleanupVerifier:
    """Verify proper cleanup after tests."""

    @staticmethod
    def capture_system_state() -> Dict[str, Any]:
        """Capture current system state for comparison."""
        return {
            "processes": set(p.pid for p in psutil.process_iter()),
            "open_files": CleanupVerifier._get_open_files(),
            "memory_usage": psutil.virtual_memory().used,
            "temp_files": CleanupVerifier._count_temp_files(),
            "db_connections": CleanupVerifier._count_db_connections(),
        }

    @staticmethod
    def verify_cleanup(initial_state: Dict[str, Any],
                       final_state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verify system was properly cleaned up."""
        issues = []

        # Check for leaked processes
        leaked_pids = final_state["processes"] - initial_state["processes"]
        if leaked_pids:
            issues.append(f"Leaked processes: {leaked_pids}")

        # Check for unclosed files
        leaked_files = final_state["open_files"] - initial_state["open_files"]
        if leaked_files:
            issues.append(f"Unclosed files: {leaked_files}")

        # Check for memory leaks (allow 10MB variance)
        memory_diff = final_state["memory_usage"] - initial_state["memory_usage"]
        if memory_diff > 10 * 1024 * 1024:  # 10MB
            issues.append(f"Memory leak: {memory_diff / 1024 / 1024:.1f}MB")

        # Check for temp file accumulation
        temp_diff = final_state["temp_files"] - initial_state["temp_files"]
        if temp_diff > 5:
            issues.append(f"Temp files not cleaned: {temp_diff} files")

        # Check for DB connection leaks
        conn_diff = final_state["db_connections"] - initial_state["db_connections"]
        if conn_diff > 0:
            issues.append(f"Database connections not closed: {conn_diff}")

        return len(issues) == 0, issues

    @staticmethod
    def _get_open_files() -> set:
        """Get set of open files."""
        try:
            current_process = psutil.Process()
            return {f.path for f in current_process.open_files()}
        except:
            return set()

    @staticmethod
    def _count_temp_files() -> int:
        """Count files in temp directory."""
        temp_dir = Path("/tmp") if os.name != 'nt' else Path(os.environ['TEMP'])
        try:
            return len(list(temp_dir.glob("muxi_test_*")))
        except:
            return 0

    @staticmethod
    def _count_db_connections() -> int:
        """Count active database connections."""
        try:
            # This would need actual DB connection counting logic
            # Placeholder for now
            return 0
        except:
            return 0

# Pytest fixture for cleanup verification
@pytest.fixture
def verify_cleanup():
    """Fixture to verify cleanup after test."""
    verifier = CleanupVerifier()
    initial_state = verifier.capture_system_state()

    yield  # Run test

    final_state = verifier.capture_system_state()
    clean, issues = verifier.verify_cleanup(initial_state, final_state)

    if not clean:
        # Log issues but don't fail test (warning only)
        for issue in issues:
            print(f"  ⚠️ Cleanup issue: {issue}")
```

#### Test Categorization and Markers
```python
# tests/e2e/common/markers.py
"""
Test categorization markers for different test types and requirements.
"""

import pytest

# Test priority markers
smoke = pytest.mark.smoke  # Quick tests for PR validation (~5 min)
regression = pytest.mark.regression  # Full regression suite (~45 min)
critical = pytest.mark.critical  # Must-pass tests
extended = pytest.mark.extended  # Extended tests (optional)

# Test speed markers
fast = pytest.mark.fast  # <5 seconds
slow = pytest.mark.slow  # >30 seconds
very_slow = pytest.mark.very_slow  # >2 minutes

# Dependency markers
requires_postgres = pytest.mark.requires_postgres
requires_faissx = pytest.mark.requires_faissx
requires_webhook = pytest.mark.requires_webhook
requires_a2a = pytest.mark.requires_a2a
requires_gpu = pytest.mark.requires_gpu  # For multimodal tests

# Parallelization markers
serial = pytest.mark.serial  # Must run sequentially
parallel_safe = pytest.mark.parallel_safe  # Safe to run in parallel
rate_limited = pytest.mark.rate_limited  # Has API rate limits

# Feature coverage markers
def covers(*features):
    """Mark test as covering specific features."""
    return pytest.mark.covers(features=features)

# Usage examples:
"""
@smoke
@fast
@parallel_safe
@covers("chat", "greeting")
def test_simple_greeting():
    pass

@regression
@slow
@requires_postgres
@serial
def test_database_persistence():
    pass

@critical
@covers("scheduling", "cron")
def test_critical_scheduling():
    pass
"""
```

#### MCP Server State Management
```python
# tests/e2e/common/mcp_state.py
import asyncio
from typing import List, Dict, Any

class MCPStateManager:
    """Manage MCP server state between tests."""

    def __init__(self):
        self.mcp_servers = {}
        self.initial_states = {}

    async def register_server(self, server_id: str, reset_func: callable):
        """Register an MCP server with its reset function."""
        self.mcp_servers[server_id] = reset_func

    async def capture_state(self, server_id: str) -> Dict[str, Any]:
        """Capture current state of an MCP server."""
        # This would need actual MCP state capture logic
        # Placeholder implementation
        return {"server_id": server_id, "state": "captured"}

    async def reset_server(self, server_id: str):
        """Reset an MCP server to clean state."""
        if server_id in self.mcp_servers:
            reset_func = self.mcp_servers[server_id]
            await reset_func()

    async def reset_all_servers(self):
        """Reset all registered MCP servers."""
        tasks = [self.reset_server(sid) for sid in self.mcp_servers]
        await asyncio.gather(*tasks)

# Pytest fixture for MCP state management
@pytest.fixture
async def clean_mcp_state():
    """Reset MCP server state between tests."""
    manager = MCPStateManager()

    # Register known MCP servers
    await manager.register_server("filesystem", reset_filesystem_mcp)
    await manager.register_server("github", reset_github_mcp)
    await manager.register_server("linear", reset_linear_mcp)

    # Capture initial state
    for server_id in manager.mcp_servers:
        manager.initial_states[server_id] = await manager.capture_state(server_id)

    yield manager  # Run test

    # Reset to initial state
    await manager.reset_all_servers()

async def reset_filesystem_mcp():
    """Reset filesystem MCP to clean state."""
    # Remove any test files created
    import shutil
    test_dir = Path("/tmp/mcp_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

async def reset_github_mcp():
    """Reset GitHub MCP state."""
    # Close any open PRs, delete test branches, etc.
    pass

async def reset_linear_mcp():
    """Reset Linear MCP state."""
    # Archive test issues, clear test projects, etc.
    pass
```

#### Test Debugging Helpers
```python
# tests/e2e/common/debug.py
import json
import pickle
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class TestDebugger:
    """Debugging utilities for test failures."""

    def __init__(self, debug_dir: Path = Path("tests/debug")):
        self.debug_dir = debug_dir
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    def capture_formation_state(self, formation, test_name: str):
        """Dump full formation state for debugging."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        state_file = self.debug_dir / f"{test_name}_{timestamp}_state.json"

        state = {
            "config": formation.config if hasattr(formation, 'config') else {},
            "agents": self._get_agent_states(formation),
            "memory": self._get_memory_state(formation),
            "services": self._get_service_states(formation),
            "timestamp": timestamp,
        }

        state_file.write_text(json.dumps(state, indent=2, default=str))
        print(f"  📸 Formation state saved to {state_file}")

    def capture_conversation(self, transcript: List[Tuple[str, str]],
                           test_name: str, error: Optional[Exception] = None):
        """Save conversation transcript for replay."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcript_file = self.debug_dir / f"{test_name}_{timestamp}_transcript.json"

        data = {
            "test_name": test_name,
            "timestamp": timestamp,
            "transcript": transcript,
            "error": str(error) if error else None,
        }

        transcript_file.write_text(json.dumps(data, indent=2))
        print(f"  📝 Transcript saved to {transcript_file}")

    def replay_conversation(self, transcript_file: Path):
        """Replay a saved conversation for debugging."""
        data = json.loads(transcript_file.read_text())
        print(f"\n🔄 Replaying conversation from {data['test_name']}")
        print(f"   Recorded at: {data['timestamp']}")

        for i, (user, assistant) in enumerate(data['transcript'], 1):
            print(f"\n[Exchange {i}]")
            print(f"User: {user}")
            print(f"Assistant: {assistant[:200]}...")

        if data['error']:
            print(f"\n❌ Original error: {data['error']}")

    def enable_verbose_mode(self):
        """Enable verbose logging for debugging."""
        import logging
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("muxi").setLevel(logging.DEBUG)

    def breakpoint_on_error(self, condition: callable = None):
        """Set conditional breakpoint for debugging."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if condition is None or condition(e):
                        import pdb
                        pdb.set_trace()
                    raise
            return wrapper
        return decorator

    def _get_agent_states(self, formation) -> Dict:
        """Extract agent states from formation."""
        # Placeholder - would need actual agent state extraction
        return {}

    def _get_memory_state(self, formation) -> Dict:
        """Extract memory state from formation."""
        # Placeholder - would need actual memory state extraction
        return {}

    def _get_service_states(self, formation) -> Dict:
        """Extract service states from formation."""
        # Placeholder - would need actual service state extraction
        return {}

# Global debugger instance
debugger = TestDebugger()

# Debug mode detection
DEBUG_MODE = os.getenv("DEBUG_TESTS", "").lower() in ["true", "1", "yes"]

if DEBUG_MODE:
    debugger.enable_verbose_mode()
```

#### Test Dependency Management
```python
# tests/e2e/common/dependencies.py
import pytest
from typing import Dict, Any

class TestDependencyManager:
    """Manage dependencies between tests."""

    # Shared state between dependent tests
    shared_state: Dict[str, Any] = {}

    @classmethod
    def set_state(cls, key: str, value: Any):
        """Store state for dependent tests."""
        cls.shared_state[key] = value

    @classmethod
    def get_state(cls, key: str, default=None) -> Any:
        """Retrieve state from previous tests."""
        return cls.shared_state.get(key, default)

    @classmethod
    def clear_state(cls):
        """Clear all shared state."""
        cls.shared_state.clear()

# Example usage:
"""
@pytest.mark.dependency()
def test_create_schedule():
    # Create a schedule
    schedule_id = create_test_schedule()
    TestDependencyManager.set_state("schedule_id", schedule_id)
    assert schedule_id is not None

@pytest.mark.dependency(depends=["test_create_schedule"])
def test_verify_schedule():
    # Verify the schedule was created
    schedule_id = TestDependencyManager.get_state("schedule_id")
    assert schedule_id is not None
    verify_schedule_exists(schedule_id)

@pytest.mark.dependency(depends=["test_verify_schedule"])
def test_delete_schedule():
    # Clean up the schedule
    schedule_id = TestDependencyManager.get_state("schedule_id")
    delete_schedule(schedule_id)
    TestDependencyManager.clear_state()
"""
```

## Parallelization Strategy

### Tests That Can Run in Parallel (After Standardization)
**~185 tests (86% of total)** can run in parallel once isolated:

#### Fully Parallelizable Areas
- **Area 1: Foundation** (10 tests) - Independent formation loading
- **Area 3: Multimodal** (38 tests) - Separate file processing
- **Area 5: Artifacts** (8 tests) - Independent file generation
- **Area 6: Knowledge** (19 tests) - Isolated vector stores
- **Area 7: Orchestration** (12 tests) - Separate agent pools
- **Area 8: Clarification** (49 tests) - Independent conversations
- **Area 10: Streaming** (6 tests) - Independent streams
- **Area 11: Formatting** (1 test) - Simple formatting

#### Partially Parallelizable Areas
- **Area 2: Memory** (15/25 tests parallel)
  - Parallel: Tests using buffer memory or SQLite
  - Sequential: Tests sharing PostgreSQL instance
- **Area 4: MCP** (18/24 tests parallel)
  - Parallel: Tests using filesystem, system MCP
  - Rate-limited: GitHub, Linear, web-search APIs
- **Area 9: Async** (9/11 tests parallel)
  - Parallel: Most async/sync mode tests
  - Sequential: Webhook timeout tests

### Tests That Must Run Sequentially
**~30 tests (14% of total)** require sequential execution:

#### Area 12: Scheduling (ALL 12 tests SEQUENTIAL)
```python
# Must run with pytest-xdist disabled for this area
pytest tests/e2e/12_scheduling -n 0  # Force sequential
```
**Reasons**:
- Uses system scheduler (APScheduler)
- Manipulates system time for testing
- Creates cron jobs that persist
- Verifies time-based executions
- Tests like `test_12b3_wait_for_execution.py` sleep for job execution

#### Specific Sequential Tests from Other Areas
1. **Memory Database Tests** (10 tests)
   - `test_2b1_sqlite_persistence.py` - Shared SQLite
   - `test_2l1_database_optimization.py` - PostgreSQL performance
   - Tests using shared PostgreSQL connections

2. **MCP Rate-Limited Tests** (6 tests)
   - Tests calling GitHub API
   - Tests calling Linear API
   - Web-search API tests
   - Need 1-2 second delays between calls

3. **Async Webhook Tests** (2 tests)
   - `test_9c2_timeout_handling.py` - 30+ second timeout
   - `test_9c1_webhook_failure.py` - Network failure simulation

### Parallel Execution Configuration

#### Recommended pytest-xdist Setup
```bash
# Run most tests in parallel (8 workers)
pytest tests/e2e -n 8 \
  --ignore=tests/e2e/12_scheduling \
  --ignore=tests/e2e/2_memory/test_2b1_sqlite_persistence.py \
  --ignore=tests/e2e/2_memory/test_2l1_database_optimization.py

# Run scheduling tests sequentially
pytest tests/e2e/12_scheduling -n 0

# Run rate-limited tests with delays
pytest tests/e2e/4_mcp -n 2 --dist loadgroup
```

#### Test Markers for Control
```python
# Add to tests that need sequential execution
@pytest.mark.serial
async def test_scheduling_job():
    pass

# Add to tests that can be grouped
@pytest.mark.xdist_group("database")
async def test_postgres_operation():
    pass

# Add to tests with external API calls
@pytest.mark.rate_limited
async def test_github_api():
    pass
```

### Resource Isolation Requirements

#### For Parallel Execution Success
1. **Database Isolation**
   - Each test gets unique database/schema
   - Use `test_<id>_` prefix for tables
   - Connection pooling with limits

2. **File System Isolation**
   - Unique temp directories per test
   - No shared file paths
   - Cleanup in fixtures

3. **Port Allocation**
   - Dynamic port assignment for webhooks
   - No hardcoded ports
   - Port range reservation (8000-9000)

4. **Memory Isolation**
   - Separate vector store instances
   - Independent buffer memory
   - No shared global state

### Expected Performance Gains

| Execution Mode | Time Estimate | Tests |
|----------------|---------------|-------|
| Sequential (current) | ~45 minutes | 215 |
| Parallel (8 workers) | ~8 minutes | 185 |
| Sequential (required) | ~10 minutes | 30 |
| **Total with parallel** | **~18 minutes** | **215** |

**2.5x speed improvement** expected with proper parallelization.

### CI/CD Pipeline Configuration

```yaml
# .github/workflows/test.yml
jobs:
  test-parallel:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        area: [1_foundation, 3_multimodal, 5_artifacts, 6_knowledge, 7_orchestration, 8_clarification, 10_streaming, 11_formatting]
    steps:
      - run: pytest tests/e2e/${{ matrix.area }} -n 4

  test-sequential:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/e2e/12_scheduling -n 0

  test-limited-parallel:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/e2e/2_memory -n 2
      - run: pytest tests/e2e/4_mcp -n 2 --dist loadgroup
      - run: pytest tests/e2e/9_async -n 2
```

## Critical Lessons Learned (January 2025)

### 1. Model Performance Issues
- **Discovery**: `gpt-5-nano` exists but is extremely slow (30+ second responses)
- **Impact**: Tests timeout waiting for model responses
- **Solution**: Replace all instances with `gpt-4o-mini` (33 files affected)
- **Lesson**: Always verify model response times for test environments

### 2. Async/Sync Pattern Complexity
- **Issue**: Tests mixing `asyncio.run()` with async methods cause event loop conflicts
- **Pattern That Works**:
  ```python
  async def test_method(self):
      # All test logic here with await
      formation = await self.setup_formation()
      response = await overlord.chat()

  def run_test(self):
      return asyncio.run(self.test_method())
  ```
- **Lesson**: Single entry point for event loop, async all the way down

### 3. Test Framework vs Direct Execution
- **Finding**: Formations load fine directly but timeout in test framework
- **Cause**: BaseE2ETest adds complexity with thread pools and multiple async contexts
- **Workaround**: Simplify test execution patterns, avoid nested async contexts

### 4. Invisible Character Detection
- **Discovery**: LLM responses contain invisible Unicode characters
- **Solution**: Clean all responses in `_apply_persona()` method
- **Implementation**: `text_cleaner.py` utility removes zero-width spaces while preserving emojis

### 5. Agent Planning Simplicity
- **Issue**: Agents using unnecessary tools for simple requests
- **Solution**: SIMPLICITY FIRST RULE in planning prompt
- **Result**: Direct responses for conversational requests without tool usage

## Implementation Plan

### Phase 0: Preserve Legacy Tests (Day 1) - ✅ COMPLETED
**DO NOT MODIFY ANY EXISTING TESTS UNTIL STANDARDIZATION IS PROVEN**

```bash
# Step 1: Create complete backup of existing tests ✅
cp -r tests/e2e tests/e2e_legacy

# Step 2: Create new standardized structure alongside legacy ✅
mkdir -p tests/e2e_new/common/formations/base
mkdir -p tests/e2e_new/common/formations/agents

# Step 3: Implement common module first ✅
# tests/e2e_new/common/__init__.py
# tests/e2e_new/common/base.py
# tests/e2e_new/common/fixtures.py

# Step 4: Migrate ONE test area as proof of concept 🚧 IN PROGRESS
# Start with Area 1_foundation (smallest, simplest)
# Run both legacy and new tests to ensure parity

# Step 5: Only after validation, gradually migrate other areas ⏳ PENDING
```

### Progress Status (As of 2025-09-19)

#### ✅ Completed Tasks:
1. **Created e2e_legacy backup** - Full backup of existing tests preserved
2. **Created e2e_new directory structure** - New standardized structure in place
3. **Implemented common module base classes**:
   - `BaseE2ETest` - Core test class with formation management
   - `FormationManager` - Handles three formation patterns
   - `TestOutputFormatter` - Standardized CI/CD output
   - `TestTimeouts` - Dynamic timeout management
   - `TestRetry` - Retry logic with circuit breaker
   - `TestResultTracker` - Performance tracking
   - `TestDataGenerator` - Test data fixtures
   - `TestEnvironment` - Environment detection
4. **Created base formation templates**:
   - `standard/formation.yaml` - For 60% of tests
   - `minimal/formation.yaml` - For 20% of tests
   - `complex/formation.yaml` - For 10% of tests
   - Symlinks to `tests/assets/secrets.enc` and `.key` ✅
5. **Fixed all linting issues** - Code passes flake8 with project standards

#### 🚧 In Progress:
- **Migrate Area 1 (foundation) as proof of concept** - Next immediate task

#### ⏳ Pending Tasks:
- **Validate both test suites produce identical results**
- **Migrate remaining areas (2-12)**
- **CI/CD integration**
- **Performance benchmarking**

#### Parallel Testing Strategy
```python
# Run both test suites in parallel during migration
pytest tests/e2e_legacy/1_foundation  # Original tests
pytest tests/e2e_new/1_foundation      # Standardized tests

# Compare results to ensure no regressions
diff tests/logs/legacy_results.json tests/logs/new_results.json
```

#### Rollback Plan
```bash
# If standardization fails at any point
rm -rf tests/e2e
mv tests/e2e_legacy tests/e2e
# Back to original state with zero risk
```

### Phase 1: Foundation (Areas 1-3) - Week 1
Priority: HIGH - Core functionality validation

#### Area 1: Foundation (10 tests)
- [ ] Create 10 individual formations from shared formation-basic
- [ ] Convert test structure to use pytest fixtures
- [ ] Remove MuxiOverlord usage if present
- [ ] Add proper cleanup in all tests

#### Area 2: Memory (25 tests)
- [ ] Split formation-memory into 25 individual formations
- [ ] Standardize database connection handling
- [ ] Add memory cleanup fixtures
- [ ] Ensure buffer memory isolation

#### Area 3: Multimodal (38 tests)
- [ ] Create 38 individual formations
- [ ] Standardize file handling patterns
- [ ] Add cleanup for generated files
- [ ] Ensure model loading consistency

### Phase 2: Services (Areas 4-6) - Week 2
Priority: HIGH - External service integration

#### Area 4: MCP (24 tests)
- [ ] Create 24 individual formations
- [ ] Standardize MCP server mocking/setup
- [ ] Handle authentication consistently
- [ ] Add server cleanup procedures

#### Area 5: Artifacts (8 tests)
- [ ] Convert MuxiOverlord to Formation pattern
- [ ] Create 8 individual formations
- [ ] Standardize file generation paths
- [ ] Add artifact cleanup

#### Area 6: Knowledge (19 tests)
- [ ] Create 19 individual formations
- [ ] Standardize knowledge base setup
- [ ] Ensure vector store isolation
- [ ] Add knowledge cleanup

### Phase 3: Advanced Features (Areas 7-9) - Week 3
Priority: MEDIUM - Complex orchestration

#### Area 7: Orchestration (12 tests)
- [ ] Consolidate 5 formation variants
- [ ] Create 12 individual formations
- [ ] Standardize A2A communication setup
- [ ] Add workflow cleanup

#### Area 8: Clarification (49 tests)
- [ ] Create 49 individual formations (largest area)
- [ ] Remove dynamic credential injection
- [ ] Standardize clarification flow testing
- [ ] Add state cleanup

#### Area 9: Async (11 tests)
- [ ] Create 11 individual formations
- [ ] Remove webhook URL overrides
- [ ] Standardize async/sync mode testing
- [ ] Add webhook cleanup

### Phase 4: Recent Features (Areas 10-12) - Week 4
Priority: LOW - Already using newer patterns

#### Area 10: Streaming (6 tests)
- [ ] Create 6 individual formations
- [ ] Standardize stream handling
- [ ] Add stream cleanup

#### Area 11: Formatting (1 test)
- [ ] Create individual formation
- [ ] Ensure format consistency

#### Area 12: Scheduling (12 tests)
- [ ] Create 12 individual formations from shared
- [ ] Standardize scheduler testing
- [ ] Add job cleanup

## Migration Strategy - Zero Risk Approach

### Safe Migration Process
```bash
# Directory structure during migration
tests/
├── e2e/                    # Current tests (untouched)
├── e2e_legacy/             # Backup copy (read-only)
└── e2e_new/                # New standardized tests

# Final cutover only after full validation
mv tests/e2e tests/e2e_old
mv tests/e2e_new tests/e2e
rm -rf tests/e2e_old        # Only after 1 week of stability
```

### Validation Checklist per Area
- [ ] All tests from legacy pass in new structure
- [ ] Execution time is same or better
- [ ] Log output captures same information
- [ ] Parallel execution works without conflicts
- [ ] No hardcoded paths or environment dependencies

### Migration Script
```python
#!/usr/bin/env python3
# scripts/migrate_e2e_tests.py
"""Safely migrate e2e tests to standardized structure."""

import shutil
from pathlib import Path

class E2EMigrator:
    def __init__(self):
        self.legacy_path = Path("tests/e2e")
        self.backup_path = Path("tests/e2e_legacy")
        self.new_path = Path("tests/e2e_new")

    def create_backup(self):
        """Step 1: Create read-only backup."""
        if self.backup_path.exists():
            print(f"Backup already exists at {self.backup_path}")
            return False

        shutil.copytree(self.legacy_path, self.backup_path)
        # Make backup read-only
        for file in self.backup_path.rglob("*"):
            file.chmod(0o444)
        print(f"✓ Created read-only backup at {self.backup_path}")
        return True

    def setup_new_structure(self):
        """Step 2: Create standardized structure."""
        # Create common module
        common = self.new_path / "common"
        common.mkdir(parents=True, exist_ok=True)

        # Copy base formations
        (common / "formations" / "base").mkdir(parents=True)
        (common / "formations" / "agents").mkdir(parents=True)

        print(f"✓ Created new structure at {self.new_path}")

    def migrate_area(self, area: str):
        """Migrate single test area."""
        print(f"\nMigrating area: {area}")

        # Copy tests to new location
        old_area = self.legacy_path / area
        new_area = self.new_path / area

        if not old_area.exists():
            print(f"  ⚠️ Area {area} not found")
            return False

        # Create new area directory
        new_area.mkdir(parents=True, exist_ok=True)

        # Migrate test files (but update imports)
        for test_file in old_area.glob("test_*.py"):
            self._migrate_test_file(test_file, new_area)

        return True

    def _migrate_test_file(self, old_file: Path, new_dir: Path):
        """Migrate single test file with updated imports."""
        content = old_file.read_text()

        # Update imports to use common module
        content = content.replace(
            "from muxi.formation import Formation",
            "from tests.e2e_new.common import BaseE2ETest"
        )

        # Write to new location
        new_file = new_dir / old_file.name
        new_file.write_text(content)
        print(f"  ✓ Migrated {old_file.name}")

    def validate_migration(self, area: str):
        """Run both test suites and compare results."""
        import subprocess
        import json

        # Run legacy tests
        legacy_result = subprocess.run(
            ["pytest", f"tests/e2e_legacy/{area}", "--json-report"],
            capture_output=True
        )

        # Run new tests
        new_result = subprocess.run(
            ["pytest", f"tests/e2e_new/{area}", "--json-report"],
            capture_output=True
        )

        # Compare results
        if legacy_result.returncode != new_result.returncode:
            print(f"  ❌ Different exit codes: {legacy_result.returncode} vs {new_result.returncode}")
            return False

        print(f"  ✓ Migration validated for {area}")
        return True

if __name__ == "__main__":
    migrator = E2EMigrator()

    # Step 1: Create backup (only once)
    if migrator.create_backup():
        print("\n⚠️  IMPORTANT: Do not modify tests/e2e_legacy!")
        print("This is your rollback safety net.\n")

    # Step 2: Setup new structure
    migrator.setup_new_structure()

    # Step 3: Migrate area by area
    areas = ["1_foundation", "2_memory", "3_multimodal", ...]
    for area in areas:
        if migrator.migrate_area(area):
            if not migrator.validate_migration(area):
                print(f"\n❌ Validation failed for {area}")
                print("Fix issues before continuing")
                break
```

## Validation Criteria

### Regression Testing
1. All tests from Areas 1-8 must pass
2. No degradation in test execution time
3. Memory usage remains stable
4. No resource leaks

### CI/CD Compatibility
1. Tests run successfully in GitHub Actions
2. Parallel execution works without conflicts
3. Clear test reports generated
4. Failures are easily debuggable

### Test Quality Metrics
- **Coverage**: All features have tests
- **Isolation**: No test affects another
- **Speed**: Tests complete in < 5 min per area
- **Reliability**: No flaky tests

## Risk Mitigation

### Risks and Mitigations

1. **Risk**: Breaking existing tests during migration
   - **Mitigation**: Migrate one area at a time, verify each

2. **Risk**: Increased test execution time
   - **Mitigation**: Enable parallel execution, optimize formations

3. **Risk**: Storage overhead from many formations
   - **Mitigation**: Use symbolic links for shared agents

4. **Risk**: Complex tests become harder to maintain
   - **Mitigation**: Create test helpers and utilities

## Success Metrics

1. **All 215 tests passing**: 100% success rate
2. **Parallel execution**: 4x speed improvement
3. **Zero flaky tests**: Consistent results
4. **CI/CD integration**: Automated regression testing
5. **Developer satisfaction**: Easier debugging and maintenance

## Timeline

- **Week 1**: Areas 1-3 (73 tests) - Foundation
- **Week 2**: Areas 4-6 (51 tests) - Services
- **Week 3**: Areas 7-9 (72 tests) - Advanced
- **Week 4**: Areas 10-12 (19 tests) - Recent
- **Week 5**: CI/CD integration and documentation

## Next Steps

1. **Immediate Actions**:
   - Create formation generator script
   - Set up test migration tracking
   - Begin with Area 1 as pilot

2. **Communication**:
   - Notify team of standardization effort
   - Document new test patterns
   - Create migration guide

3. **Tooling**:
   - Update test runner script
   - Create formation validation tool
   - Set up test metrics dashboard

## Appendix: Current Formation Sharing

| Area | Tests | Formations | Sharing Ratio | Priority |
|------|-------|------------|---------------|----------|
| 12_scheduling | 12 | 1 | 12:1 | HIGH |
| 8_clarification | 49 | 2-3 | ~20:1 | HIGH |
| 2_memory | 25 | 1 | 25:1 | HIGH |
| 7_orchestration | 12 | 5 | 2.4:1 | MEDIUM |
| 3_multimodal | 38 | 1 | 38:1 | HIGH |
| 9_async | 11 | 1 | 11:1 | MEDIUM |
| Other areas | ~78 | ~6 | ~13:1 | MEDIUM |

## Benefits of Shared Formation Approach

### Storage & Maintenance Savings
- **Before**: 215 separate formation directories = ~5MB duplicated configs
- **After**: 3 base templates + 45 specialized = ~0.8MB total
- **Reduction**: 84% less storage, 90% fewer files to maintain

### Test Organization Benefits
- **Clear categorization**: Tests grouped by modification pattern
- **Easy updates**: Change base formation, affects all related tests
- **Better documentation**: Runtime modifications show test intent
- **Reduced duplication**: Shared agents and MCP configs

### Development Velocity
- **New test creation**: Copy existing test, modify 2-3 lines
- **Debugging**: Clear separation between base config and test-specific changes
- **Review process**: Easier to spot what each test is actually testing
- **Refactoring**: Central place to update common configurations

## Migration Path

### Phase 0: Create Base Formations (Week 0.5)
1. Create 3 base formation templates
2. Create shared agent/MCP directories
3. Write formation generator utilities

### Phase 1-4: Migrate by Pattern
- **Credential tests**: Migrate together using same base
- **Memory tests**: Group by memory type modifications
- **Async tests**: Share webhook/mode configurations
- **Complex tests**: Keep specialized formations

## Common Pitfalls & Solutions (from Lessons Learned)

### Critical Testing Issues

1. **Event Loop Conflicts**
   - **Problem**: MUXI Runtime uses asyncio internally, conflicts with pytest-asyncio
   - **Solution**: Use ThreadPoolExecutor pattern (see Testing Style Guide)

2. **Missing Agent Description**
   - **Problem**: Validation fails without description field
   - **Solution**: Always include `description: "Agent purpose"` in agent configs

3. **Async Response Handling**
   - **Problem**: Responses may be async even without `use_async=True`
   - **Solution**: Always check response structure and handle both sync/async

4. **Large File Timeouts**
   - **Problem**: Video/PDF processing exceeds default timeout
   - **Solution**: Use `TestTimeouts.get_timeout()` with file size detection

5. **Memory Leaks in Long Tests**
   - **Problem**: Completed requests accumulate in memory
   - **Solution**: Leverage buffer memory TTL (48h default) for automatic cleanup

6. **Context Loss in Background Tasks**
   - **Problem**: RequestContext lost with `asyncio.create_task()`
   - **Solution**: Explicitly set context in background task

### Testing Anti-Patterns to Avoid

1. **Don't use mocks** - Always test with real services
2. **Don't hardcode timeouts** - Use dynamic timeout management
3. **Don't ignore webhook setup** - Even sync requests may trigger webhooks
4. **Don't assume sync responses** - Formation settings may force async
5. **Don't skip cleanup** - Always call `formation.stop_overlord()`

## Conclusion - Simplified & Safe

### Key Simplifications from Review

1. **Unified Common Module** (`tests/e2e/common/`)
   - Single `BaseE2ETest` class for all tests
   - `FormationManager` handles all runtime modifications
   - Shared fixtures, assertions, and utilities
   - **Result**: 90% less boilerplate code

2. **Just 3 Base Formations** (not 215)
   - `standard.yaml` - 60% of tests
   - `minimal.yaml` - 20% of tests
   - `complex.yaml` - 10% of tests
   - **Result**: 84% less maintenance overhead

3. **Zero-Risk Migration**
   - Keep `tests/e2e` completely untouched
   - Build `tests/e2e_new` in parallel
   - Validate each area before proceeding
   - One-command rollback if needed
   - **Result**: No disruption to development

4. **Simplified Logging**
   - Reuse existing `test-and-log.sh` for everything
   - Same command for local and CI/CD
   - No custom pytest plugins needed
   - **Result**: Less complexity, same functionality

### Implementation Timeline (Revised)

| Phase | Duration | Deliverable | Risk | Status |
|-------|----------|-------------|------|---------|
| **Phase 0** | 1 day | Backup + common module | Zero | ✅ COMPLETED |
| **Phase 1** | 3 days | Area 1 proof of concept | Zero | 🚧 IN PROGRESS |
| **Phase 2** | 1 week | Areas 2-6 migration | Zero | ⏳ PENDING |
| **Phase 3** | 1 week | Areas 7-12 migration | Zero | ⏳ PENDING |
| **Phase 4** | 2 days | Cutover + cleanup | Minimal | ⏳ PENDING |

**Total: ~3 weeks** (Updated estimate based on actual progress)

### Final Benefits

- **2.5x faster** test execution via parallelization
- **10x easier** to write new tests (inherit from BaseE2ETest)
- **Zero risk** migration (always have rollback)
- **79% of tests** share just 3 base formations
- **One location** for all common functionality

### Next Steps

1. ✅ ~~Copy existing `e2e` directory to `e2e_legacy` and create a fresh `e2e` directory~~
2. ✅ ~~Implement `tests/e2e_new/common/` module~~
3. 🚧 Migrate Area 1 as proof of concept (NEXT TASK)
4. ⏳ Validate both suites run identically
5. ⏳ Proceed with remaining areas

### Files Created in This Session

#### Common Module Structure (`tests/e2e_new/common/`)
- `__init__.py` - Module initialization
- `base.py` - BaseE2ETest class with formation management
- `formations.py` - FormationManager with three pattern support
- `formatter.py` - TestOutputFormatter for CI/CD
- `timeout.py` - TestTimeouts with dynamic calculation
- `retry.py` - TestRetry with circuit breaker
- `results.py` - TestResultTracker for performance tracking
- `env.py` - TestEnvironment for environment detection
- `markers.py` - Test categorization markers
- `fixtures/data.py` - TestDataGenerator for test data

#### Formation Templates (`tests/e2e_new/common/formations/base/`)
- `standard/formation.yaml` - Standard template (60% of tests)
- `minimal/formation.yaml` - Minimal template (20% of tests)
- `complex/formation.yaml` - Complex template (10% of tests)
- All templates have symlinks to `tests/assets/secrets.enc` and `.key`

### Implementation Notes

1. **Three Formation Patterns Implemented**:
   - Pattern 1: Runtime modification (56% of tests)
   - Pattern 2: Shared directory with multiple YAMLs (23% of tests)
   - Pattern 3: Completely separate formations (21% of tests)

2. **Event Loop Conflict Resolution**:
   - Used ThreadPoolExecutor pattern in BaseE2ETest
   - Avoids conflicts between MUXI's asyncio and pytest-asyncio

3. **Symlink Strategy**:
   - All formations symlink to central secrets in `tests/assets/`
   - Maintains single source of truth for credentials

4. **Linting Compliance**:
   - All code formatted with black (line length 100)
   - Passes flake8 with line length 120
   - Follows project naming conventions

Ready to begin **Area 1 migration** as proof of concept with **zero risk to existing tests**.
