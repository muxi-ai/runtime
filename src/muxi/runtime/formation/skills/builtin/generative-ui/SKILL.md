---
name: generative-ui
description: "Create interactive HTML widgets, dashboards, diagrams, and visual explainers for requests that are better shown than described."
license: Apache-2.0
compatibility: ">=1.0"
allowed-tools: generate_file
---

# Generative UI

Use this skill when the user wants an interactive visual response instead of plain text.

## When to use
- Interactive explainers
- Small simulations and calculators
- Dashboards and scorecards
- Architecture diagrams and flow visualizations
- Visual summaries of structured data

## Required approach
1. Decide whether the request is genuinely more useful as a visual artifact than as prose.
2. If yes, use the `generate_file` tool to create a single self-contained HTML file.
3. Prefer inline CSS and inline JavaScript so the widget works as a portable artifact.
4. Prefer semantic HTML and accessible controls with clear labels.
5. Prefer SVG for diagrams and simple visualizations; use Canvas only when animation is necessary.
6. Keep the layout responsive and dark-mode friendly.
7. In your final response, describe what you created without mentioning file paths or sandbox details.

## Implementation rules
- Save the result as `.html`
- Keep everything in one file unless the user explicitly asks for multiple assets
- Do not depend on local files outside the generated artifact
- Avoid external CDNs unless the user explicitly asks for them
- Include concise instructional copy in the UI when it helps the user understand how to interact with it
- Prefer simple, robust controls such as sliders, buttons, tabs, toggles, and tables

## Suggested patterns

### Interactive explainer
- Short title and one-sentence summary
- One or two controls
- Live-updating numbers or chart
- Brief interpretation below the visualization

### Dashboard
- Summary cards at the top
- One primary chart
- One compact table or detail panel
- Clear units and legends

### Diagram
- Use SVG with labels and arrows
- Keep spacing generous
- Keep text readable at common laptop widths

## Tool usage
Use:

```python
generate_file(code="...", filename="widget.html")
```

Generate complete Python that writes the full HTML document to disk.
