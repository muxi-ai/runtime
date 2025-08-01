# A2A Communication Test Findings

## Current Status

The tests are passing but not for the expected reasons:

### What's Working:
1. **Workflow orchestration is disabled** - `auto_decomposition: false` prevents the overlord from decomposing tasks
2. **Agents recognize limitations** - IT Support knows it can't create Linear issues, Project Manager knows it can't get system info
3. **Tasks get completed** - Somehow the agents are getting the information they need

### What's Not Clear:
1. **A2A configuration** - The formation has `a2a: internal: enabled: true` but this doesn't match the schema
2. **Communication mechanism** - It's unclear if true A2A communication is happening or if the overlord is helping
3. **MCP tool access** - The agents might be sharing tools through the overlord rather than A2A

## Observations from Test Output:

1. **IT Support Response**: "I need help from the Project Manager agent to create issues on Linear since I don't have access to Linear tools."
   - ✓ Correctly identifies it needs help
   - ✓ Knows which agent to ask
   - ? But how does it get the help?

2. **Project Manager Response**: Successfully creates Linear issues with system information
   - ✓ Has the system info despite no direct access
   - ? How did it get the memory statistics?

## Potential Explanations:

1. **Overlord Mediation**: The overlord might be facilitating communication even with workflow disabled
2. **Tool Sharing**: MCP tools might be accessible across agents through the overlord
3. **Hidden A2A**: A2A might be working but not logging clearly
4. **Enhanced Prompts**: The MCP `enhance_user_prompts: true` might be adding information

## Next Steps:

1. Check if agents have direct A2A communication methods
2. Add logging to trace how information flows between agents
3. Test with explicit A2A method calls
4. Verify the correct A2A configuration format

## Configuration Issues:

The current configuration:
```yaml
a2a:
  internal:
    enabled: true
```

Might need to be:
```yaml
a2a:
  server_enabled: false  # For internal only
  external_registry_enabled: false  # No external registry needed
```

Based on the A2AServiceSchema in the codebase.