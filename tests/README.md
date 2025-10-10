# MUXI Runtime Tests

This directory contains the comprehensive test suite for MUXI Runtime, validating all features through systematic, incremental testing.

## 📁 Directory Structure

```
tests/
├── assets/                  # Test data and fixtures
│   ├── formations/          # YAML formation configurations for testing
│   │   ├── formation-basic/
│   │   ├── formation-memory/
│   │   ├── formation-multi-agent/
│   │   ├── formation-file-generation/
│   │   ├── formation-complete/
│   │   └── secrets.enc      # Shared encrypted secrets
│   └── files/               # Test documents, media, and sample files
│       ├── *.pdf            # PDF test documents
│       ├── *.docx           # Word documents
│       ├── *.png/jpg        # Images for OCR/vision
│       ├── *.mp3/m4a        # Audio files
│       └── *.mp4/mov        # Video files
├── e2e/                     # End-to-end integration tests
│   ├── 1_foundation/        # Foundation layer tests
│   ├── 2_memory/            # Memory systems tests
│   ├── 3_multimodal/        # Multimodal processing tests
│   ├── 4_mcp/               # MCP integration tests
│   ├── 5_artifacts/         # Artifacts system tests
│   ├── 6_knowledge/         # Knowledge system tests
│   ├── 7_orchestration/     # Multi-agent coordination tests
│   └── 8_clarification/     # Clarification flow tests
├── unit/                    # Unit tests
│   └── api/                 # API endpoint tests
├── reports/                 # Test execution reports
│   ├── 1a.md, 1b.md...      # Area 1 test reports
│   ├── 2a.md, 2b.md...      # Area 2 test reports
│   └── ...                  # Additional test reports
├── conftest.py              # Shared pytest fixtures
└── Comprehensive_Test_Plan.md  # Master test plan document
```

**IMPORTANT:** When developing - REMEMBER TO NEVER USE PATTERN MATCHING to detect user intent, preferences, or other context. Always defer to using LLM so MUXI can stay multi-lingual.

## 🧪 Testing Philosophy

**We test against real services, not mocks.** This ensures our code works in production.

### Why Real Services?
- Mock services don't test actual integration points
- Real embeddings are crucial for vector search quality
- Authentication and security features need real validation
- Performance characteristics differ significantly from mocks

### Required Services

Before running tests, ensure these real services are available:

1. **LLM Providers**: Real OpenAI, Anthropic, or other provider API keys
2. **FAISSx Servers**: For vector search (ports 45678, 65432)
3. **PostgreSQL Database**: For multi-user tests
4. **A2A Registry Server**: For agent communication
5. **MCP Servers**: Built-in and external servers

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests
pytest

# Run specific test area
pytest e2e/tests/1_foundation/

# Run specific test file
pytest e2e/tests/1_foundation/test_1a1_basic_yaml_formation.py -v

# Run with coverage
pytest --cov=muxi --cov-report=html
```

### Test Organization by Feature Area

Tests are organized by feature areas following our comprehensive test plan:

- **Areas 1-3**: Core functionality (formation, memory, multimodal)
- **Areas 4-6**: Integration features (MCP, file generation, knowledge)
- **Areas 7-8**: Advanced features (workflow, clarification)
- **Areas 9-12**: Production features (async, streaming, resilience, observability)

Each area contains:
- `TEST_MAPPING.md` - Maps test plan requirements to actual test files
- `FINAL_SUMMARY.md` - Area's accomplishments
- `test_Xa1_*.py` - Individual test files following naming convention
- `run_areaX_tests.py` - Area-specific test runner

## 📝 Naming Convention

Test files follow a standardized naming pattern:

```
test_[area][group][number]_descriptive_name.py
```

Examples:
- `test_1a1_basic_yaml_formation.py` - Area 1, Group A, Test 1
- `test_2b1_sqlite_persistence.py` - Area 2, Group B, Test 1
- `test_3c2_video_processing.py` - Area 3, Group C, Test 2

## 🔧 Configuration

### Environment Variables

Set your API keys and service configurations:

```bash
export OPENAI_API_KEY="your-key-here"
export ANTHROPIC_API_KEY="your-key-here"
export FAISSX_TENANT_ID="your-tenant-id"
```

### Test Formations

Pre-configured formations are available in `tests/assets/formations/`:

- `formation-basic/` - Single agent with minimal memory
- `formation-memory/` - Various memory configurations
- `formation-multi-agent/` - Multiple agents for routing tests
- `formation-file-generation/` - Built-in MCP enabled
- `formation-complete/` - Comprehensive formation with all components

## 📊 Test Coverage

Current test coverage across features:

| Feature | Coverage | Status |
|---------|----------|--------|
| Formation Loading | 100% | ✅ |
| Memory Systems | 100% | ✅ |
| Multimodal Processing | 94% | ✅ |
| MCP Integration | 100% | ✅ |
| File Generation | 95.5% | ✅ |
| Knowledge System | 100% | ✅ |
| Multi-Agent Coordination | 100% | ✅ |
| Clarification Flow | 100% | ✅ |

Total: **1,400+ test combinations** across 22 feature dimensions

### Note about e2e tests

Ensure every test ends up with a summary and the correspondence between the user and the overlord.

After all the logs are printed, add:

```
========================================

### Test Result:
  🎉 SUCCESS: ...
  ✓ ...
  ✓ ...
  ✓ ...

========================================

### Chat transcript:

User: ...
System: ...
User: ...
System: ...
```


### Test Execution Pattern

**IMPORTANT**: When running tests, always use the test runner script to save context:
```bash
# Run test with automatic log redirection
./tests/run-with-log.sh e2e/tests/8_clarification/test_8a1.py

# Or with custom log name for iteration
./tests/run-with-log.sh e2e/tests/8_clarification/test_8a1.py test_8a1_v2.log
```

After running tests:
1. Use the Task tool with `test-runner-summarizer` agent to analyze the log
2. The agent will surface key issues, failures, and actionable insights
3. This approach saves significant context in the main conversation

Example workflow:
```bash
# Run test with automatic logging
./tests/run-with-log.sh e2e/tests/7_orchestration/test_sops.py

# Then use Task tool to analyze:
# "Analyze the test log at tests/logs/test_sops.log and summarize any failures or issues"
```

This pattern ensures:
- Full test output is captured for debugging
- Main conversation stays clean and focused
- Context usage is optimized
- All issues are properly surfaced
- No approval dialogs interrupt the workflow


## 🐛 Known Issues

### Large File Processing
- Video files >100MB may timeout with Google Gemini
- OpenAI Whisper has a 25MB limit for audio files

### Cross-Format Operations
- Some complex cross-format operations require optimization
- Workarounds documented in test reports

## 📚 Documentation

- [Comprehensive Test Plan](Comprehensive_Test_Plan.md) - Master testing strategy
- [Test Reports](reports/) - Detailed execution results
- [Contributing](../CONTRIBUTING.md) - How to add new tests

## 🤝 Contributing Tests

When adding new tests:

1. Follow the naming convention
2. Use real services (no mocks)
3. Add to appropriate area/group
4. Update TEST_MAPPING.md
5. Document in FINAL_SUMMARY.md
6. Use existing formations when possible

Example test structure:

```python
"""
Area X - Test Group XA: Feature Description

Tests specific functionality following the test plan.
"""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from src.muxi.formation import Formation

@pytest.mark.asyncio
async def test_xa1_feature_name():
    """Test description matching test plan."""
    formation = Formation()
    await formation.load("tests/assets/formations/formation-basic/formation.yaml")
    overlord = await formation.start_overlord()

    response = await overlord.chat(
        "Test message",
        user_id="test_user"
    )

    assert response is not None
    assert "expected" in response.lower()
```

## 📈 Success Metrics

Tests validate:
- ✅ All 22 feature dimensions in combination
- ✅ User credentials with encryption & isolation
- ✅ File generation across all major formats
- ✅ Domain knowledge with multiple agents
- ✅ Built-in MCP security validation
- ✅ SOP system with 72% code reduction
- ✅ Multiple clarification sequences
- ✅ Formation-first architecture
- ✅ Real developer API (`overlord.chat()`)

---

For questions or issues with tests, see the [main Contributing Guide](../CONTRIBUTING.md) or open an issue on GitHub.
