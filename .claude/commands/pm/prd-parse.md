# PRD Parse

Convert PRD to technical implementation epic.

## Usage
```
/pm:prd-parse <feature_name>
```

## Instructions

You are a technical lead converting a Product Requirements Document into a detailed implementation epic for: **$ARGUMENTS**

### 1. Read the PRD
- Load the PRD from `.claude/prds/$ARGUMENTS.md`
- Analyze all requirements and constraints
- Understand the user stories and success criteria
- Extract the PRD description from frontmatter

### 2. Technical Analysis
- Identify architectural decisions needed
- Determine technology stack and approaches
- Map functional requirements to technical components
- Identify integration points and dependencies

### 3. File Format with Frontmatter
Create the epic file at: `.claude/epics/$ARGUMENTS/epic.md` with this exact structure:

```markdown
---
name: $ARGUMENTS
status: backlog
created: [Current ISO date/time]
progress: 0%
prd: .claude/prds/$ARGUMENTS.md
github: [Will be updated when synced to GitHub]
---

# Epic: $ARGUMENTS

## Overview
Brief technical summary of the implementation approach

## Architecture Decisions
- Key technical decisions and rationale
- Technology choices
- Design patterns to use

## Technical Approach
### Frontend Components
- UI components needed
- State management approach
- User interaction patterns

### Backend Services
- API endpoints required
- Data models and schema
- Business logic components

### Infrastructure
- Deployment considerations
- Scaling requirements
- Monitoring and observability

## Implementation Strategy
- Development phases
- Risk mitigation
- Testing approach

## Task Breakdown Preview
High-level task categories that will be created:
- [ ] Category 1: Description
- [ ] Category 2: Description
- [ ] etc.

## Dependencies
- External service dependencies
- Internal team dependencies
- Prerequisite work

## Success Criteria (Technical)
- Performance benchmarks
- Quality gates
- Acceptance criteria

## Estimated Effort
- Overall timeline estimate
- Resource requirements
- Critical path items
```

### 4. Frontmatter Guidelines
- **name**: Use the exact feature name (same as $ARGUMENTS)
- **status**: Always start with "backlog" for new epics
- **created**: Use current date/time in ISO format
- **progress**: Always start with "0%" for new epics
- **prd**: Reference the source PRD file path
- **github**: Leave placeholder text - will be updated during sync

### 5. Output Location
Create the directory structure if it doesn't exist:
- `.claude/epics/$ARGUMENTS/` (directory)
- `.claude/epics/$ARGUMENTS/epic.md` (epic file)

Focus on creating a technically sound implementation plan that addresses all PRD requirements while being practical and achievable for "$ARGUMENTS".
