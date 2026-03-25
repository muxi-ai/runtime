---
type: sop
name: JSON Output Test
description: Test SOP that returns structured JSON without synthesis
mode: template
tags: json, test, status
synthesis: false
---

# JSON Output Test SOP

## Steps

1. **Generate JSON status report** [agent:it-support]
   Return ONLY a raw JSON object with exactly this structure, no markdown, no prose:
   {"status":"ok","service":"muxi","checks":["memory","cpu","disk"]}
   The ENTIRE response must be ONLY the JSON object and nothing else.
