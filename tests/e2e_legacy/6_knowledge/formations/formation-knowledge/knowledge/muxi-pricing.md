# The World’s First AI Server
You have a web server for websites. Now, you have an AI server for multi-agent systems – with orchestration, memory, and tools built-in. No hacks, no glue code.

# MUXI Cloud plans and pricing

MUXI is a developer-first platform for building, deploying, and orchestrating AI agents. This document outlines the available plans, pricing, add-ons, and operational notes related to how the platform is delivered.

---

## 🏷️ Free

- ✅ Free shared playground compute, suitable for testing and demos
- ✅ Limits: 1 Overlord, 3 Agents, 3 MCP servers
- ✅ Auto-sleep after 7 days of inactivity

---

## 🧪 Flex (pay-as-you-go)

**Only pay if you deploy a VPS. No usage = no cost.**

**Included:**

- ✅ Dedicated VPS when activated (choose your server)
- ✅ Unlimited agents (per VPS capacity)
- ✅ Observability logs
- ✅ Full access to agent marketplace
- ✅ CLI + GitHub deploy

**Price:** $20/month **only when active** + VPS cost
**Ideal for:** Hobbyists, tinkerers, casual devs

---

## 😎 Pro (billed annually)

**Flat-rate Pro access for regular users.**

**Included:**

- ✅ Everything in Flex
- ✅ Discounted monthly rate
- ✅ Persistent deployment access
- ✅ Always-on VPS, no “activation” requirement

**Price:** $10/month billed annually ($120/year) + VPS cost
**Ideal for:** Indie hackers, small production projects
**Upgrade:** Add Trail or move to Team anytime

---

## 🎁 Pro + Trail Bundle (billed annually)

**All-in plan with Trail Analytics included at a discount.**

**Included:**

- ✅ Everything in Pro
- ✅ Discounted bundled pricing
- ✅ Full developer analytics dashboard
- ✅ Trail Analytics included (5 GB logs/month)

**Price:** $20/month billed annually ($240/year) + VPS cost
**Ideal for:** Power users who want logs, dashboards, and insights
**Storage above 5GB** is billed per GB/month

---

## 👥 Team plan *(starts at)*

All Pro features, with collaboration and team management features.

**Included:**

- ✅ Everything in Pro
- ✅ Team access control
- ✅ Private organization registry
- ✅ Admin audit logs
- ✅ Usage tracking per agent/user
- ✅ SSO (SAML) and team onboarding
- ✅ Billing and usage dashboard
- ✅ Trail Analytics included (5GB logs/month)

**Pricing:** Starting at $49/user/month (capped at $499/month)

---

## 🚀 Startup Plan

Built for early-stage teams that want full power without enterprise pricing.

**Included:**

- ✅ Team plan with up to 10 team members

**Eligibility:**
Available to startups with < $1M in funding or < $500K in revenue

**Price:** $99/month
**Upgrade:** Scales to Team when limits are exceeded

**Implementation notes:**

- Can be provisioned instantly via self-service
- Requires basic verification (LinkedIn, website, etc.)
- Ideal for YC, Seed, Indie, or Bootstrap teams

---

## 🏢 Enterprise

For organizations with strict compliance, cloud restrictions, or integration needs.

**Custom offering includes:**

- ✅ Multi-cloud support (AWS, Azure, GCP, etc.)
- ✅ Region and zone selection
- ✅ Private VPC deployment
- ✅ Custom install scripts
- ✅ SLA, security reviews, and onboarding
- ✅ Registry mirrors + internal agent publishing

**Price:** Custom quote
**Contact us for a tailored setup.**

---

## 🧩 Add-ons and extensions

| Add-on                         | Availability       | Price                 |
|--------------------------------|--------------------|-----------------------|
| Trail Analytics (standalone)   | All plans          | $20/mo + storage      |
| Hosted local models (Ollama)   | All plans          | Requires min VPS size |
| Horizontal scaling setup       | Pro, Team          | $100+/mo/lb + VPS     |
| Private LLM endpoint proxy     | All plans          | Usage-based           |
| Astrategia API access          | Self-hosted only   | Usage-based API       |
| SSO / IAM                      | Team, Enterprise   | Included              |
| Dedicated DB / buffer service  | Team+              | Custom                |

---


## 💳 Marketplace agent policy

All users can:

- Browse and install **free agents**
- View and search all **paid agents**
- Deploy paid agents **after adding billing info**

Marketplace access is **not restricted by plan**. Only usage of paid agents requires billing information.

---

## 📜 Licensing note: Astrategia (Overlord model)

**Astrategia** is a proprietary fine-tuned version of Microsoft’s Phi-3 model, optimized for task planning, delegation, and orchestration across agents.

Due to licensing restrictions under the Microsoft Research License:

- The Astrategia model **cannot be redistributed**
- It **cannot be included** in open-source or self-hosted packages
- It **may be used** by:
  - MUXI Cloud users (Flex, Pro, Team, Enterprise)
  - Self-hosted users **via hosted API** with a paid usage plan

> We do not provide the fine-tuned weights directly.
> Self-hosted users may connect to the Astrategia API to enable orchestration functionality in their deployments.

---

## 📌 Technical backend notes

- MUXI Cloud is hosted primarily on **Hetzner (EU)** to optimize pricing and GPU access.
- Server provisioning, orchestrator bootstrapping, and model routing are fully automated via internal orchestration layer.
- Observability is handled via Trail (S3 + DuckDB), with metrics and traces in ClickHouse for Pro+ plans.
- Trail billing is usage-based, but bundled in the highest Pro tier or Team contract if selected.
- Local model support is provided through automated Ollama or llama.cpp deployments.
- Horizontal scaling (e.g. distributed memory or decoupled services) is available via add-ons for Pro+.

---

For questions, partnership requests, or custom plans, [contact the MUXI team](mailto:support@muxi.ai).
