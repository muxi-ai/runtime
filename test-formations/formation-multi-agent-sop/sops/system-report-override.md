---
type: sop
name: System Report Override
description: Override Linear issue creation with system calculation and PDF generation
mode: template
tags: linear, system, usage, cpu, memory, issue
---

# System Report Override SOP

This SOP overrides the default behavior of creating Linear issues with system info.
Instead, it generates a calculated system report as a PDF artifact.

## Steps

1. **Gather system information** [agent:it-support]
   Collect comprehensive system usage data including CPU, memory, disk, and core count.
   Store all metrics for calculation in the next step.

2. **Calculate system performance score**
   Extract core_count and cpu_usage_percent from the system info.
   Calculate performance score = core_count * (cpu_usage_percent / 100).
   Format the calculation results with the raw system data.

3. **Generate PDF report artifact**
   Create a PDF artifact containing:
   - System information summary
   - Performance score calculation
   - Timestamp and host information
   - Formatted as a professional system report
   Use the artifact system to generate and return the PDF to the user.

## Expected Outcome

Instead of creating a Linear issue, this workflow produces a PDF artifact with:
- Complete system metrics
- Calculated performance score (cores × usage)
- Professional formatting
- Direct download link for the user

## Notes

This SOP intentionally overrides the Linear issue creation to test SOP triggering and execution.
When SOPs are working correctly, this workflow will execute instead of the default agent routing.
