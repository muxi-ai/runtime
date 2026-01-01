# MUXI Website - OSS-First Launch Structure

*This document outlines the OSS-first website structure for muxi.org at launch*

## 🎯 **OSS-First Strategy**

**Goal**: Maximize developer adoption and community growth before introducing commercial offerings.

**Domain**: `muxi.org` (emphasizes open-source, non-profit nature)

**Focus**: Developer experience, community building, technical excellence

## 🌐 **OSS-First Site Structure**

### **Root Path (`/`) - Developer & Community Focused**
*For developers discovering and adopting MUXI*

```
muxi.org/
├── index.html                 # "Open-source runtime for AI agents"
├── docs/                      # All technical documentation (see runtime-sitemap.md & full-sitemap.md)
├── examples/                  # Showcase gallery → /docs/cookbooks/
├── community/                 # Discord, GitHub, contributions
├── blog/                      # Technical content, updates, tutorials
├── registry/                  # Formation & MCP marketplace (future)
├── about/                     # Project mission, team, open source philosophy
└── github/                    # → Redirect to GitHub repo
```

## 🚀 **Developer-First Homepage**

### **Hero Section**
```html
🤖 The Open-Source Runtime for AI Agents
Deploy intelligent systems as easily as Docker containers

[Get Started in 5 Minutes] [View Examples] [⭐ Star on GitHub]

curl -fsSL https://muxi.org/install | sh
muxi new my-agent && muxi dev
```

### **Value Props (Developer-Focused)**
```
✅ Self-hostable & open source
✅ Formation-as-code (YAML configuration)
✅ 1000+ MCP tools ecosystem
✅ Multi-agent orchestration
✅ Production-ready from day one
✅ Active community support
```

### **Progressive Learning Path**
```
Get productive in minutes:

⚡ 5 minutes: Your First Agent
   Create a basic formation, deploy locally
   [Try Now →] /docs/learn/01-basic-formation/

🔧 15 minutes: Add Superpowers
   Connect tools, add memory, enhance capabilities
   [Learn More →] /docs/learn/02-add-tools/

🤝 30 minutes: Multi-Agent Teams
   Orchestrate multiple agents, complex workflows
   [See Recipe →] /docs/cookbooks/system-recipes/

🏗️ 60 minutes: Production Ready
   Deploy, monitor, scale your AI systems
   [Deploy Guide →] /docs/learn/04-production/
```

## 📋 **OSS-First Navigation**

### **Primary Nav**
```
Docs | Examples | Community | Blog | About
```

### **Docs Dropdown**
```
Docs ▼
├── 🚀 Get Started         → /docs/learn/
├── 📖 Cookbooks          → /docs/cookbooks/
├── 🔧 API Reference      → /docs/api/
├── 📝 Formation Guide    → /docs/formations/
├── ⚡ CLI Reference      → /docs/cli/
├── 🤝 Contributing       → /docs/runtime/contributor-handbook/
└── 🏗️ Runtime Internals → /docs/runtime/
```

### **Examples Dropdown**
```
Examples ▼
├── 🤖 Agent Recipes      → /docs/cookbooks/agent-recipes/
├── 🔧 System Recipes     → /docs/cookbooks/system-recipes/
├── 🔗 Integration Patterns → /docs/cookbooks/integration-recipes/
├── 🎯 Use Case Demos     → /examples/demos/
└── 🖼️ Showcase Gallery  → /examples/
```

### **Community Dropdown**
```
Community ▼
├── 💬 Discord            → /community/discord/
├── 🐙 GitHub            → /community/github/
├── 📝 Contributing      → /docs/runtime/contributor-handbook/
├── 🎪 Events            → /community/events/
├── 🌟 Showcase          → /community/showcase/
└── 🚀 Roadmap           → /about/roadmap/
```

## 🌟 **OSS-Specific Pages**

### **Examples (`/examples/`)**
```
/examples/
├── index.html              # Gallery of working examples
├── demos/                  # Live interactive demos
│   ├── customer-support/   # Live demo + formation YAML
│   ├── research-assistant/ # Live demo + formation YAML
│   ├── content-creator/    # Live demo + formation YAML
│   └── multi-agent-team/   # Live demo + formation YAML
├── formations/             # Community formation library
│   ├── popular/            # Most starred formations
│   ├── recent/             # Recently added
│   └── categories/         # By use case/industry
└── tutorials/              # Step-by-step build guides
```

### **Community (`/community/`)**
```
/community/
├── index.html              # Community hub and stats
├── discord/                # → Discord invite + preview
├── github/                 # → GitHub repo + contribution stats
├── contributing/           # → /docs/runtime/contributor-handbook/
├── events/                 # Meetups, conferences, webinars
├── showcase/               # Community formations and success stories
├── blog/                   # → /blog/ (community posts)
└── code-of-conduct/        # Community guidelines
```

### **About (`/about/`)**
```
/about/
├── index.html              # Project mission and philosophy
├── team/                   # Core contributors and maintainers
├── roadmap/                # Public development roadmap
├── governance/             # Project governance model
├── license/                # Elastic License 2.0 details
├── sponsors/               # Sponsors and supporters
├── press/                  # Press kit and media resources
└── contact/                # Non-commercial contact info
```

### **Blog (`/blog/`)**
```
/blog/
├── index.html              # Latest posts
├── tutorials/              # Technical tutorials
├── releases/               # Release announcements
├── community/              # Community spotlights
├── architecture/           # Deep technical dives
├── contributors/           # Contributor stories
└── [year]/[month]/[slug]/  # Individual blog posts
```

## 🎯 **Key Messaging (OSS-Focused)**

### **Primary Messages**
```
✅ "Open-source runtime for AI agents"
✅ "Self-hostable and community-driven"
✅ "Formation-as-code simplicity"
✅ "Production-ready from day one"
✅ "Join 10k+ developers building with MUXI"
```

### **Community-Driven CTAs**
```
Primary: [Get Started] [⭐ Star on GitHub]
Secondary: [Join Discord] [Read Docs] [View Examples]
Tertiary: [Contribute] [Share Formation] [Report Issue]
```

### **Avoid Commercial Language**
```
❌ "Enterprise-grade"     → ✅ "Production-ready"
❌ "Trusted by companies" → ✅ "Used by developers"
❌ "Contact sales"        → ✅ "Join community"
❌ "Pricing plans"        → ✅ "Always free"
❌ "Business solutions"   → ✅ "Developer tools"
```

## 📊 **OSS Homepage Layout**

```html
Header:
[🤖 MUXI] Docs | Examples | Community | Blog | About [⭐ GitHub]

Hero:
🤖 The Open-Source Runtime for AI Agents
Self-hostable, formation-based, production-ready

Deploy intelligent systems as easily as Docker containers

[Get Started in 5 Minutes] [⭐ Star on GitHub] [💬 Join Discord]

Quick Start:
curl -fsSL https://muxi.org/install | sh
muxi new my-agent && muxi dev
[📋 Copy] [📖 Full Guide]

Progressive Learning:
⚡ 5 min: Your first agent     [Try Now →]
🔧 15 min: Add superpowers     [Learn More →]
🤝 30 min: Multi-agent teams   [See Recipe →]
🏗️ 60 min: Production ready   [Deploy Guide →]

Why Choose MUXI:
📝 Formation-as-Code         🔧 1000+ MCP Tools        🤝 Multi-Agent Ready
🧠 Intelligent Memory       ⚡ Self-Hostable          🔒 Production-Grade
🌍 Active Community         📖 Rich Documentation     🚀 Rapid Development

Community Highlights:
⭐ 15.2k GitHub Stars       👥 5.8k Discord Members    📦 2.1k Formations Shared
🔧 847 Contributors        📝 1.2k Community Posts    🚀 Weekly Releases

Featured Examples:
[Customer Support Bot]  [Research Assistant]  [Content Creator]  [Multi-Agent Team]
[View All Examples →]

Getting Started:
1️⃣ Install MUXI CLI       → curl -fsSL muxi.org/install | sh
2️⃣ Create your formation  → muxi new my-agent
3️⃣ Deploy locally         → muxi dev
4️⃣ Share with community   → muxi push

[🚀 Start Building] [📖 Read Docs] [💬 Get Help]

Footer:
📖 Docs | 🎯 Examples | 💬 Community | 📝 Blog | ℹ️ About
🐙 GitHub | 💬 Discord | 🐦 Twitter | 📧 Newsletter
📄 License: Elastic 2.0 | 🔒 Privacy | 📋 Code of Conduct
```

## 🔄 **Future Evolution Strategy**

### **Phase 1: Pure OSS (Launch)**
- Focus: Developer adoption, community growth
- Metrics: GitHub stars, Discord members, formations shared
- Revenue: None (focus on adoption)

### **Phase 2: Hybrid OSS + Commercial Hints**
- Add: `/cloud/` section (coming soon)
- Add: Enterprise contact form
- Maintain: Developer-first messaging
- Metrics: Same + enterprise inquiries

### **Phase 3: Commercial Split**
- Launch: muxi.com (commercial)
- Keep: muxi.org (pure OSS)
- Strategy: Two-site approach

## 🎨 **OSS Brand Identity**

### **Visual Style**
- **Colors**: Developer-friendly palette (dark mode first)
- **Typography**: Monospace accents, clean sans-serif
- **Icons**: Open-source friendly, technical aesthetic
- **Layout**: Code-focused, terminal-inspired elements

### **Tone & Voice**
- **Technical**: Precise, accurate, no marketing fluff
- **Welcoming**: Inclusive, beginner-friendly guidance
- **Community**: Collaborative, contribution-focused
- **Authentic**: Honest about limitations and roadmap

### **Content Strategy**
- **Tutorials**: Step-by-step, copy-pasteable
- **Examples**: Real-world, production-ready
- **Documentation**: Comprehensive, searchable
- **Community**: User-generated content, showcases

This OSS-first structure maximizes developer adoption while building a strong foundation for future commercial success! 🌟
