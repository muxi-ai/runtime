# Trigger System E2E Tests

End-to-end tests for the MUXI trigger system.

## Test Coverage

### 13A: Basic Functionality
- **13A1** - List triggers endpoint
- **13A2** - Execute trigger (sync mode)
- **13A3** - Execute trigger (async mode)  
- **13A4** - Nested data rendering

### 13B: Error Handling
- **13B1** - Missing key error
- **13B2** - Trigger not found
- **13B3** - Formation not found

## Running Tests

```bash
# Run all tests
python run_trigger_tests.py

# Run individual test
python test_13a1_list_triggers.py
```

## Test Formation

Formation located in `formation-triggers/`:
- Port: 18271
- Triggers: test-simple, test-nested, github-issue
