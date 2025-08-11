---
type: sop
name: New Customer Onboarding
description: Standard process for onboarding enterprise customers
mode: template
tags: customer, onboarding, setup, enterprise
---

# New Customer Onboarding

## Steps

1. **Verify customer information** [agent:operations]
   - Use [file:templates/customer-verification.md] for checklist
   - Query Salesforce via [mcp:salesforce] for account details
   - Validate company details and tax ID
   - Confirm billing information
   - Verify primary contact details

2. **Provision user accounts** [agent:devops]
   - Follow [file:references/account-provisioning.md]
   - Create admin account using [mcp:auth0/create_user]
   - Set up initial user seats per [file:references/seat-allocation.md]
   - Configure role-based permissions

3. **Schedule training** [agent:customer-success]
   - Book kickoff call within 48 hours
   - Use [file:templates/training-agenda.md]
   - Create calendar event via [mcp:google-calendar]
   - Send invites to stakeholders

4. **Configure integrations** [agent:developer]
   - Check [file:references/sso-setup-guide.md] if SSO requested
   - Set up SSO using [mcp:okta] if applicable
   - Connect required third-party tools
   - Test data flow using [file:templates/integration-checklist.md]

5. **Send welcome package** [agent:communications]
   - Use [file:templates/welcome-email.md]
   - Send via [mcp:sendgrid] or [mcp:mailchimp]
   - Include [file:references/getting-started.md]
   - Create Linear issue for tracking using [mcp:linear/create_issue]