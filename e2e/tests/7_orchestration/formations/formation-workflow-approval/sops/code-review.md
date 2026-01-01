---
type: sop
name: Code Review Best Practices
description: Guidelines for conducting thorough code reviews
mode: guide
tags: development, quality, review, best-practices
---

# Code Review Best Practices

## Guidelines

1. **Check code quality** [agent:senior-developer]
   - Review for design patterns and architecture
   - Look for potential security issues
   - Verify test coverage
   - Consider performance implications

2. **Provide constructive feedback** [agent:writer]
   - Be specific about issues found
   - Suggest improvements with examples
   - Acknowledge good practices
   - Use [file:templates/review-feedback.md] for structure

3. **Verify requirements** [agent:qa-specialist]
   - Check against ticket requirements
   - Ensure acceptance criteria are met
   - Test edge cases
   - Use [mcp:jira] to update ticket status

4. **Document decisions** [agent:documentation-specialist]
   - Record architectural decisions
   - Note any technical debt incurred
   - Update [file:references/adr-template.md] if needed