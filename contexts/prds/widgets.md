# Widgets PRD
**Product Requirements Document**

**Date:** 2025-01-17
**Status:** 📋 **PLANNED** (Deferred from Area 11B)
**Priority:** P2 (Post-foundation)
**Owner:** Runtime Team

## Executive Summary

Widgets will enhance MUXI Runtime responses with contextual UI components that improve user experience for common workflow patterns. This feature focuses on **high-value, deterministic use cases** with **tight SDK integration** for seamless user interactions.

**Core Principle:** Widgets should feel like natural extensions of the conversation, not bolted-on UI components.

## Background & Motivation

### Current State
- MUXI responses are static text/markdown/html/JSON
- Users must manually type responses for workflow approvals
- Clarification requests require full text responses
- Credential collection is done through plain text (security concern)
- Links in responses require manual navigation
- Source references are embedded in text without easy access

### User Pain Points
1. **Workflow Friction:** "Approve this plan" requires typing "yes" or "approve"
2. **Clarification Overhead:** "Which GitHub account?" requires typing account name
3. **Security Risk:** Credentials typed in plain text chat
4. **Context Switching:** Clicking links loses conversation context
5. **Source Verification:** Hard to access referenced sources quickly

### Opportunity
Transform static responses into **interactive experiences** while maintaining **conversation flow** and **cross-platform compatibility**.

## Product Vision

> **"Conversations that adapt to user needs with contextual interactions, while preserving the natural flow of AI dialogue."**

**Not building:** Generic UI framework or complex interactive widgets
**Building:** Focused, conversation-enhancing interactions with seamless SDK integration

## Target Scenarios

### **Scenario 1: Workflow Approval**
```
🤖 "I've created a deployment plan with 3 steps. Here's the summary:
1. Update dependencies
2. Run migration scripts
3. Deploy to production

[Approve Plan] [Modify Plan]"

👤 *Clicks "Approve Plan"*
🤖 "Great! Starting deployment process..."
```

### **Scenario 2: Clarification Enhancement**
```
🤖 "You have 3 GitHub accounts configured:
- personal/username (personal projects)
- company/teamname (work projects)
- org/nonprofit (volunteer work)

Which account should I use for this repository?

[Personal] [Company] [Nonprofit]"

👤 *Clicks "Company"*
🤖 "Using company/teamname account. Fetching repository data..."
```

### **Scenario 3: Secure Credential Collection**
```
🤖 "I need access to your Slack workspace to send notifications.

[Enter Slack Token] [Setup OAuth]"

👤 *Clicks "Enter Slack Token"*
🤖 *Shows secure input form*
👤 *Enters token securely*
🤖 "Token configured successfully. Testing connection... ✅"
```

### **Scenario 4: Link Previews**
```
🤖 "Here's the documentation for the API: https://api.example.com/docs

[📄 API Documentation Preview]
Title: REST API Reference v2.1
Description: Complete API reference with examples..."
```

### **Scenario 5: Source References**
```
🤖 "Based on the latest React 19 release notes, the new features include...

[📚 View Sources (3)]"

👤 *Clicks "View Sources"*
🤖 *Expands with:*
- React 19 Release Blog Post
- GitHub Release Notes
- React Docs Updates
```

## Core Requirements

### **Functional Requirements**

#### **FR1: Workflow Approval Interactions**
- **Trigger:** System detects pending workflow approval
- **Elements:** "Approve Plan" and "Modify Plan" buttons
- **Behavior:**
  - "Approve" → Execute workflow automatically
  - "Modify" → Open clarification for changes
- **Fallback:** Text-based approval still works

#### **FR2: Enhanced Clarification Options**
- **Trigger:** Clarification system has multiple predetermined options
- **Elements:** Button for each option
- **Behavior:** Clicking button sends selected option as user response
- **Fallback:** User can still type custom response

#### **FR3: Secure Credential Collection**
- **Trigger:** Agent detects need for API keys, tokens, or credentials
- **Elements:** Secure form with appropriate input types
- **Behavior:**
  - Token input → masked password field
  - OAuth setup → redirect flow
  - Username/password → secure form
- **Security:** Never log credential values, encrypt in transit

#### **FR4: Link Previews**
- **Trigger:** Response contains external URLs
- **Elements:** Preview cards with title, description, favicon
- **Behavior:** Expandable preview without leaving conversation
- **Fallback:** Standard clickable links

#### **FR5: Source References**
- **Trigger:** Response references external sources or documents
- **Elements:** "View Sources" expandable section
- **Behavior:** Shows clickable list of referenced sources
- **Integration:** Links to knowledge base entries when available

#### **FR6: Artifact Positioning**
- **Trigger:** Response includes artifacts (files, code, etc.)
- **Elements:** Placeholder markers for SDK artifact placement
- **Behavior:** SDK renders artifacts at specified positions
- **Enhancement:** Better than current "appended at end" approach

### **Non-Functional Requirements**

#### **NFR1: Cross-Platform Compatibility**
- Must work across all SDK platforms (Web, Mobile, CLI, API)
- Graceful degradation for non-interactive clients
- Consistent behavior across different response formats

#### **NFR2: Security**
- Credential forms never store values in logs or memory
- All credential transmission encrypted end-to-end
- Input validation for all widgets

#### **NFR3: Performance**
- Widget generation adds <100ms to response time
- Link preview fetching happens asynchronously
- No blocking operations in response pipeline

#### **NFR4: Accessibility**
- All widgets keyboard navigable
- Screen reader compatible
- Clear visual indicators for interactive areas

## Technical Architecture

### **Response Structure**
```json
{
  "content": "Here's your plan: <widget:workflow_approval>\n\nAlso check this link: <widget:link_preview_1>",
  "widgets": {
    "workflow_approval": {
      "type": "workflow_approval",
      "config": {
        "workflow_id": "wf_123",
        "actions": ["approve", "modify"]
      }
    },
    "link_preview_1": {
      "type": "link_preview",
      "config": {
        "url": "https://example.com",
        "title": "Example Site",
        "description": "Sample description"
      }
    }
  },
  "format": "markdown"
}
```

### **Widget Types**

#### **workflow_approval**
```json
{
  "type": "workflow_approval",
  "config": {
    "workflow_id": "string",
    "actions": ["approve", "modify", "cancel"],
    "context": "string (optional)"
  }
}
```

#### **clarification_options**
```json
{
  "type": "clarification_options",
  "config": {
    "clarification_id": "string",
    "options": [
      {"label": "Personal Account", "value": "personal"},
      {"label": "Company Account", "value": "company"}
    ]
  }
}
```

#### **credential_form**
```json
{
  "type": "credential_form",
  "config": {
    "service": "slack|github|openai",
    "fields": [
      {"name": "token", "type": "password", "label": "API Token"},
      {"name": "workspace", "type": "text", "label": "Workspace ID"}
    ],
    "action": "store_credentials"
  }
}
```

#### **link_preview**
```json
{
  "type": "link_preview",
  "config": {
    "url": "string",
    "title": "string",
    "description": "string",
    "image": "string (optional)",
    "site_name": "string (optional)"
  }
}
```

#### **source_references**
```json
{
  "type": "source_references",
  "config": {
    "sources": [
      {
        "title": "React 19 Release Notes",
        "url": "https://react.dev/blog/react-19",
        "type": "documentation"
      }
    ]
  }
}
```

### **Detection Logic**

```python
class WidgetDetector:
    """Deterministic detection of when to add widgets"""

    def detect_widgets(self, response, context):
        widgets = {}

        # Workflow approval detection
        if context.has_pending_workflow_approval():
            widgets["workflow_approval"] = self._create_workflow_approval(context)

        # Clarification enhancement
        if context.has_clarification_options():
            widgets["clarification_options"] = self._create_clarification_options(context)

        # Credential collection
        if context.needs_credentials():
            widgets["credential_form"] = self._create_credential_form(context)

        # Link preview generation
        links = self._extract_links(response.content)
        for i, link in enumerate(links):
            widgets[f"link_preview_{i}"] = self._create_link_preview(link)

        # Source reference detection
        if context.has_source_references():
            widgets["source_references"] = self._create_source_references(context)

        return widgets
```

## SDK Integration Requirements

### **Web SDK**
- React components for each widget type
- Click handlers that send structured responses
- Secure credential form with proper input masking
- Link preview cards with expand/collapse

### **Mobile SDK**
- Native UI components for each platform (iOS/Android)
- Touch-optimized interactions
- Biometric authentication for credential collection
- In-app browser for link previews

### **CLI SDK**
- Text-based fallbacks for all interactions
- Keyboard shortcuts for common actions
- Secure credential prompting (hidden input)
- Optional browser opening for links

### **API SDK**
- Structured JSON responses with widget definitions
- Webhook callbacks for interactive responses
- Credential encryption for API storage
- Link metadata fetching

## Implementation Phases

### **Phase 1: Foundation (P0)**
- Response structure with placeholders
- Basic widget detection logic
- Web SDK components for workflow approval
- Secure credential collection forms

### **Phase 2: Enhancement (P1)**
- Link preview generation and caching
- Source reference expansion
- Mobile SDK implementation
- CLI fallback improvements

### **Phase 3: Polish (P2)**
- Advanced link preview features (thumbnails, metadata)
- Accessibility improvements
- Performance optimizations
- Analytics and usage tracking

## Success Metrics

### **Adoption Metrics**
- **Widget usage rate:** >70% of eligible responses include widgets
- **User engagement rate:** >60% of widgets are clicked/used
- **SDK compatibility:** 100% feature parity across Web, Mobile, CLI

### **User Experience Metrics**
- **Workflow approval time:** 50% reduction from text-based approval
- **Clarification resolution rate:** 80% resolved through button clicks
- **Credential collection success:** 95% successful form completion
- **User satisfaction:** >4.5/5 rating for widget features

### **Technical Metrics**
- **Response time impact:** <100ms additional latency
- **Error rate:** <1% widget failures
- **Security incidents:** 0 credential-related breaches

## Risks & Mitigations

### **Risk: SDK Fragmentation**
- **Impact:** Inconsistent experience across platforms
- **Mitigation:** Shared design system and component specifications
- **Acceptance criteria:** 95% feature parity across all SDKs

### **Risk: Security Vulnerabilities**
- **Impact:** Credential exposure or unauthorized access
- **Mitigation:** End-to-end encryption, security audits, no logging
- **Acceptance criteria:** Pass security penetration testing

### **Risk: Performance Degradation**
- **Impact:** Slower response times hurt user experience
- **Mitigation:** Asynchronous processing, caching, performance monitoring
- **Acceptance criteria:** <100ms additional response time

### **Risk: Over-Engineering**
- **Impact:** Feature bloat and maintenance overhead
- **Mitigation:** Focus on 6 core use cases, defer everything else
- **Acceptance criteria:** Only implement defined widget types

## Future Considerations

### **Potential Expansions**
- **Charts and data visualization** (when clear use cases emerge)
- **File upload interfaces** (for document analysis workflows)
- **Progress indicators** (for long-running operations)
- **Collaborative widgets** (for multi-user workflows)

### **Integration Opportunities**
- **A2A system:** Widgets for agent-to-agent communication
- **MCP servers:** Rich tool interfaces through widgets
- **Knowledge system:** Interactive exploration of knowledge graphs
- **Workflow system:** Visual workflow builders and editors

## Definition of Done

### **Core Features Complete**
- [ ] All 6 widget types implemented and tested
- [ ] Web SDK components with full functionality
- [ ] Secure credential handling with encryption
- [ ] Cross-platform compatibility verified
- [ ] Performance benchmarks met (<100ms impact)

### **Quality Assurance**
- [ ] Security audit completed and passed
- [ ] Accessibility testing completed (WCAG 2.1 AA)
- [ ] Cross-browser testing completed
- [ ] Mobile responsiveness verified
- [ ] CLI fallbacks tested and documented

### **Documentation & Support**
- [ ] Developer documentation with examples
- [ ] SDK integration guides published
- [ ] Security guidelines documented
- [ ] Troubleshooting guides created
- [ ] Performance optimization guide available

---

## Appendix: Why This Approach

### **Focused Scope**
Instead of building a generic interactive UI framework, we're solving **specific, high-value problems** with **simple, reliable solutions**.

### **SDK-First Design**
Widgets require tight integration with client applications. By designing for SDK integration from the start, we ensure **consistent, high-quality experiences** across all platforms.

### **Security by Design**
Credential collection and sensitive interactions are **built with security as the primary concern**, not retrofitted later.

### **Progressive Enhancement**
All widgets **gracefully degrade** to text-based alternatives, ensuring compatibility with existing integrations and clients.

### **Conversation Flow Preservation**
Widgets enhance the conversation **without disrupting the natural flow** of AI dialogue. They feel like natural extensions, not foreign UI components.

This focused approach delivers **maximum user value** with **minimal complexity** and **low risk of over-engineering**.