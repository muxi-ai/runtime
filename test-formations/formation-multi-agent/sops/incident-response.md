---
type: sop
name: Production Incident Response
description: Handle production incidents from detection to resolution
mode: template
tags: critical, production, ops
---

# Production Incident Response

## Steps

1. **Assess severity and impact** [agent:monitoring-specialist]
   - Check monitoring dashboards for scope
   - Review [file:references/severity-matrix.md] for classification
   - Use [mcp:datadog] to pull metrics from last hour
   - Determine number of affected users

2. **Notify stakeholders** [agent:communications]
   - Use [file:references/escalation-tree.md] for contact info
   - P1: Page on-call engineer via [mcp:pagerduty]
   - P2: Send Slack notification using [mcp:slack]
   - P3: Create ticket using [mcp:linear/create_issue]

3. **Identify root cause** [agent:researcher]
   - Review recent deployments
   - Check [file:references/dashboard-guide.md] for metrics analysis
   - Query logs using [mcp:elasticsearch]
   - Correlate with any recent changes

4. **Create incident report** [agent:writer]
   - Use [file:templates/incident-report.md] as starting point
   - Include screenshots and timeline
   - Create Linear issue with [mcp:linear/create_issue]
   - Reference [file:references/outage-analysis.md]

5. **Document post-mortem** [agent:documentation-specialist]
   - Follow [file:templates/postmortem.md] format
   - Timeline of events
   - Lessons learned and action items
   - Upload to Confluence using [mcp:confluence]