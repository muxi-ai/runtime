## MUXI Runtime Python Coding Style Guide

This guide codifies how we write Python in MUXI. It complements the architectural rules in `docs/` and enforces consistency across `src/muxi/`.

### Scope and tooling
- **Language**: Python 3.10+
- **Formatter**: Black, line length 100
- **Import sorter**: isort, profile "black", line_length 100
- **Type checker**: mypy (strict settings in `pyproject.toml`)
- **Test runner**: pytest

Suggested workflow:
```bash
isort . && black .
mypy src
pytest -q
```

---

### Guiding principles
- Optimize for clarity and maintainability over cleverness.
- Small, composable functions with clear contracts and types.
- Fail early with actionable errors; never hide failures.
- Prefer explicitness: explicit imports, explicit returns, explicit timeouts.

---

### Naming conventions
- **Modules/Packages**: `lowercase_with_underscores` (e.g., `buffer_manager.py`).
- **Classes**: `PascalCase` (e.g., `RequestManager`).
- **Exceptions**: `PascalCase` and end with `Error` (e.g., `ConfigurationError`).
- **Functions/Methods**: `lowercase_with_underscores` and verbs (e.g., `load_config`, `emit_event`).
- **Variables**: descriptive nouns (e.g., `request_context`, `retry_attempts`). Avoid 1–2 char names.
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT_SECONDS`).
- **Booleans**: predicate-style names (e.g., `is_enabled`, `has_vector_search`).
- **Private members**: prefix with `_` (e.g., `_rebuild_index`).
- **Tests**: file names `test_*.py`; tests named `test_<behavior>_...`.

Do:
```python
class CredentialResolverError(Exception):
    pass

def is_retryable(status_code: int) -> bool: ...
```

Don't:
```python
class CredentialResolver(Exception): ...  # Missing Error suffix

def retryable(x): ...  # Vague and untyped
```

---

### Function and method design
- Single responsibility; keep parameter lists small (≤ 5). Use small data objects (Pydantic/TypedDict) for structured inputs.
- Always annotate parameters and return types. Avoid `Any`.
- Prefer pure functions for business logic; isolate I/O.
- Validate inputs at the boundary; raise precise exceptions.
- Use early returns (guard clauses) to avoid deep nesting.

Do:
```python
def fetch_agent_cards(agent_ids: list[str], timeout_seconds: float = 5.0) -> dict[str, str]:
    """Return mapping agent_id -> card contents."""
    if not agent_ids:
        return {}
    # ...
```

Don't:
```python
def doStuff(a):  # untyped, vague
    cards = {}
    if len(a) > 0:
        # deep nesting ...
        return cards
    else:
        return {}
```

Return style:
- Return explicit values; avoid sentinel `None` unless documented as `T | None`.
- Use `tuple[...]` or small model objects for multi-values; avoid positional magic lists.

---

### Async and concurrency
- Prefer `async`/`await`. Do not block the event loop.
- Use `httpx.AsyncClient` with explicit `timeout=`; never unbounded I/O.
- Use `anyio` task groups for fan-out/fan-in; set reasonable concurrency limits.
- Handle cancellation (`CancelledError`) and cleanup.
- Offload CPU-bound work to threads/processes if needed; avoid heavy CPU in the loop.

Do:
```python
import httpx

async def get_json(url: str, timeout_s: float = 5.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
```

Don't:
```python
import requests

def get_json(url):  # blocks event loop if used in async contexts
    return requests.get(url).json()
```

---

### Typing standards (mypy)
Strict mypy rules apply (see `pyproject.toml`).
- Annotate all defs. Use modern forms: `list[str]`, `dict[str, Any]`, `str | None`.
- Prefer precise types (`TypedDict`, `Literal`, `Enum`) over broad `dict`/`str`.
- Use Pydantic v2 models for validated external inputs/outputs.
- Avoid `# type: ignore`. When unavoidable, narrow with a reason (e.g., `# type: ignore[arg-type]  # fast path for known variant`).

---

### Errors and exceptions
- Raise specific, domain-appropriate exceptions. Include actionable messages, omit secrets.
- Never use bare `except:`. Catch narrow exceptions (`httpx.TimeoutException`).
- Re-raise with context using `from` to preserve traceback.
- Only swallow exceptions where failure must not disrupt app flow (e.g., optional telemetry) and document why.

Do:
```python
try:
    data = await get_json(url, timeout_s=5)
except httpx.TimeoutException as exc:
    raise ExternalServiceError(f"Timeout fetching: {url}") from exc
```

Don't:
```python
try:
    data = await get_json(url)
except Exception:
    return {}  # Silent failure
```

---

### Observability and logging
- Use `EventLogger` (`src/muxi/services/observability/logger.py`) for structured events.
- Emit typed events (System, Conversation, Error, Server, API). Attach `RequestContext` when available.
- Route non-conversation events to stdout (as designed); conversation events follow configured sinks.

Do:
```python
from muxi.services.observability.logger import EventLogger
from muxi.datatypes.observability import SystemEvents, EventLevel

logger = EventLogger(level=EventLevel.INFO)
logger.emit_event(SystemEvents.STARTUP, description="Scheduler initialized")
```

Don't:
```python
print("started")  # use EventLogger instead
```

---

### Imports
- Order: stdlib, third-party, local. No wildcard imports.
- Use absolute imports across major components (e.g., formation → services). Use relative imports within a feature subtree to reduce verbosity.
- Avoid deep import chains that create cycles; refactor shared pieces into `utils/` or `datatypes/`.

---

### Docstrings and comments
- Public modules, classes, and functions must have docstrings. Keep them concise and high-signal.
- Use Google-style (or similar) sections for non-trivial APIs: Args, Returns, Raises, Examples.
- Explain the “why”, not the obvious “what”. Place comments above code blocks.

Do:
```python
def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search buffer by semantic similarity.

    Args:
      query: Natural language query.
      limit: Maximum results.
    Returns:
      Ranked results with metadata.
    """
```

---

### Data models and configuration
- Use Pydantic v2 models for validated configs, API payloads, and public schemas.
- Prefer `Enum` for constrained choices. Avoid magic strings.
- For unvalidated internal mappings, prefer `TypedDict` from `src/muxi/datatypes/type_definitions.py`.

---

### Security
- Never hardcode secrets; use formation secrets interpolation (`${{ secrets.NAME }}`).
- Sanitize inputs; validate external payloads via Pydantic.
- Follow least-privilege; respect A2A/MCP auth boundaries.

---

### Testing
- Tests live under `tests/` and are named `test_*.py`.
- Use Arrange–Act–Assert and descriptive test names.
- For async, use pytest’s async support and helpers in `tests/utils/`.
- Isolate external I/O with fakes/mocks; set deterministic timeouts.
- Add tests for error paths and edge cases, not just happy paths.

Do:
```python
async def test_fetch_times_out(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("boom"))
    with pytest.raises(ExternalServiceError):
        await fetch()
```

---

### Performance
- Prefer readability; optimize only with evidence (profiling/benchmarks).
- Use provided services (vector search, caching) instead of bespoke implementations.
- Bound work with timeouts, rate limits, and batch sizes where applicable.

---

### Pull request checklist
- Types on all new/changed functions; no untyped defs.
- Docstrings for public APIs; examples where helpful.
- Black/isort clean; ≤100 columns.
- Explicit I/O timeouts; robust error handling; no bare `except`.
- EventLogger used for meaningful events.
- Tests added/updated; mypy and pytest pass.

---

### Concrete Do/Don’t reference

Imports:
```python
# Do
from typing import Iterable
import httpx
from muxi.services.scheduler.service import SchedulerService

# Don’t
from typing import *
from muxi.services.scheduler.service import *
```

Async HTTP:
```python
# Do
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.get(url)
    resp.raise_for_status()

# Don’t
resp = requests.get(url)  # blocks
```

Exceptions:
```python
# Do
class ExternalServiceError(Exception):
    pass

try:
    await op()
except httpx.HTTPError as exc:
    raise ExternalServiceError("fetch failed") from exc

# Don’t
except Exception:
    pass
```

Typing:
```python
# Do
def parse_ids(value: str | list[str]) -> list[str]: ...

# Don’t
def parse_ids(value): ...  # untyped & ambiguous
```

---

### Directory references
- Code: `src/muxi/`
- Data types: `src/muxi/datatypes/`
- Services: `src/muxi/services/`
- Formation: `src/muxi/formation/`
- Observability: `src/muxi/services/observability/`

This guide is living; update it as new patterns solidify in the codebase.
