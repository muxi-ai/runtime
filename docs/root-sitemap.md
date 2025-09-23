# MUXI Website - Future Commercial Structure

*This document outlines the planned commercial website structure for when MUXI evolves beyond pure OSS*

## 🎯 **Strategic Evolution Path**

```
Phase 1: OSS-first (muxi.org)           → Pure developer adoption
Phase 2: Hybrid (muxi.org + /cloud/)    → Introduce commercial offerings
Phase 3: Split (muxi.com + muxi.org)    → Full commercial + OSS separation
```

## 🌐 **Future Commercial Site Structure**

### **Root Path (`/`) - Business & Marketing Focused**
*For decision makers, enterprises, and commercial users*

```
muxi.com/
├── index.html                 # "The Vercel for AI Deployments"
├── pricing/                   # Commercial plans and pricing
├── enterprise/                # Enterprise solutions and support
├── customers/                 # Case studies and testimonials
├── solutions/                 # Industry-specific solutions
├── security/                  # Compliance, SOC2, security docs
├── support/                   # Commercial support and SLA
├── partners/                  # Partner program and integrations
├── company/                   # About, team, investors, press
├── blog/                      # Business-focused content
├── contact/                   # Sales and enterprise contact
├── docs/                      # → Redirect to muxi.org/docs/
└── open-source/               # → Redirect to muxi.org/
```

### **Documentation Path (`/docs/`) - Redirect Strategy**
*All technical documentation remains on muxi.org*

```
muxi.com/docs/ → muxi.org/docs/
```

## 🏢 **Commercial Homepage Structure**

### **Hero Section**
```html
🚀 The Vercel for AI Deployments
Deploy intelligent agents with enterprise-grade reliability

[Start Free Trial] [Book Demo] [View Pricing]

Trusted by 500+ companies worldwide
[Customer logos]
```

### **Value Props (Business-Focused)**
```
✅ Enterprise-grade infrastructure
✅ 99.9% uptime SLA
✅ SOC2 compliant
✅ Global edge deployment
✅ 24/7 expert support
✅ Built on open-source MUXI
```

### **Solutions Section**
```
By Industry:
- Customer Support Automation
- Research & Development
- Content & Marketing
- Sales & Lead Generation

By Use Case:
- Multi-Agent Workflows
- Document Processing
- API Integrations
- Real-time Assistance
```

## 📋 **Commercial Navigation**

### **Primary Nav**
```
Solutions | Pricing | Enterprise | Customers | Docs | Company
```

### **Solutions Dropdown**
```
Solutions ▼
├── By Industry
│   ├── Customer Support    → /solutions/customer-support/
│   ├── R&D Automation     → /solutions/research/
│   ├── Content Marketing  → /solutions/content/
│   └── Sales Enablement   → /solutions/sales/
├── By Use Case
│   ├── Multi-Agent Teams  → /solutions/multi-agent/
│   ├── Document AI        → /solutions/document-ai/
│   ├── API Orchestration  → /solutions/api-orchestration/
│   └── Real-time Support  → /solutions/real-time/
└── View All Solutions     → /solutions/
```

### **Enterprise Dropdown**
```
Enterprise ▼
├── Overview              → /enterprise/
├── Security             → /security/
├── Compliance           → /enterprise/compliance/
├── Support              → /support/
├── Professional Services → /enterprise/services/
└── Contact Sales        → /contact/
```

### **Company Dropdown**
```
Company ▼
├── About               → /company/
├── Team                → /company/team/
├── Careers             → /company/careers/
├── Press               → /company/press/
├── Investors           → /company/investors/
├── Open Source         → https://muxi.org/
└── Contact             → /contact/
```

## 🎯 **Key Commercial Pages**

### **Pricing (`/pricing/`)**
```
/pricing/
├── index.html              # Plans and pricing tiers
├── calculator/             # Cost calculator
├── enterprise/             # Custom enterprise pricing
└── faq/                   # Pricing FAQ
```

### **Enterprise (`/enterprise/`)**
```
/enterprise/
├── index.html              # Enterprise overview
├── security/               # → /security/
├── compliance/             # SOC2, GDPR, HIPAA
├── support/                # → /support/
├── services/               # Professional services
├── onboarding/             # Enterprise onboarding
└── case-studies/           # Enterprise customer stories
```

### **Solutions (`/solutions/`)**
```
/solutions/
├── index.html              # Solutions overview
├── customer-support/       # Industry solution
├── research/               # Industry solution
├── content/                # Industry solution
├── sales/                  # Industry solution
├── multi-agent/            # Use case solution
├── document-ai/            # Use case solution
├── api-orchestration/      # Use case solution
└── real-time/              # Use case solution
```

### **Customers (`/customers/`)**
```
/customers/
├── index.html              # Customer stories overview
├── case-studies/           # Detailed case studies
├── testimonials/           # Customer testimonials
├── logos/                  # Customer logo wall
└── success-stories/        # Success story collection
```

## 🔗 **Cross-Site Linking Strategy**

### **Commercial → OSS**
```
muxi.com/docs/           → muxi.org/docs/
muxi.com/open-source/    → muxi.org/
muxi.com/community/      → muxi.org/community/
muxi.com/github/         → github.com/muxi-ai/runtime
```

### **OSS → Commercial**
```
muxi.org/cloud/          → muxi.com/
muxi.org/enterprise/     → muxi.com/enterprise/
muxi.org/pricing/        → muxi.com/pricing/
```

## 🎨 **Brand Differentiation**

### **muxi.com (Commercial)**
- **Colors**: Professional blues, enterprise grays
- **Tone**: Business-focused, ROI-driven, enterprise-ready
- **CTAs**: "Start Trial", "Book Demo", "Contact Sales"
- **Content**: Case studies, ROI, compliance, SLA

### **muxi.org (OSS)**
- **Colors**: Developer-friendly, vibrant accent colors
- **Tone**: Technical, community-driven, open-source
- **CTAs**: "Get Started", "Star on GitHub", "Join Discord"
- **Content**: Tutorials, examples, community, contributions

## 📊 **Commercial Homepage Layout**

```html
Header: [Logo] Solutions | Pricing | Enterprise | Customers | Docs | Company [Start Trial]

Hero:
  🚀 The Vercel for AI Deployments
  Enterprise-grade infrastructure for intelligent agents
  [Start Free Trial] [Book Demo] [View Pricing]

Social Proof:
  Trusted by 500+ companies
  [Customer logos carousel]

Value Props:
  🏢 Enterprise Ready    ⚡ Global Scale    🔒 SOC2 Compliant
  📞 24/7 Support       💰 Predictable Pricing    🔧 Expert Services

Solutions:
  Transform your business with AI agents
  [Industry Solutions] [Use Case Solutions] [View All →]

Customers:
  "MUXI helped us reduce support tickets by 80%"
  [Customer testimonial carousel]

Pricing Preview:
  Start free, scale as you grow
  [Pricing tiers preview] [View Full Pricing →]

Footer:
  Solutions | Pricing | Enterprise | Support | Legal | muxi.org
```

## 🚀 **Migration Strategy**

### **Phase 1 → 2 Transition**
1. Add `/cloud/` section to muxi.org
2. Introduce pricing page
3. Add enterprise contact forms
4. Maintain developer-first messaging

### **Phase 2 → 3 Transition**
1. Launch muxi.com with full commercial site
2. Keep muxi.org as pure OSS community site
3. Implement cross-site linking strategy
4. Maintain unified documentation on muxi.org

This structure ensures a smooth evolution from OSS-first to full commercial while maintaining developer trust and community engagement! 🌟
