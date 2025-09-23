# MUXI Documentation Site - Complete Sitemap

This document outlines the complete documentation strategy for the MUXI ecosystem, covering both **public documentation** (for MUXI Server + CLI/SDK users) and **runtime internals** documentation (for contributors and embedders).

## 🎯 **Two-Tier Documentation Strategy**

### **Tier 1: Public Documentation** (`muxi.org/docs`)
*For the "mass public" using MUXI Server + CLI/SDK*

**Target Audience:**
- Developers building AI systems with formations
- Teams deploying AI agents to production
- Companies integrating AI into their workflows

**Focus:** Getting things done with MUXI tools

### **Tier 2: Runtime Internals** (`muxi.org/docs/runtime/`)
*For contributors, embedders, and deep customization*

**Target Audience:**
- Contributors to MUXI Runtime
- Developers embedding MUXI Runtime in their applications
- Engineers who need to understand the engine internals

**Focus:** How MUXI works under the hood

---

## 🚀 **Public Documentation Structure**

### **Progressive Learning Path: Layer by Layer**

The core philosophy is **progressive complexity** - each layer builds on the previous one, with clear time investments and outcomes.

#### **⚡ Quick Win Path (25 minutes total)**
*"From zero to working AI system with real capabilities"*

**Layer 1: Basic Formation (5 minutes)**
```
/learn/01-basic-formation/
├── README.md               # "Your first AI agent in 5 minutes"
├── installation.md         # CLI installation and setup
├── first-formation.md      # muxi new walkthrough
├── agent-basics.md         # Understanding agents and system messages
└── see-it-live.md          # muxi dev and web interface
```

**Layer 2: Add Tools (10 minutes)**
```
/learn/02-add-tools/
├── README.md               # "Give your agent superpowers"
├── mcp-overview.md         # What are MCP servers?
├── web-search.md           # Adding web search capability
├── file-operations.md      # File system tools
└── tool-discovery.md       # Finding and using community tools
```

**Layer 3: Add Memory (10 minutes)**
```
/learn/03-add-memory/
├── README.md               # "Conversations that remember"
├── buffer-memory.md        # Short-term conversation context
├── persistent-memory.md    # Long-term memory across sessions
├── vector-search.md        # Semantic memory capabilities
└── memory-configuration.md # Tuning memory settings
```

#### **🏢 Production Path (40 minutes total)**
*"Scale to teams and production deployment"*

**Layer 4: Multiple Users (15 minutes)**
```
/learn/04-multiple-users/
├── README.md              # "Scale to teams and customers"
├── multi-tenant.md        # User isolation and security
├── api-keys.md            # Authentication and access control
├── user-credentials.md    # Per-user credential management
└── security-basics.md     # Security best practices
```

**Layer 5: Agent Collaboration (15 minutes)**
```
/learn/05-agent-collaboration/
├── README.md              # "Agents working together"
├── multi-agent-basics.md  # Creating specialized agents
├── agent-routing.md       # How requests get routed
├── a2a-communication.md   # Agent-to-agent messaging
└── workflow-patterns.md   # Common collaboration patterns
```

**Layer 6: Observability (10 minutes)**
```
/learn/06-observability/
├── README.md              # "See what's happening"
├── logging-setup.md       # Event streaming and logs
├── monitoring.md          # Health checks and metrics
├── debugging.md           # Troubleshooting agent behavior
└── performance.md         # Performance monitoring
```

#### **🌐 Ecosystem Path (30 minutes total)**
*"Join the community and scale infrastructure"*

**Layer 7: Registry & Sharing (15 minutes)**
```
/learn/07-registry-sharing/
├── README.md              # "Join the AI ecosystem"
├── muxi-push-pull.md      # Publishing and using formations
├── community-agents.md    # Discovering community agents
├── sharing-mcp.md         # Publishing MCP servers
└── best-practices.md      # Registry best practices
```

**Layer 8: Multiple Formations (15 minutes)**
```
/learn/08-multiple-formations/
├── README.md              # "Enterprise-scale AI infrastructure"
├── server-management.md   # Running multiple formations
├── resource-allocation.md # Managing server resources
├── formation-lifecycle.md # Deployment and updates
└── scaling-patterns.md    # Horizontal scaling strategies
```

#### **🎨 Advanced Path (30 minutes)**
*"Custom applications and integrations"*

**Layer 9: SDK & Custom UX (30 minutes)**
```
/learn/09-sdk-custom-ux/
├── README.md               # "Build custom AI applications"
├── python-sdk.md           # Python SDK integration
├── javascript-sdk.md       # JavaScript/TypeScript SDK
├── rest-api.md             # Direct API integration
├── custom-interfaces.md    # Building custom UIs
└── integration-patterns.md # Common integration scenarios
```

### **Reference Documentation**

#### **Formation Development**
```
/formations/
├── README.md             # Formation development guide
├── schema-reference.md   # Complete YAML reference
├── agents/               # Agent configuration guide
├── memory-systems.md     # Memory configuration
├── mcp-integration.md    # MCP server setup
├── secrets-management.md # Environment variables and secrets
├── scheduling.md         # Proactive AI and scheduling
└── advanced-features.md  # SOPs, workflows, resilience
```

#### **CLI Reference**
```
/cli/
├── README.md               # CLI overview and installation
├── commands.md             # Complete command reference
├── formation-management.md # push, pull, start, stop
├── server-management.md    # Server operations
├── debugging.md            # CLI debugging tools
└── configuration.md        # CLI configuration
```

#### **Server Operations**
```
/server/
├── README.md               # MUXI Server overview
├── installation.md         # Installation and setup
├── configuration.md        # Server configuration
├── deployment.md           # Production deployment
├── monitoring.md           # Monitoring and health checks
├── security.md             # Security configuration
└── scaling.md              # Scaling and load balancing
```

#### **SDK Documentation**
```
/sdks/
├── README.md               # SDK ecosystem overview
├── python/                 # Python SDK complete reference
├── javascript/             # JavaScript/TypeScript SDK
├── go/                     # Go SDK (future)
├── rest-api.md             # REST API reference
└── webhooks.md             # Webhook integration
```

### **Examples & Use Cases**
```
/examples/
├── README.md             # Example gallery and use cases
├── chatbots/             # Customer service, support bots
├── automation/           # Workflow automation examples
├── data-processing/      # Document analysis, extraction
├── multi-agent/          # Complex coordination examples
├── integrations/         # CRM, database, API integrations
└── custom-applications/  # Custom UI and application examples
```

### **Concepts & Architecture**
```
/concepts/
├── README.md             # High-level architecture overview
├── formations.md         # What are formations?
├── agents.md             # Agent capabilities and roles
├── memory.md             # Memory systems (user perspective)
├── tools-mcp.md          # MCP ecosystem and tools
├── scheduling.md         # Proactive AI capabilities
├── security.md           # Security model overview
└── versioning.md         # ScalVer versioning explained
```

---

## ⚙️ **Runtime Internals Documentation Structure**

*For contributors and embedders - detailed in separate runtime-sitemap.md*

```
/runtime/
├── landing/                   # Orientation for contributors
├── formation-fundamentals/    # Formation loading and initialization
├── core-systems/              # Formation engine, overlord, agents
├── memory-architecture/       # Three-tier memory deep dive
├── workflow-orchestration/    # Task decomposition and SOPs
├── services-integrations/     # MCP, A2A, scheduler, observability
├── runtime-embedding/         # Library integration patterns
├── api-automation/            # Formation API and automation
├── operations-playbooks/      # Production operations
├── testing-validation/        # Testing strategies
├── performance-engineering/   # Optimization and scaling
├── security-architecture/     # Security deep dives
├── evolution-migration/       # System evolution guides
├── versioning/                # ScalVer implementation details
├── contributor-handbook/      # Contribution guidelines
├── examples-recipes/          # Code examples and patterns
└── architecture-decisions/    # ADRs and evolution timeline
```

---

## 🎯 **Homepage Learning Flow**

### **Progressive Complexity Cards**

```
┌─────────────────────────────────┐
│ ⚡ Quick Win (25 min)            │
│ Basic Formation + Tools + Memory│
│                                 │
│ ✓ Working AI assistant          │
│ ✓ Web search capabilities       │
│ ✓ Conversation memory           │
│                                 │
│ [Start Building →]              │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ ⌂ Production (40 min)           │
│ Multi-User + Collaboration      │
│                                 │
│ ✓ Serve multiple users          │
│ ✓ Agent collaboration           │
│ ✓ Full observability            │
│                                 │
│ [Scale Up →]                    │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ ❉ Ecosystem (30 min)            │
│ Registry + Community + Scale    │
│                                 │
│ ✓ Publish to registry           │
│ ✓ Multiple formations           │
│ ✓ Community participation       │
│                                 │
│ [Join Ecosystem →]              │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ ✎ Advanced (30 min)             │
│ SDK + Custom UX + Integration   │
│                                 │
│ ✓ Custom applications           │
│ ✓ SDK integration               │
│ ✓ Unique experiences            │
│                                 │
│ [Get Creative →]                │
└─────────────────────────────────┘
```

### **Hero Section**
```
🤖 The Docker for AI Agents
Deploy intelligent systems as easily as websites

From zero to production AI in 2 hours
├── ⚡ 25 min: Working AI with tools & memory
├── 🏢 40 min: Multi-user production system
├── 🌐 30 min: Community ecosystem participation
└── 🎨 30 min: Custom applications & integrations

[Get Started in 5 Minutes] [View Examples] [Read Docs]
```

## 🎯 **Content Strategy Principles**

### **1. Progressive Disclosure**
- Each layer builds on the previous
- Clear time investment and outcomes
- Multiple "graduation moments"
- Users can stop at any layer and have value

### **2. Example-Driven Learning**
- Every concept has runnable code
- Real formation YAML examples
- Expected outputs and behaviors
- Links to complete working examples

### **3. Clear Separation of Concerns**
- **Public docs**: "How to use MUXI" (formations, CLI, deployment)
- **Internals docs**: "How MUXI works" (runtime, overlord, memory)
- **No overlap or confusion** between the two

### **4. Community-Focused**
- Registry and sharing as core features
- Community examples and patterns
- Contribution pathways clearly marked
- Open ecosystem participation

### **5. Production-Ready Focus**
- Security, monitoring, and scaling from early layers
- Real-world deployment scenarios
- Enterprise concerns addressed
- Performance and reliability guidance

---

## 📊 **Success Metrics**

### **Learning Path Completion**
- **Layer 1-3 (25 min)**: "Quick Win" - working AI system
- **Layer 4-6 (40 min)**: "Production Ready" - multi-user system
- **Layer 7-8 (30 min)**: "Ecosystem Participant" - community member
- **Layer 9 (30 min)**: "Advanced Builder" - custom applications

### **User Journey Tracking**
- Time to first working formation
- Progression through learning layers
- Registry participation (push/pull)
- Community contributions

### **Content Effectiveness**
- Tutorial completion rates
- Example usage patterns
- Support question categories
- Feature adoption metrics

This structure creates a comprehensive, user-friendly documentation experience that scales from "hello world" to production deployment while maintaining clear separation between user-focused and contributor-focused content.
