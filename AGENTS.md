# Repository Guidelines

## Project Structure & Modules
- `src/muxi/`: Python package (runtime core). Key areas: `formation/` (loading, workflow, resilience), `services/` (llm, memory, mcp, multimodal, a2a, observability), `utils/`.
- `tests/`: Pytest suites (`unit/`, `integration/`, `e2e/`) plus fixtures and assets. Test discovery: `test_*.py`, classes `Test*`, functions `test_*`.
- `examples/`: Small usage samples. `test-formations/`: YAML formations for tests.
- `schemas/`, `migrations/`, `docs/`, `scripts/`: Supporting specs, DB migrations, docs, and utilities (e.g., `scripts/encrypt_credentials_data.py`).

## Build, Test, and Development
- Create env and install: `python -m venv .venv && source .venv/bin/activate` then `pip install -e .[dev]`.
- Run tests: `pytest` (verbose: `pytest -v`; coverage: `pytest --cov=muxi --cov-report=term-missing`).
- Type check: `mypy src` and `pyright` (config in `pyrightconfig.json`).
- Lint/format: `ruff check .`, `black .`, `isort .`. CI uses Black line length 100 and isort profile `black`.
- SpaCy model (first run): `python -m spacy download en_core_web_sm` (setup tries to auto-install).

## Coding Style & Naming
- Python 3.10+ with type hints on public APIs; async I/O where applicable.
- Formatting: Black (100 cols), isort (profile=black). Lint: Ruff + Flake8 (max line length 120).
- Names: modules `snake_case`, classes `PascalCase`, functions/vars `snake_case`; tests mirror package paths and use explicit names describing behavior.

## Testing Guidelines
- Framework: pytest with asyncio auto mode. Prefer real integrations where feasible; otherwise use fixtures in `tests/fixtures/`.
- Place: quick logic in `unit/`, service boundaries in `integration/`, end-to-end flows in `e2e/` using `test-formations/`.
- Conventions: one assertion focus per test, arrange/act/assert comments, deterministic data.

## Commit & Pull Requests
- Commits: clear, descriptive messages (no strict conventional format). Example: `feat: add vector memory cleanup` or `fix: handle missing formation key`.
- Branches: `feature/<short-topic>` or `fix/<issue-ref>`.
- PRs must include: concise description, rationale, screenshots/logs if relevant, links to issues, and test results (`pytest ...`). Keep PRs focused and small.

## Security & Configuration
- Secrets via `.env` (see README); never commit credentials. Use `scripts/encrypt_credentials_data.py` for secure storage.
- Validate formations against `schemas/`. Prefer least-privilege for DB and external services.

## Architecture Overview
```
       Client/Server API            Formations (YAML)
              |                           |
              v                           v
+--------------------- MUXI Runtime ----------------------+
|  Formation Engine  |  Overlord   |  Services (LLM/IO)   |
|     load/validate  | orchestrate | memory, mcp, a2a     |
+---------------------------------------------------------+
                 | events/IO      | providers/DB
                 v                v
          Observability        External Systems
```
Key flows: YAML → Formation → Overlord → Agents/Services → Observability; async-first with real integrations.
