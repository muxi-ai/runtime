# MUXI Runtime Agent Playbook

Your fast-reference for building, debugging, and extending the MUXI Runtime without losing critical context.

---

## MUXI Ecosystem

This repository is part of the larger MUXI ecosystem.

**Complete architectural overview:** See [ARCHITECTURE.md](https://github.com/muxi-ai/muxi/blob/main/ARCHITECTURE.md) in the main MUXI repo.

**Deep codebase mental model:** See [mental-model.md](mental-model.md) for detailed architecture, data flows, module internals, and agent context.

**This repo (runtime):** The formation execution environment - FastAPI-based Python runtime packaged as SIF container.

---

## TL;DR: Non-Negotiables
- Use sub-agents: `file-analyzer` for reading files, `code-analyzer` for code search/analysis, `test-runner` for any tests.
- Maintain required LLM config: formations must declare `llm.models` with a `text` entry (e.g., `openai/gpt-4o-mini`). System aborts if missing.
- Respect the formation loading order: Observability → LLM configuration → Memory systems → Document processing → Background services → Agents.
- Follow the absolute rules: no partial implementations, no dead code, no duplication, consistent naming, no over-engineering, keep concerns separated, prevent resource leaks, and study existing code before writing new logic.
- Treat tests seriously: no mocks, prefer real integrations, single-focus assertions, deterministic data, and run the right test tier (unit/integration/e2e). Every e2e run uses the scripted runner.
- Keep workflow hygiene: plan carefully, review and simplify your plan before execution, optimize for the smallest viable change, strip whitespace on blank lines, prefer `ast-grep` over raw regex, and use `trash` instead of `rm`.
- Start CodeRabbit early (`coderabbit --prompt-only`), watch its feedback, and resolve every flagged issue before moving on.
- Honor reflection protocol after complex engagements: offer to update CLAUDE.md when the task warrants it.
- Never use emojies
- Always obtain the current date and time from the system using the `date` command before writing any frontmatter or using dates in documents.

## Architecture Snapshot
- **Formation-first**: YAML formations describe the entire AI system; runtime turns them into a live orchestration.
- **System flow**:
  ```
  Formation Engine → Overlord Orchestrator → Agent Pool
         ↓                    ↓                  ↓
     Validation          Coordination       Execution
         ↓                    ↓                  ↓
  Memory Systems ← Services Layer → Tool Integration
  ```
- **Critical patterns**:
  - Provider-agnostic LLM abstraction via OneLLM.
  - SOP-driven orchestration for complex workflows.
  - Three-tier memory: Buffer (FIFO + vector) → Persistent (DB) → Vector (FAISSx).
  - Unified services: MCP, agent-to-agent, multimodal, scheduler, observability.
  - Memobase partitions guarantee multi-user isolation.

## Project Layout
```
runtime/
├── src/muxi/runtime/      # Core runtime package (shares muxi namespace with SDK)
│   ├── formation/         # Formation engine, overlord, agents, workflows
│   ├── services/          # Memory, MCP, observability, scheduler
│   └── datatypes/         # Type definitions
├── tests/                 # Unit + integration tests
├── e2e/                   # End-to-end tests (200+ across 12 areas)
├── contributing/          # Contributor documentation
└── migrations/            # Database migrations
```

## Development Standards
- **Language & style**: target Python 3.10+, adopt async I/O where throughput improves, format with Black (line length 100) and isort (`profile=black`), lint with Ruff & Flake8 (line length 120), keep naming snake_case/PascalCase as appropriate.
- **Testing discipline**: map fast logic to `tests/unit`, service seams to `tests/integration`, end-to-end flows to `e2e/tests`; rely on deterministic data or fixtures from `tests/fixtures`; structure tests with arrange/act/assert and meaningful failure output.
- **Workflow basics**: branch naming `feature/<topic>` or `fix/<issue>`, commits are descriptive, PRs stay small with rationale, logs/screenshots, links, and pytest evidence.
- **Code review loop**: keep CodeRabbit running, revisit its output after significant edits, and iterate until the report is clean.

## Sub-Agent Protocol
- **File operations**: delegate file reads to the file-analyzer agent for summarized context.
- **Code analysis**: use the code-analyzer agent for tracing logic, vulnerability hunts, or repo-wide searches.
- **Testing**: pipe every test run through the test-runner agent using the provided script. Ensure every test reports a summary, and for e2e runs append the exact block below after the logs:
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

## System Requirements & Guarantees
- **LLM configuration**:
  ```yaml
  llm:
    models:
      - text: "openai/gpt-4o-mini"  # REQUIRED
      - vision: "..."               # optional, falls back to text
      - audio: "..."                # optional, falls back to text
  ```
  No default model exists; missing `text` fails fast.
- **Formation load order**: Observability → LLM configuration → Memory systems → Document processing → Background services → Agents.
- **Error handling**: fail fast on critical config, log-and-continue for optional features, degrade gracefully on external outages, surface user-friendly feedback via the resilience layer.
- **Multilingual stance**: rely on LLM intent detection instead of regex; avoid language-specific heuristics and hardcoded command strings. Example: replace `re.match(r'^(help|assist)'...)` checks with LLM-driven intent detection so guidance works in any language.

## Runtime Operations
- **SOP execution pipeline**:
  ```python
  user_request → SOP search (FAISS) → Pass SOP to decomposer → Execute workflow
  ```
  SOP search is semantic; full SOP content feeds the decomposer; execution mode varies by SOP type (template vs guide).
- **Intent-based routing**:
  ```python
  async def chat(self, message: str, user_id: str):
      intent = await self.intent_detector.analyze(message)
      sops = await self.sop_coordinator.search(message)
      if sops:
          agents = self.select_agents_for_sop(sops[0])
      else:
          agent = self.select_agent(intent)
      context = await self.memory.get_context(user_id)
      response = await agent.process(message, context)
  ```
- **Memory tiers**:
  - Working memory: always on, size-configurable.
  - Buffer memory: FIFO plus vector recall for recent context.
  - Persistent memory: PostgreSQL/SQLite backing.
  - Vector memory: FAISSx for semantic retrieval.
  - Multi-user isolation: enforced through Memobase partitioning.
- **ID hierarchy**:
  ```
  user_id (user isolation)
    └── session_id (chat grouping)
        └── request_id (single interaction with all clarifications)
  ```
  - `user_id`: top-level isolation, lowercase, "0" in single-user mode.
  - `session_id`: groups related requests into a conversation, scopes buffer memory filtering.
  - `request_id`: tracks ONE complete interaction including all clarifications; used as key for `clarification:{request_id}`.
  - **Clarification coordination** (intentional two-level lookup):
    - Overlord: `_pending_clarification[session_id]` → returns `request_id`
    - UnifiedClarificationSystem: `clarification:{request_id}` → clarification state
    - **⚠️ DO NOT attempt to "fix" this two-level lookup—it's intentional and correct**

## Observability Standards
- **Event types**: 349 typed events across 5 categories (SystemEvents, ConversationEvents, ServerEvents, APIEvents, ErrorEvents) covering complete request lifecycle.
- **Validation requirement**: 100% validation mandatory—run `python3 scripts/validate_events.py` before committing any observe() changes.
- **Event naming conventions**:
  - Past tense for completion: `_COMPLETED`, `_FAILED`, `_SELECTED`
  - Present tense for progress: `_PROCESSING`, `_STARTED`, `_PLANNING`
  - Component prefix: `OVERLORD_*`, `AGENT_*`, `WORKFLOW_*`, `MEMORY_*`, `MCP_*`
- **Adding events**: prefer reusing existing events with enhanced metadata over creating new types; add new events only when semantically distinct.
- **Metadata enhancement**: enrich events with performance metrics, quality scores, and diagnostic fields.
- **Event lifecycle**: emit `_STARTED` for initiation, `_COMPLETED` for success, `_FAILED` for errors—ensures complete traceability.

## Testing Philosophy
- Use real services (OpenAI, Anthropic, live MCP, actual embeddings); mocks are disallowed.
- Tests should spotlight the targeted feature and succeed when that feature works—even if ancillary services are missing.
- Design tests to expose real defects with verbose diagnostics; never submit cheater tests.
- Feature-day orientation: Days 1-3 foundation/memory/multimodal, Days 4-6 MCP/file generation/knowledge, Days 7-12 advanced workflow & resilience.

## E2E Testing Standards
- **Test Structure**: All e2e tests in `e2e/tests/[area_number]_[area_name]/`; 12 areas covering foundation → scheduling.
- **Three Test Patterns**:
  - Pattern 1 (Runtime Modification): Modifies formation at runtime—suitable for behavior tests.
  - Pattern 2 (Shared Directory): Uses shared formation directory—suitable for tests with common config.
  - Pattern 3 (Separate Formations): Each test has isolated formation—suitable for complex/specialized tests.
- **Pattern Selection**: Choose based on test requirements, not standardization; standalone scripts > complex abstractions for timing-sensitive tests (e.g., scheduler).
- **Async Cleanup**: Always use async cleanup utilities for tests creating fire-and-forget tasks; prevents RecursionError spam.
- **Formation Setup**: Co-locate formations with tests; use symlinks for `.key` and `secrets.enc` files.
- **Service Dependencies**: Document required services (PostgreSQL, FAISSx, webhook server); tests may require specific ports/configs.
- **Simplicity Principle**: Don't over-abstract—complex base classes can introduce bugs; working tests > standardized tests.

## Troubleshooting Cheatsheet
- **Missing required LLM capability 'text'**: ensure formation includes a `text` model under `llm.models`.
- **Intent detection failing**: verify formation LLM entry, credentials, and model capability coverage.
- **Workflow not triggering**: confirm `auto_decomposition: true`, validate complexity threshold (default 7.0), and ensure no agent override is forcing a bypass.
- **Event validation failing**: run `python3 scripts/validate_events.py` to identify missing event types; all observe() calls must use enum-defined events.
- **E2E test 'str' object is not callable**: check if base class abstraction interferes; consider standalone pattern without base class.
- **RecursionError spam in tests**: missing async cleanup; use `ensure_async_cleanup()` utility from test helpers.
- **Formation not loading in tests**: verify symlinks to `.key` and `secrets.enc` use correct relative paths.
- **Scheduler tests timing out/failing**: avoid RUNTIME pattern; use standalone scripts with direct formation loading for precise timing control.
- **'list' object has no attribute 'get' during config load**: knowledge config format mismatch. Use dict format (`knowledge: {enabled: true, sources: [...]}`) or remove the field entirely if not needed. Empty list `knowledge: []` is also valid.
- **Docker AMD64 image too large**: PyTorch defaults to CUDA on AMD64 (4GB+ NVIDIA libs). Fix: Install CPU-only PyTorch first via `--index-url https://download.pytorch.org/whl/cpu`.
- **SIF build fails with "no space left"**: Add disk cleanup step before Apptainer install in CI workflow.
- **GitHub release upload fails (>2GB)**: Check Docker image size—likely CUDA bloat. SIF files must be under 2GB.
- **Artifact generation returns 0 artifacts (no error logged)**: The `_invoke_tool` catch-all `except Exception` silently converts failures to `{"error": ..., "status": "error"}` dicts that lack `_artifact`, so the artifact extractor skips them. Check server logs for the "using artifact service" event—if "Executed planned step" appears at the same millisecond, the subprocess failed instantly.
- **Artifact temp directory vanishes between runs**: macOS (and some container runtimes) clean `/var/folders` temp dirs. The `_create_execution_dir` method now re-creates the base dir on every call—do not rely on the `__init__` mkdir alone.
- **Artifact sandbox `ulimit -v` kills matplotlib/numpy on Linux**: `ulimit -v` limits virtual address space (not RSS). matplotlib + numpy + scipy map many shared libraries that easily exceed 512MB virtual. Current limit is 2GB. If you see subprocess hangs that resolve exactly at the timeout, check the memory limit first.
- **SIF chart generation times out but works in Docker**: Likely the `ulimit -v` virtual memory limit (Linux-only code path in `artifact_service.py`). Test by running the artifact service directly inside the SIF: `singularity exec ... python -c "from muxi.runtime.formation.artifacts.artifact_service import ArtifactService; ..."`.
- **`docker system prune -af` breaks SIF deployments**: This removes the runtime-runner image which contains `/opt/muxi-tools` (node, npx, git, curl, fonts). Rebuild with `docker build -t ghcr.io/muxi-ai/runtime-runner:latest .` from the runtime-runner repo.
- **LLM ignores generate_file constraints**: Claude Haiku may ignore soft phrasing like "Do NOT import requests". Use stronger language: "NEVER", "WILL BE REJECTED", "offline sandbox". Even so, LLMs will generate networking code when the task implies fetching data—allow networking imports rather than fighting the pattern.
- **generate_file uses fpdf and fails on Unicode**: fpdf's default font (Helvetica) cannot encode non-ASCII characters. The constraint prompt now says "prefer reportlab over fpdf". If fpdf is used, the code must strip or replace non-ASCII characters.
- **SyntaxError after an AI edit near secret-like identifiers**: display-layer secret masking can leak `***` strings into the written file. After editing lines containing auth/secret/key identifiers, verify with `python3 -c "import ast; ast.parse(open('<file>').read())"`.

## Development Patterns
- **Adding services**: implement in `src/muxi/services/`, wire into formation loading, register with the overlord, and update schemas when configuration is exposed.
- **Orchestration edits**: modify `overlord.py`, sync workflow integrations, preserve SOP compatibility, test with real formations.
- **Memory updates**: touch the relevant tier, maintain partitioning, validate Memobase behavior, and confirm extraction paths remain intact.
- **E2E test development**:
  - Review existing tests in the area to understand patterns.
  - Choose appropriate pattern (runtime/shared/separate) based on test needs.
  - Use symlinks for `.key` and `secrets.enc` files with correct relative paths.
  - Include async cleanup for proper resource management (fire-and-forget tasks).
  - Test with actual services—no mocks.
  - Verify formation path resolution works correctly.
  - Prefer simplicity: standalone script > complex base class if test is timing-sensitive.

## File Index
- `src/muxi/runtime/formation/formation.py` — formation lifecycle management.
- `src/muxi/runtime/formation/overlord/overlord.py` — central orchestration logic.
- `src/muxi/runtime/formation/workflow/` — SOP execution pipeline.
- `src/muxi/runtime/formation/resilience/` — error recovery and user messaging.
- `src/muxi/runtime/services/` — runtime services catalog.
- `src/muxi/runtime/datatypes/observability.py` — event type definitions.
- `scripts/validate_events.py` — event validation utility.
- `e2e/tests/` — 12 test areas covering all runtime functionality.
- Formation schema: see [agentformation.org](https://agentformation.org).

## Artifact Service (generate_file)
- `generate_file` is a **built-in tool**, not an MCP. Registered in `agent.py`, routes to `artifact_service.py`.
- Architecture: LLM generates Python code via `_infer_tool_parameters()` → code validated via AST (`_validate_code`) → executed via `subprocess.run` in an isolated temp directory → output files tracked and wrapped as `MuxiArtifact`.
- **Allowed imports** are whitelisted in `ALLOWED_IMPORTS` (artifact_service.py). Includes data science, visualization, document generation, and networking libraries.
- **Constraints** are injected into the `_infer_tool_parameters` system prompt for `generate_file` calls: library preferences, backend settings, encoding notes.
- **Sandbox limits**: `MAX_EXECUTION_TIME = 60s`, `MAX_MEMORY_MB = 2048` (virtual, via `ulimit -v` on Linux only).
- **Artifact extraction**: After planning execution, `my_results` is scanned for dicts containing `_artifact` key. Only results from `generate_file` with a successful `MuxiArtifact` will be extracted. Errors are caught silently—check logs for "using artifact service" followed immediately by "Executed planned step" (same timestamp = instant failure).
- **SIF considerations**: The subprocess inherits the Singularity environment. Ensure `/tmp` is bind-mounted and writable. The `ulimit -v` code path only runs on Linux—macOS uses direct `subprocess.run` without memory limits.

## Upcoming Features

### Agent Skills (SKILL.md)
Implementation of the open [Agent Skills specification](https://agentskills.io/specification):
- Skills directory: `formation/skills/{skill-name}/SKILL.md`
- Progressive disclosure: metadata at startup, full content on activation
- Executor container for script execution (ZeroMQ-based)

### Enterprise Permissions
Group-based permission filtering via `muxi-enterprise` package:
- YAML-based group definitions with inheritance
- Agent/MCP filtering by group membership
- Runtime patching (zero changes to OSS code)

## Technical Debt Targets
1. Validate declared model capabilities vs assigned responsibilities.
2. Improve performance via model instance caching.
3. Build richer fallback chains for capability gaps.
4. Ship tooling for configuration migrations.

## Collaboration Norms
- Feedback is expected: challenge assumptions, flag better approaches, call out missing conventions.
- Communicate succinctly; offer plans when detail is needed, otherwise keep responses tight.
- Skip flattery; stick to factual, skeptical, collaborative dialogue.
- Ask clarifying questions instead of guessing intent.

## Hard Rules Checklist
- No partial implementations or "temporary" simplifications.
- Eliminate dead code; reuse existing helpers/constants before introducing new ones.
- Preserve naming consistency across modules, classes, functions, and variables.
- Avoid over-engineering—choose the simplest workable solution.
- Keep concerns separated; no mixing validation, persistence, and presentation layers.
- Prevent resource leaks: close DB connections, cancel timers, remove listeners.
- Read existing code paths to understand conventions before modifying or extending.

## Reflection Protocol
1. After any multi-step or feedback-heavy task, ask: “Would you like me to reflect on our interaction and suggest potential improvements to the active CLAUDE.md file?”
2. If the user declines or stays silent, conclude normally.
3. If the user agrees:
   - Review relevant feedback and compare it with the active CLAUDE.md guidance.
   - List the in-scope CLAUDE.md files (global + workspace) influencing the task.
   - Propose concrete, actionable edits (use `replace_in_file` blocks when feasible).
   - Await approval before applying adjustments, then return to task completion flow.

## Operational Notes
- Secrets live beside formation YAMLs in encrypted `secrets.enc` files (with `secrets` template showing required keys); avoid environment variables for runtime config.
- Commit hooks may false-positive on auth-related identifiers (e.g. `*Authenticator(`, `_config.get(`). If a commit of reviewed, secret-free code is blocked, the user commits manually; do not reword code to appease the scanner.

## Running Tests
- **Unit tests**: `python -m pytest tests/unit/ -v` (standard pytest).
- **E2E tests**: Each e2e test is a **standalone script**, not a pytest test. Do NOT run them with `pytest`. Use the dedicated runners from the `e2e/` directory:
  - **Full suite**: `cd e2e && python run_all_tests.py` — runs every test sequentially with per-area timeouts, early-kill on success, and crash-signal retries. Saves report to `e2e/results/test_report.json`.
  - **Random sample** (sniff-test): `cd e2e && python run_random_tests.py N` — picks N random tests from the full pool and runs them. Defaults to 10. Saves report to `e2e/results/random_test_report.json`.
  - **Single test**: `cd e2e/tests/<area> && python test_<name>.py` — run one test directly as a script.
- Both runners handle `PYTHONPATH`, timeouts, early-kill after SUCCESS markers, and retry on SIGSEGV/SIGABRT crashes.
