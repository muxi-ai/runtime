# Multiple Clarification Sequences PRD

## Overview

This PRD outlines the implementation of multiple clarification sequences within a single conversation, allowing the system to handle complex flows where one clarification may lead to another while preserving the original user intent.

## Problem Statement

Currently, the MUXI clarification system operates under a "one clarification per user" model where starting a new clarification cancels any existing one. This creates significant UX friction in scenarios where:

- User rejects clarification options and needs alternative flows
- System needs to collect additional information after initial clarification
- Complex workflows require multiple decision points
- Sub-clarifications are needed to resolve the main clarification

**Example Breaking Scenario:**
1. User: "List repositories in my account"
2. System: "Which account? (A) personal (B) work"
3. User: "None of these, I want to add a new account"
4. System: "Please provide your GitHub token"
5. User: Provides token
6. **Problem**: Original request ("list repositories") is lost - system doesn't continue with the original intent

## Goals

1. **Clarification Chaining**: Support sequences of clarifications that can build upon each other
2. **Intent Preservation**: Maintain the original user request throughout multiple clarification rounds
3. **Flow Continuity**: Automatically resume original request after sub-clarifications are resolved
4. **Backward Compatibility**: Ensure existing single-clarification flows continue to work
5. **Context Awareness**: Maintain conversation context across clarification boundaries

## User Stories

### 1. Credential Rejection Flow
**As a user rejecting credential options, I want to add a new account and have my original request fulfilled.**

Flow:
```
User: "List my GitHub repositories"
System: "Which account? 1. personal 2. work"
User: "None of these, I want to add a new account"
System: "Please provide your GitHub token for the new account:"
User: "ghp_abc123..."
System: "✅ New account added. Here are your repositories:" [continues original request]
```

### 2. Multi-Step Configuration
**As a user configuring complex settings, I want to go through multiple clarification steps.**

Flow:
```
User: "Set up my development environment"
System: "Which cloud provider? 1. AWS 2. GCP 3. Azure"
User: "AWS"
System: "Which region? 1. us-east-1 2. us-west-2 3. eu-west-1"
User: "us-east-1"
System: "Do you need a database? 1. Yes 2. No"
User: "Yes"
System: "Which database? 1. PostgreSQL 2. MySQL 3. MongoDB"
User: "PostgreSQL"
System: "✅ Setting up AWS development environment in us-east-1 with PostgreSQL..."
```

### 3. Error Recovery Flow
**As a user whose clarification response causes an error, I want to retry without losing context.**

Flow:
```
User: "Deploy my application"
System: "Which environment? 1. staging 2. production"
User: "production"
System: "❌ Production deployment failed. Would you like to: 1. Retry 2. Deploy to staging 3. Cancel"
User: "Deploy to staging"
System: "✅ Deploying to staging environment..."
```

## Technical Design

### 1. Clarification Stack Architecture

Replace the current single-clarification model with a **clarification stack**:

```python
class ClarificationStack:
    """Manages a stack of clarifications for a single user."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.stack: List[ClarificationFrame] = []
        self.original_intent: Optional[OriginalIntent] = None

    async def push_clarification(self, clarification: ClarificationRequest) -> None:
        """Add a new clarification to the stack."""

    async def pop_clarification(self) -> Optional[ClarificationRequest]:
        """Remove and return the top clarification."""

    async def peek_clarification(self) -> Optional[ClarificationRequest]:
        """Get the current active clarification without removing it."""

    def is_empty(self) -> bool:
        """Check if the stack is empty."""

    async def resolve_current(self, response: str) -> ClarificationResult:
        """Resolve the current clarification and determine next action."""
```

### 2. Clarification Frame Structure

Each clarification in the stack maintains its own context:

```python
class ClarificationFrame:
    """Represents a single clarification in the stack."""

    clarification_id: str
    parent_id: Optional[str]  # ID of parent clarification
    request: ClarificationRequest
    context: Dict[str, Any]  # Context needed to resume
    created_at: datetime
    resolved_at: Optional[datetime]
    resolution: Optional[str]

    # Flow control
    on_resolve: Optional[Callable]  # What to do when this clarification resolves
    on_cancel: Optional[Callable]   # What to do if this clarification is cancelled
```

### 3. Original Intent Preservation

Preserve the original user intent throughout the clarification stack:

```python
class OriginalIntent:
    """Preserves the original user request throughout clarifications."""

    message: str
    user_id: str
    session_id: str
    timestamp: datetime
    context: Dict[str, Any]

    # Collected information from clarifications
    resolved_parameters: Dict[str, Any] = {}

    async def can_fulfill(self) -> bool:
        """Check if enough information has been collected to fulfill the intent."""

    async def fulfill(self) -> Any:
        """Execute the original intent with collected parameters."""
```

### 4. Enhanced Clarification Manager

Upgrade the current `ClarificationManager` to support stacks:

```python
class StackedClarificationManager:
    """Manages multiple clarification sequences per user."""

    def __init__(self):
        self.user_stacks: Dict[str, ClarificationStack] = {}
        self.active_sessions: Dict[str, ClarificationSession] = {}

    async def start_clarification_sequence(
        self,
        user_id: str,
        original_intent: OriginalIntent,
        initial_clarification: ClarificationRequest
    ) -> str:
        """Start a new clarification sequence."""

    async def push_clarification(
        self,
        user_id: str,
        clarification: ClarificationRequest,
        parent_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a new clarification to the user's stack."""

    async def resolve_clarification(
        self,
        user_id: str,
        response: str
    ) -> ClarificationResult:
        """Resolve the current clarification and determine next action."""

    async def can_fulfill_original_intent(self, user_id: str) -> bool:
        """Check if the original intent can now be fulfilled."""

    async def fulfill_original_intent(self, user_id: str) -> Any:
        """Execute the original intent with all collected information."""
```

### 5. Flow Control Logic

Implement intelligent flow control to handle different resolution scenarios:

```python
class ClarificationFlowController:
    """Controls the flow between clarifications and intent fulfillment."""

    async def handle_clarification_response(
        self,
        user_id: str,
        response: str
    ) -> FlowAction:
        """Process a clarification response and determine next action."""

        result = await self.clarification_manager.resolve_clarification(user_id, response)

        if result.action == "push_new_clarification":
            # User response requires another clarification
            return await self._handle_sub_clarification(user_id, result)

        elif result.action == "pop_and_continue":
            # Current clarification resolved, continue with parent
            return await self._handle_clarification_pop(user_id, result)

        elif result.action == "fulfill_intent":
            # All clarifications resolved, fulfill original intent
            return await self._handle_intent_fulfillment(user_id, result)

        elif result.action == "cancel_sequence":
            # User wants to cancel the entire sequence
            return await self._handle_sequence_cancellation(user_id, result)
```

### 6. Integration Points

#### A. Overlord Integration
```python
# In overlord.py
async def _handle_user_message(self, user_id: str, message: str) -> Response:
    # Check if user has active clarification sequence
    if self.clarification_manager.has_active_sequence(user_id):
        return await self._handle_clarification_response(user_id, message)

    # Normal message processing
    return await self._process_new_message(user_id, message)
```

#### B. Agent Integration
```python
# In agent.py
async def _handle_missing_information(self, missing_info: MissingInfo) -> None:
    # Instead of single clarification, start a sequence
    await self.clarification_manager.start_clarification_sequence(
        user_id=self.user_id,
        original_intent=self.current_intent,
        initial_clarification=missing_info.to_clarification()
    )
```

## Implementation Phases

### Phase 1: Core Infrastructure (MVP)
- Implement `ClarificationStack` and `ClarificationFrame`
- Create `OriginalIntent` preservation mechanism
- Basic push/pop clarification operations
- Simple linear clarification sequences

### Phase 2: Enhanced Flow Control
- Implement `ClarificationFlowController`
- Add support for branching clarifications
- Error recovery and retry mechanisms
- Context preservation across clarification boundaries

### Phase 3: Advanced Features
- Clarification cancellation and rollback
- Parallel clarification branches
- Timeout handling for long sequences
- Analytics and flow optimization

### Phase 4: User Experience Enhancements
- Progress indicators for long sequences
- Clarification history and navigation
- Smart suggestions based on context
- Voice and multi-modal clarification support

## Example Implementation: Credential Rejection Flow

### Before (Current Behavior):
```python
# In credential_handler.py
async def handle_ambiguous_credential(self, error: AmbiguousCredentialError):
    # Start clarification - cancels any existing ones
    await self.clarification_manager.start_clarification(
        user_id=error.user_id,
        request=self._create_credential_selection_request(error)
    )
```

### After (Multiple Clarifications):
```python
# Enhanced credential_handler.py
async def handle_ambiguous_credential(self, error: AmbiguousCredentialError):
    # If this is the first clarification, preserve original intent
    if not self.clarification_manager.has_active_sequence(error.user_id):
        original_intent = OriginalIntent(
            message=self.current_message,
            user_id=error.user_id,
            session_id=self.session_id,
            context={"service": error.service, "action": "credential_selection"}
        )

        await self.clarification_manager.start_clarification_sequence(
            user_id=error.user_id,
            original_intent=original_intent,
            initial_clarification=self._create_credential_selection_request(error)
        )
    else:
        # This is a sub-clarification (e.g., user rejected options)
        await self.clarification_manager.push_clarification(
            user_id=error.user_id,
            clarification=self._create_credential_addition_request(error)
        )

async def handle_credential_rejection(self, user_id: str, rejection_response: str):
    # User rejected credential options, start credential addition flow
    addition_clarification = self._create_credential_addition_clarification(rejection_response)

    await self.clarification_manager.push_clarification(
        user_id=user_id,
        clarification=addition_clarification,
        parent_context={"action": "add_new_credential"}
    )

async def handle_credential_addition_complete(self, user_id: str, new_credential: Dict):
    # Credential added successfully, check if we can fulfill original intent
    if await self.clarification_manager.can_fulfill_original_intent(user_id):
        # Resume original request with new credential
        return await self.clarification_manager.fulfill_original_intent(user_id)
    else:
        # Need more information, continue clarification sequence
        return await self._continue_clarification_sequence(user_id)
```

## Error Handling and Edge Cases

### 1. Clarification Timeout
```python
# Handle cases where user doesn't respond to clarifications
async def handle_clarification_timeout(self, user_id: str) -> None:
    stack = self.get_user_stack(user_id)

    # Try to fulfill with partial information
    if stack.original_intent.can_fulfill_partially():
        await self._fulfill_with_defaults(user_id)
    else:
        await self._cancel_sequence_with_explanation(user_id)
```

### 2. Circular Clarifications
```python
# Prevent infinite clarification loops
def _check_circular_clarification(self, stack: ClarificationStack, new_clarification: ClarificationRequest) -> bool:
    seen_types = {frame.request.type for frame in stack.stack}
    return new_clarification.type in seen_types
```

### 3. Context Overflow
```python
# Handle cases where clarification context becomes too large
async def _manage_context_size(self, stack: ClarificationStack) -> None:
    if stack.get_context_size() > MAX_CONTEXT_SIZE:
        await self._compress_context(stack)
```

## Security Considerations

1. **Context Isolation**: Ensure clarification contexts don't leak between users
2. **Validation**: Validate each clarification response before processing
3. **Audit Trail**: Log all clarification sequences for debugging and security
4. **Rate Limiting**: Prevent abuse through excessive clarification sequences
5. **Timeout Protection**: Prevent resource exhaustion through abandoned sequences

## Success Metrics

1. **Sequence Completion Rate**: % of clarification sequences that successfully complete
2. **Average Sequence Length**: Number of clarifications needed to resolve requests
3. **User Satisfaction**: User feedback on multi-step clarification flows
4. **Error Recovery Rate**: % of errors that are successfully recovered through clarification
5. **Context Preservation**: % of original intents successfully fulfilled after clarifications

## Open Questions

1. Should there be a maximum depth for clarification stacks?
2. How should we handle concurrent clarification sequences for the same user?
3. Should clarification history be persisted across sessions?
4. How do we handle clarifications that require real-time interaction?
5. Should we support clarification branching (multiple possible paths)?

## Future Enhancements

1. **Visual Clarification Flow**: UI showing clarification progress and history
2. **Voice Clarifications**: Support for voice-based clarification sequences
3. **Predictive Clarifications**: AI-powered suggestions to reduce clarification steps
4. **Collaborative Clarifications**: Multiple users contributing to clarification resolution
5. **Template-Based Clarifications**: Pre-defined sequences for common workflows

## Migration Strategy

### Phase 1: Backward Compatibility
- Implement new system alongside existing clarification manager
- Route simple clarifications through legacy system
- Route complex sequences through new system

### Phase 2: Gradual Migration
- Migrate credential clarifications to new system
- Migrate agent clarifications to new system
- Add opt-in flags for new behavior

### Phase 3: Full Migration
- Deprecate old clarification manager
- Migrate all clarification flows to new system
- Remove legacy clarification code

## Testing Strategy

### Unit Tests
- Test clarification stack operations (push/pop/peek)
- Test original intent preservation
- Test flow control logic
- Test error recovery mechanisms

### Integration Tests
- Test credential rejection → addition → fulfillment flow
- Test multi-step configuration workflows
- Test error recovery scenarios
- Test timeout handling

### End-to-End Tests
- Test complex clarification sequences in real conversations
- Test concurrent clarification handling
- Test context preservation across long sequences
- Test performance under load

## Example Test Scenarios

### Test 1: Credential Rejection Flow
```python
async def test_credential_rejection_flow():
    # Start with ambiguous credential request
    response1 = await overlord.chat("List my GitHub repositories")
    assert "which account" in response1.lower()

    # User rejects options
    response2 = await overlord.chat("None of these, I want to add a new account")
    assert "provide your github token" in response2.lower()

    # User provides token
    response3 = await overlord.chat("ghp_abc123...")
    assert "successfully added" in response3.lower()

    # Original intent should be fulfilled
    assert "repositories" in response3.lower()
```

### Test 2: Multi-Step Configuration
```python
async def test_multi_step_configuration():
    response1 = await overlord.chat("Set up my development environment")
    assert "cloud provider" in response1.lower()

    response2 = await overlord.chat("AWS")
    assert "region" in response2.lower()

    response3 = await overlord.chat("us-east-1")
    assert "database" in response3.lower()

    response4 = await overlord.chat("Yes")
    assert "which database" in response4.lower()

    response5 = await overlord.chat("PostgreSQL")
    assert "setting up aws development environment" in response5.lower()
```

### Test 3: Error Recovery
```python
async def test_error_recovery():
    response1 = await overlord.chat("Deploy my application")
    assert "environment" in response1.lower()

    response2 = await overlord.chat("production")
    assert "deployment failed" in response2.lower()

    response3 = await overlord.chat("Deploy to staging")
    assert "deploying to staging" in response3.lower()
```

---

*PRD Created: 2025-07-14*
*Status: Draft - Ready for Review*
*Related: natural-language-credential-management.md*
