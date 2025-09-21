# Area 2: Memory Tests

## Overview
Area 2 tests validate the three-tier memory architecture in MUXI Runtime:
- **Buffer Memory**: Short-term context with FIFO and vector search
- **Persistent Memory**: Long-term storage with PostgreSQL/SQLite
- **Vector Memory**: Semantic search with FAISSx integration

## Test Organization

### Pattern
All Area 2 tests follow **Pattern 2: Shared Directory** approach:
- Single shared formation directory: `formations/formation-memory/`
- Multiple YAML files for different memory configurations
- Tests inherit from `BaseMemoryTest` class
- Each test loads specific YAML configuration

### Test Categories

#### Core Memory Tests (Fully Migrated)
1. **Basic Operations** (2a1, 2b1, 2c1, 2d1)
   - Buffer memory configuration
   - SQLite persistence
   - PostgreSQL user isolation
   - Local vs remote buffer modes

#### Vector Search Tests (Templates Created)
2. **FAISSx Integration** (2e, 2e1, 2e3)
   - Authentication modes
   - PostgreSQL + FAISSx hybrid
   - Multi-user vector search

#### Advanced Features (Templates Created)
3. **Extraction & Collections** (2i1-2i3, 2j1)
   - Natural language extraction
   - Complex extraction patterns
   - Collection field usage

4. **Optimization & Resilience** (2k1-2k2, 2l1, 2m1)
   - Enhanced prompt integration
   - Memory priority
   - Database optimization
   - Error resilience

5. **Preference System** (2o, 2o1, 2o2)
   - Preference detection
   - Preference storage
   - Preference retrieval

## Formation Configurations

| Configuration | File | Purpose |
|--------------|------|---------|
| `basic` | formation-basic.yaml | Simple memory setup |
| `buffer_local` | formation-buffer-local.yaml | In-memory FAISS |
| `buffer_remote` | formation-buffer-remote.yaml | FAISSx server |
| `sqlite` | formation-sqlite.yaml | SQLite persistence |
| `postgres` | formation-postgres.yaml | PostgreSQL persistence |
| `postgres_faissx` | formation-postgres-and-faissx.yaml | Hybrid storage |
| `postgres_faissx_auth` | formation-postgres-and-faissx-with-auth.yaml | With authentication |
| `auto_extract` | formation-auto-extract.yaml | Auto-extraction |
| `memory_limits` | formation-memory-limits.yaml | Resource limits |

## Running Tests

### Individual Test
```bash
cd tests/e2e_new/2_memory
python test_2a1_basic_conversation_context.py
```

### All Memory Tests
```bash
pytest tests/e2e_new/2_memory/test_*.py -v
```

### With Required Services
```bash
# Start PostgreSQL
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=testpass postgres:15

# Start FAISSx (no auth)
faissx.server run --port 45678 &

# Start FAISSx (with auth)
faissx.server run --port 65432 --enable-auth --auth-file formations/faissx-auth.json &

# Run tests
pytest tests/e2e_new/2_memory/ -v
```

## Migration Status

### Summary
- **Total Tests**: 26 files
- **Fully Migrated**: 4 tests (complete with logic)
- **Templates Created**: 15 tests (structure ready, logic migration needed)
- **Not Migrated**: 7 helper/debug tests (low priority)

### Progress
- ✅ Core test structure established
- ✅ BaseMemoryTest class created
- ✅ Shared formations copied
- ✅ Import paths fixed
- 🚧 15 tests need logic migration from templates
- ⏳ 7 helper tests pending (low priority)

## Key Improvements from Migration

1. **Standardized Structure**: All tests follow same pattern
2. **Shared Base Class**: `BaseMemoryTest` reduces duplication
3. **Consistent Output**: Using `TestOutputFormatter`
4. **Proper Cleanup**: Automatic resource cleanup
5. **Better Organization**: Clear test categories
6. **Formation Reuse**: Single shared formation directory

## Next Steps

1. **Complete Logic Migration**: Fill in test logic for 15 template files
2. **Validate Tests**: Run full test suite with services
3. **Remove Old Tests**: Clean up original test files
4. **Update CI/CD**: Add new test paths to automation

## Notes

- Helper tests (`*_helper.py`) are debug utilities and have lower priority
- All tests require the shared `secrets.enc` and `.key` files
- Some tests require external services (PostgreSQL, FAISSx)
- Tests use `os._exit()` for clean shutdown