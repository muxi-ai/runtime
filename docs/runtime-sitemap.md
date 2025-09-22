# MUXI Runtime Internals - Documentation Sitemap

This sitemap outlines the "MUXI Runtime Internals" documentation space for engineers who need to understand, extend, or embed the runtime. It assumes readers already know the public-facing MUXI documentation and now want implementation-level detail.

- **Landing & Orientation** – Position the runtime within the larger MUXI platform, highlight key differentiators, and provide quick entry points into core subsystems.
  - **Who Is This For** – Identify contributor personas (core runtime devs, formation authors, embedded integrators) and set expectations for the technical depth.
  - **Runtime at a Glance** – Summarize the formation→overlord→agent pipeline with links to architectural diagrams.
  - **Terminology Primer** – Define critical terms (formation, request_id hierarchy, SOP, MCP) to align contributors on vocabulary.
  - **Navigation Map** – Surface the primary docs pillars and suggest first reads for different contributor personas. Includes quick-reference links to key docs (e.g., `context/project-structure.md`, `docs/clarification-system.md`).
- **Formation Fundamentals** – Explain how the runtime ingests formations, wires services, and prepares execution state.
  - **Initialization Pipeline** – Detail the strict loading order (observability→LLM→memory→services→agents) and failure modes.
  - **Secrets & Credentials** – Describe secrets.env handling, credential scoping, and rotation strategies.
  - **Formation Loader Internals** – Cover formation parsing, normalization hooks, and extension points inside `src/muxi/formation`.
  - **Formation Library** – Curate annotated examples from `examples/` and `test-formations/` with scenario-based callouts.
- **Core Systems** – Connect high-level concepts to code modules for the formation engine, overlord core, and agent lifecycle.
  - **Formation Engine Internals** – Cover configuration loading, validation entry points, and extension hooks in `src/muxi/formation`.
  - **Overlord Core Loop** – Trace `_process_sync_chat`, intent detection, clarification flow, and routing logic with code references.
  - **Agent Pool & Execution** – Describe agent registration, capability metadata, and execution lifecycle management.
  - **Services Layer Overview** – Map shared services (memory, LLM, observability, scheduler, etc.) to their owning packages.
- **Memory Architecture & Intelligence** – The digital brain that learns and forgets intelligently, enabling context preservation and autonomous improvement.
  - **Three-Tier Memory Deep Dive** – Buffer (FIFO+vector) → Persistent (DB) → Vector (FAISSx) with detailed flow diagrams and performance characteristics.
  - **Context Preservation & Continuity** – How memory maintains conversation flow across sessions, agent handoffs, and clarification cycles.
  - **Intelligent Cleanup & Optimization** – What gets remembered vs forgotten, FIFO rules, vector search optimization, and focus management.
  - **Multi-User Isolation** – Memobase partitioning mechanics, formation-based boundaries, and user context segregation with user_id → session_id → request_id hierarchy.
  - **Memory Performance Tuning** – Configuration parameters, monitoring strategies, cache hit optimization, and scaling patterns.
  - **Memory System Migration** – Migrating between backends, upgrading storage formats, and handling large-scale data evolution.
- **Workflow & Orchestration** – Document intelligent task decomposition, SOP integration, and resilience behaviors.
  - **Complexity Analysis & Routing** – Explain scoring methods, routing strategies, and configurable thresholds.
  - **SOP System** – Detail template vs guide execution, resource map resolution, and decomposer integration.
  - **Approval & Async Patterns** – Capture plan approvals, deferred async execution, and webhook callbacks.
  - **Resilience Integration** – Outline error classification, retry strategies, and circuit breaker configuration.
- **Services & Integrations** – Central hub for runtime service adapters and external integration layers.
  - **OneLLM Provider Abstraction** – Describe model configuration, capability checks, and failover behavior.
  - **MCP Tooling Layer** – Explain server registration, transport modes, security, and developer ergonomics.
  - **A2A Collaboration** – Document protocol flow, discovery, authentication, and cross-formation delegation.
  - **Scheduler & Proactive Tasks** – Detail natural language scheduling, audit trails, and async execution surfaces.
  - **Multimodal Pipeline** – Outline ingestion, processing, and routing of non-text modalities.
  - **Observability Stack** – Summarize event streaming, metrics, tracing, and integration points.
  - **Secrets & Compliance Services** – Highlight credential management, RBAC hooks, and compliance controls.
- **Runtime Embedding Guide** – Direct integration patterns for embedding MUXI into existing Python applications.
  - **Embedding Patterns** – Service wrapper patterns, agent pool integration, and formation-as-library approaches.
  - **Custom Agent Development** – Building domain-specific agents, capability registration, and tool integration patterns.
  - **Custom Service Integration** – Extending the services layer, middleware hooks, and plugin architecture.
  - **Memory System Customization** – Custom memory providers, storage backends, and retrieval strategies.
  - **Observability Integration** – Connecting to existing monitoring systems, custom event handlers, and metrics export.
  - **Runtime Lifecycle Management** – Startup/shutdown patterns, configuration management, and graceful degradation.
- **API & Automation** – Reference surface for programmatic control of the runtime and automation workflows.
  - **Formation REST API** – Document implemented endpoints, envelopes, authentication, and versioning (for users/contributors).
  - **Library Embedding** – Focus on direct Python integration, async patterns, and embedding MUXI Runtime as a component in existing applications.
  - **Async & Webhook Flows** – Explain background jobs, status polling, and webhook payload formats.
  - **Future SDKs & CLI Hooks** – Reserve space for upcoming server wrapper/SDK documentation and integration guidance.
  - **Scripting & Embedding** – Provide examples for embedding the runtime in Python applications and automation scripts.
- **Operations & Playbooks** – Practical guidance for running MUXI Runtime in different environments.
  - **Request Lifecycle Runbook** – Walk through end-to-end processing with checkpoints for debugging.
  - **Deployment & Packaging** – Cover Docker/Kubernetes patterns, secrets distribution, and infrastructure prerequisites.
  - **Scaling & Performance** – Offer profiling tips, caching strategies, and configuration tuning with emphasis on async I/O and resource limits.
  - **Troubleshooting Guides** – Centralize known issues, error catalog, and diagnostic checklists.
  - **Observability Runbooks** – Show how to consume logs, metrics, and traces during incidents.
- **Testing & Validation** – Comprehensive testing strategies and validation approaches for contributors and embedders.
  - **Test Philosophy** – Cover no-mocks policy, real integrations, deterministic data, and test organization by feature days.
  - **Test Suite Structure** – Explain `tests/`, `e2e/`, fixtures, and how to add coverage with the test-runner sub-agent.
  - **Debugging & Profiling** – Tools and techniques for performance monitoring, memory analysis, and issue reproduction.
  - **Validation Checklists** – Pre-deployment validation, integration testing, and production readiness verification.
- **Performance Engineering** – Production optimization and troubleshooting for complex, async, multi-agent systems.
  - **Memory Performance Profiling** – Tools and techniques for memory optimization, cache analysis, and bottleneck identification.
  - **Agent Coordination Bottlenecks** – Identifying and resolving orchestration issues, routing delays, and resource contention.
  - **LLM Provider Optimization** – Failover tuning, cost optimization, latency reduction, and request batching strategies.
  - **Testing Complex Flows** – Formation loading, agent coordination, memory consistency, and end-to-end workflow validation.
  - **Production Debugging Runbooks** – Systematic troubleshooting for complex scenarios, performance regression analysis.
  - **Scaling Strategies** – Horizontal scaling patterns, load distribution, and resource allocation optimization.
- **Security Architecture Deep-Dive** – Enterprise-grade security implementation and compliance frameworks.
  - **Multi-User Isolation Mechanics** – How Memobase partitioning actually works, data segregation, and security boundaries.
  - **Agent Permission Models** – Security boundaries between agents and formations, capability-based access control.
  - **MCP Server Sandboxing** – Security isolation for external tool integrations, permission escalation prevention.
  - **Credential Management Internals** – Secrets handling, rotation strategies, scoping mechanisms, and audit trails.
  - **Audit Trail Implementation** – Compliance logging, chain-of-thought preservation, and regulatory requirement mapping.
  - **Zero Trust Integration** – Integration patterns with zero trust architectures and identity providers.
- **Evolution & Migration** – Handling change in production systems without losing context or breaking functionality.
  - **Formation Schema Migration** – Upgrading formation formats without downtime, backward compatibility strategies.
  - **Runtime Version Compatibility** – Managing runtime upgrades, API versioning, and feature flag management.
  - **Memory System Migration** – Migrating between memory backends, data format evolution, and zero-downtime transitions.
  - **Agent Hot-Swapping** – Updating agents without losing context, capability migration, and rollback procedures.
  - **Configuration Evolution** – Managing configuration changes, validation strategies, and rollout procedures.
- **Contributor Handbook** – Onboarding and standards for contributors extending the runtime.
  - **Contribution Workflow** – Outline branching, review expectations (CodeRabbit), and PR hygiene.
  - **Coding & Testing Standards** – Capture lint/format requirements, async patterns, and testing philosophy.
  - **Module Onboarding Guides** – Provide "start here" guides for formation engine, overlord, services, and workflow subsystems.
  - **Test Suite Map** – Explain test directory organization, fixture strategy, and how to add coverage.
  - **Documentation Requirements** – State expectations for updating docs, ADRs, and changelog entries.
- **Examples & Recipes** – Scenario-driven guides and runnable walkthroughs.
  - **Quickstart Formations** – Provide annotated formation examples for common agent setups.
  - **Agent Collaboration Patterns** – Showcase multi-agent orchestration, tool chaining, and A2A usage.
  - **Scheduler Scenarios** – Walk through creating recurring jobs, reminders, and proactive workflows.
  - **Embedding Cookbook** – Share code snippets for integrating runtime features into external Python services, with emphasis on library usage patterns.
  - **End-to-End Tutorials** – Link to full-stack demos combining formations, workflows, and services.
- **Architecture Decisions** – Chronicle the evolution of the runtime and justify major changes.
  - **ADR Index** – Maintain a list of decision records with summaries and status.
  - **Change Timeline** – Highlight landmark updates (clarification overhaul, SOP relocation, resilience integration).
  - **Future Considerations** – Track queued architectural work, open questions, and experimental ideas.

---

## 📁 Documentation Directory Structure

This section shows how the documentation would be organized on disk, with clear mapping between sitemap sections and actual files. The structure maximizes reuse of existing high-quality documentation while providing a cohesive user experience.

```
docs/
├── README.md                          # Main documentation index (167 lines)
│   └── Links to major sections and quick start guides
│
├── landing/
│   ├── README.md                      # Landing & Orientation (NEW)
│   ├── who-is-this-for.md             # Contributor personas and expectations (NEW)
│   ├── runtime-glance.md              # Architecture overview with diagrams (NEW)
│   ├── terminology.md                 # Critical terms and vocabulary (NEW)
│   └── navigation-map.md              # Reading paths for different audiences (NEW)
│
├── formation-fundamentals/
│   ├── README.md                      # Formation Fundamentals index (NEW)
│   ├── initialization-pipeline.md     # Loading order and failure modes (NEW)
│   ├── secrets-credentials.md         # Secret handling and rotation (NEW)
│   ├── loader-internals.md            # Formation parsing and hooks (NEW)
│   └── formation-library.md           # Examples from test-formations/ (NEW)
│
├── core-systems/
│   ├── README.md                      # Core Systems index (NEW)
│   ├── formation-engine.md            # Engine internals and validation (NEW)
│   ├── overlord-loop.md               # _process_sync_chat and routing (NEW)
│   ├── agent-pool.md                  # Agent lifecycle and execution (NEW)
│   └── services-layer.md              # Shared services overview (NEW)
│
├── memory-architecture/
│   ├── README.md                      # Memory Architecture index (NEW)
│   ├── three-tier-deep-dive.md         # Buffer→Persistent→Vector details (NEW)
│   ├── context-preservation.md         # Session and agent handoff continuity (NEW)
│   ├── intelligent-cleanup.md          # FIFO rules and optimization (NEW)
│   ├── multi-user-isolation.md        # Memobase partitioning mechanics (NEW)
│   ├── performance-tuning.md          # Configuration and monitoring (NEW)
│   └── migration-guide.md             # Backend migration strategies (NEW)
│
├── workflow-orchestration/
│   ├── README.md                      # Workflow & Orchestration index (NEW)
│   ├── complexity-routing.md          # Scoring methods and thresholds (NEW)
│   ├── sop-system.md                  # Template vs guide execution (NEW)
│   ├── approval-patterns.md            # Async and approval workflows (NEW)
│   └── resilience-integration.md      # Error recovery and circuit breakers (NEW)
│
├── services-integrations/
│   ├── README.md                      # Services & Integrations index (NEW)
│   ├── onellm-abstraction.md           # Provider-agnostic LLM interface (NEW)
│   ├── mcp-tooling.md                  # Server registration and transports (NEW)
│   ├── a2a-collaboration.md            # Protocol flow and delegation (NEW)
│   ├── scheduler-tasks.md              # Natural language scheduling (NEW)
│   ├── multimodal-pipeline.md          # Non-text content processing (NEW)
│   ├── observability-stack.md          # Event streaming and metrics (NEW)
│   └── secrets-compliance.md           # Credential management (NEW)
│
├── runtime-embedding/
│   ├── README.md                      # Runtime Embedding Guide index (NEW)
│   ├── embedding-patterns.md          # Service wrapper and integration (NEW)
│   ├── custom-agents.md               # Domain-specific agent development (NEW)
│   ├── service-integration.md         # Middleware hooks and plugins (NEW)
│   ├── memory-customization.md        # Custom storage backends (NEW)
│   ├── observability-integration.md    # External monitoring systems (NEW)
│   └── lifecycle-management.md         # Startup/shutdown patterns (NEW)
│
├── api-automation/
│   ├── README.md                      # API & Automation index (NEW)
│   ├── formation-rest-api.md          # REST endpoints and authentication (NEW)
│   ├── library-embedding.md            # Direct Python integration (NEW)
│   ├── async-webhooks.md               # Background jobs and notifications (NEW)
│   ├── sdks-cli-hooks.md               # Future SDKs and CLI integration (NEW)
│   └── scripting-examples.md           # Embedding and automation scripts (NEW)
│
├── operations-playbooks/
│   ├── README.md                      # Operations & Playbooks index (NEW)
│   ├── request-lifecycle-runbook.md    # End-to-end processing checkpoints (NEW)
│   ├── deployment-packaging.md         # Docker/Kubernetes patterns (NEW)
│   ├── scaling-performance.md         # Profiling and resource optimization (NEW)
│   ├── troubleshooting-guides.md       # Known issues and diagnostics (NEW)
│   └── observability-runbooks.md       # Logs, metrics, and incident response (NEW)
│
├── testing-validation/
│   ├── README.md                      # Testing & Validation index (NEW)
│   ├── test-philosophy.md              # No-mocks policy and real integrations (NEW)
│   ├── test-suite-structure.md        # tests/, e2e/, fixtures organization (NEW)
│   ├── debugging-profiling.md          # Performance monitoring tools (NEW)
│   └── validation-checklists.md        # Pre-deployment verification (NEW)
│
├── performance-engineering/
│   ├── README.md                      # Performance Engineering index (NEW)
│   ├── memory-profiling.md             # Memory optimization and analysis (NEW)
│   ├── coordination-bottlenecks.md     # Orchestration performance issues (NEW)
│   ├── llm-optimization.md             # Provider failover and cost reduction (NEW)
│   ├── complex-flow-testing.md        # Workflow and integration testing (NEW)
│   ├── production-debugging.md        # Systematic troubleshooting (NEW)
│   └── scaling-strategies.md           # Load distribution and scaling (NEW)
│
├── security-architecture/
│   ├── README.md                      # Security Architecture index (NEW)
│   ├── multi-user-isolation.md        # Memobase partitioning security (NEW)
│   ├── agent-permissions.md           # Capability-based access control (NEW)
│   ├── mcp-sandboxing.md               # External tool integration security (NEW)
│   ├── credential-management.md       # Secrets handling and audit trails (NEW)
│   ├── audit-trails.md                 # Compliance logging and tracing (NEW)
│   └── zero-trust-integration.md       # Identity provider integration (NEW)
│
├── evolution-migration/
│   ├── README.md                      # Evolution & Migration index (NEW)
│   ├── formation-schema-migration.md  # Format upgrades and compatibility (NEW)
│   ├── runtime-compatibility.md        # Version management and flags (NEW)
│   ├── memory-migration.md            # Backend transitions (NEW)
│   ├── agent-hot-swapping.md          # Context-preserving updates (NEW)
│   └── configuration-evolution.md      # Change management procedures (NEW)
│
├── contributor-handbook/
│   ├── README.md                      # Contributor Handbook index (NEW)
│   ├── contribution-workflow.md        # Branching and PR processes (NEW)
│   ├── coding-standards.md            # Lint, format, and async patterns (NEW)
│   ├── module-onboarding.md            # Subsystem entry points (NEW)
│   ├── test-suite-map.md              # Testing organization and fixtures (NEW)
│   └── documentation-requirements.md   # Docs, ADRs, and changelog updates (NEW)
│
├── examples-recipes/
│   ├── README.md                      # Examples & Recipes index (NEW)
│   ├── quickstart-formations.md        # Annotated formation examples (NEW)
│   ├── agent-collaboration.md          # Multi-agent orchestration (EXISTING)
│   ├── scheduler-scenarios.md          # Proactive task examples (NEW)
│   ├── embedding-cookbook.md           # Library integration patterns (NEW)
│   └── end-to-end-tutorials.md         # Full-stack demonstrations (NEW)
│
├── architecture-decisions/
│   ├── README.md                      # Architecture Decisions index (NEW)
│   ├── adr-index.md                   # Decision records and status (NEW)
│   ├── change-timeline.md             # Major updates and evolution (NEW)
│   └── future-considerations.md       # Queued work and open questions (NEW)
│
└── _includes/                         # Shared content and templates
    ├── cross-references.md            # Links to related sections (NEW)
    ├── glossary.md                    # Terminology definitions (NEW)
    └── navigation-aids.md             # Reading paths and quick links (NEW)
```

### 🔗 **Existing Documentation Integration Strategy**

**Direct Reuse (80% of content)**:
- `clarification-system.md` → Core Systems > Overlord Core Loop
- `memory-systems.md` → Memory Architecture & Intelligence (primary source)
- `multi-user-architecture.md` → Memory Architecture > Multi-User Isolation
- `request-lifecycle.md` → Operations & Playbooks > Request Lifecycle Runbook
- `workflow/` directory (8 files) → Workflow & Orchestration (complete)
- `a2a/` directory (10 files) → Services & Integrations > A2A Collaboration
- `scheduler/` directory (7 files) → Services & Integrations > Scheduler & Proactive Tasks
- `mcp/` directory (4 files) → Services & Integrations > MCP Tooling Layer
- `api/` directory → API & Automation > Formation REST API
- `observability.md` → Services & Integrations > Observability Stack
- `agent-collaboration.md` → Examples & Recipes > Agent Collaboration Patterns
- `agent-tool-chaining.md` → Examples & Recipes > Agent Collaboration Patterns

**Context Integration**:
- `.claude/context/project-brief.md` → Formation Fundamentals & Core Systems
- `.claude/context/system-patterns.md` → Core Systems & Architecture Decisions
- `.claude/context/project-structure.md` → Core Systems > Services Layer Overview
- `.claude/context/tech-context.md` → Architecture Decisions

**Schema Documentation**:
- `schemas/formation/README.md` → Formation Fundamentals (primary source, 1654 lines)
- Formation schema validation and configuration reference

**New Content Needed (20%)**:
- Runtime embedding guides and cookbook
- Performance engineering and optimization
- Security architecture deep-dives
- Testing and validation strategies
- Migration and evolution guides

### 🎯 **Content Strategy Benefits**

1. **🚀 80% Faster Development**: Reuse 40+ existing high-quality files
2. **📚 Consistent Quality**: All reused docs are comprehensive and well-written
3. **🔗 Cohesive Navigation**: Cross-references create unified user experience
4. **⚡ Minimal Duplication**: No rewriting of well-documented areas
5. **🎯 Focused Effort**: 20% new content for missing areas like embedding and performance

- **Versioning & Release Management** – Understand how MUXI Runtime uses ScalVer with fixed YYYYMMDD format for maximum clarity and SemVer compatibility.
  - **ScalVer Overview** – Calendar-aware versioning scheme (MAJOR.YYYYMMDD.PATCH) with precise release dating
  - **Fixed Date Format** – Why MUXI uses consistent 8-digit dates for crystal-clear release dating
  - **Same-Day Principle** – Understanding that multiple releases on the same date are always patches, never features
  - **Compatibility** – Full SemVer compatibility ensures existing tooling works without modification
  - **Migration Guide** – How to transition from SemVer to fixed YYYYMMDD ScalVer format
  - **Release Planning** – Best practices for choosing release dates and managing patch cycles
  - **Pre-release & Metadata** – Handling alpha/beta releases and build metadata with ScalVer

This structure provides a comprehensive, professional documentation site that serves contributors, embedders, and users while maximizing reuse of existing high-quality documentation.

