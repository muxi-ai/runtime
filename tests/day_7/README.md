# Day 7 Tests: Task Decomposition

This directory contains tests for Day 7a - Task Decomposition capabilities of the MUXI Runtime.

## Test Files

### test_7a_task_decomposition.py
The main test that verifies the Overlord's ability to naturally decompose complex tasks across multiple agents.

**Test scenario**: 
- User prompt: "research 'ran aroussi funding gap' and write a short summary about it. save the summary as a linear issue"
- Expected flow: researcher → writer → project-manager
- Validates that actual web search is performed (not general LLM knowledge)

### test_7a_pdf_artifact.py
Tests PDF generation and artifact handling through the multi-agent system.

**Test scenario**:
- User requests PDF generation with specific content
- Validates artifact creation and base64 encoding
- Verifies MuxiArtifact structure with data_url field

## Running Tests

```bash
# Run task decomposition test
python test_7a_task_decomposition.py

# Run PDF artifact test  
python test_7a_pdf_artifact.py
```

## Test Outputs

Results are saved in `test_outputs/` directory with timestamps for debugging.

## Note

These tests currently demonstrate agent routing rather than true workflow decomposition. The workflow system exists but needs to be integrated into the Overlord's chat flow (see workflow-integration-implementation-plan.md).