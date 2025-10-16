
====================================================================================================
DETAILED REVIEW - ALL PROBLEMATIC EVENTS
====================================================================================================


====================================================================================================
MISSING_DESCRIPTION: 13 events
====================================================================================================

1. ConversationEvents.A2A_MESSAGE_FAILED [ERROR]
   Location: src/muxi/services/a2a/client.py:236
   Description: f-string: A2A message to {target_agent_id} failed: {str(e)}
   Recommendation: MISSING DESCRIPTION - Add meaningful description

   CODE CONTEXT:
        226:             )
        227: 
        228:             # Track error metrics
        229:             duration = asyncio.get_event_loop().time() - start_time
        230:             observability.observe(
        231:                 event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
        232:                 level=observability.EventLevel.ERROR,
        233:                 data={
        234:                     "source_agent_id": source_agent_id,
        235:                     "target_agent_id": target_agent_id,
   >>>  236:                     "message_type": message_type,
        237:                     "duration": duration,
        238:                     "error": str(e),
        239:                 },
        240:             )
        241: 
        242:             raise
        243: 
        244:     async def handle_message(
        245:         self,
        246:         agent,


2. ConversationEvents.A2A_MESSAGE_SENT [INFO]
   Location: src/muxi/services/a2a/client.py:202
   Description: f-string: Error sending A2A message: {e}
   Recommendation: MISSING DESCRIPTION - Add meaningful description

   CODE CONTEXT:
        192:             response: SendMessageResponse = await self.sdk_client.send_message(request)
        193: 
        194:             # Track metrics
        195:             duration = asyncio.get_event_loop().time() - start_time
        196:             observability.observe(
        197:                 event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
        198:                 level=observability.EventLevel.INFO,
        199:                 data={
        200:                     "source_agent_id": source_agent_id,
        201:                     "target_agent_id": target_agent_id,
   >>>  202:                     "message_type": message_type,
        203:                     "duration": duration,
        204:                     "success": True,
        205:                 },
        206:             )
        207: 
        208:             if wait_for_response:
        209:                 try:
        210:                     # Attempt to access result attribute safely
        211:                     if response.root and response.root.result:
        212:                         # Convert SDK response back to MUXI format


3. ConversationEvents.AGENT_A2A [DEBUG]
   Location: src/muxi/formation/agents/agent.py:1600
   Description: f-string: Agent {self.agent_id} attempting A2A (attempt {self._a2a_attempt_count}/{self._max_a2a_attempts}
   Recommendation: MISSING DESCRIPTION - Add meaningful description

   CODE CONTEXT:
       1590:                     description=f"Failed to call LLM with tools for agent {self.agent_id}: {str(e)}",
       1591:                 )
       1592:                 # Fallback to no tools
       1593:                 raw_response = await self.model.chat(self._messages)
       1594:         else:
       1595:             # No tools available - try A2A for non-workflow tasks
       1596:             if not is_workflow_task and self._a2a_attempt_count < self._max_a2a_attempts:
       1597:                 # Increment attempt counter before making the call
       1598:                 self._a2a_attempt_count += 1
       1599: 
   >>> 1600:                 observability.observe(
       1601:                     event_type=observability.ConversationEvents.AGENT_A2A,
       1602:                     level=observability.EventLevel.DEBUG,
       1603:                     data={
       1604:                         "agent_id": self.agent_id,
       1605:                         "attempt_count": self._a2a_attempt_count,
       1606:                         "max_attempts": self._max_a2a_attempts,
       1607:                     },
       1608:                     description=(
       1609:                         f"Agent {self.agent_id} attempting A2A (attempt "
       1610:                         f"{self._a2a_attempt_count}/{self._max_a2a_attempts})"


   ... and 10 more events in this category


====================================================================================================
REVIEW_DEBUG_GRANULAR: 38 events
====================================================================================================

1. ConversationEvents.A2A_DISCOVERY_COMPLETED [DEBUG]
   Location: src/muxi/services/a2a/discovery.py:901
   Description: A2A registry saved successfully
   Recommendation: REVIEW - DEBUG ConversationEvent, may be too granular for production

   CODE CONTEXT:
        891:                 "formation_name": self.formation_name,
        892:                 "agents": agents_data,
        893:                 "saved_at": time.time(),
        894:             }
        895: 
        896:             with open(registry_path, "w") as f:
        897:                 json.dump(data, f, indent=2)
        898: 
        899:             #  A2A discovery debug - TODO: add observability
        900: 
   >>>  901:             observability.observe(
        902:                 event_type=observability.ConversationEvents.A2A_DISCOVERY_COMPLETED,
        903:                 level=observability.EventLevel.DEBUG,
        904:                 data={"formation_name": self.formation_name, "saved_agents": len(self.agents)},
        905:                 description="A2A registry saved successfully",
        906:             )
        907: 
        908:         except Exception as e:
        909:             observability.observe(
        910:                 event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
        911:                 level=observability.EventLevel.ERROR,


2. ConversationEvents.A2A_MESSAGE_SENT [DEBUG]
   Location: src/muxi/services/a2a/client.py:153
   Description: Routing internally to {target_agent_id}
   Recommendation: REVIEW - DEBUG ConversationEvent, may be too granular for production

   CODE CONTEXT:
        143:             )
        144: 
        145:             # Check if internal or external routing
        146:             if self._is_internal(target_agent_id):
        147:                 observability.observe(
        148:                     event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
        149:                     level=observability.EventLevel.DEBUG,
        150:                     data={"target_agent_id": target_agent_id, "routing": "internal"},
        151:                     description=f"Routing internally to {target_agent_id}",
        152:                 )
   >>>  153:                 return await self._send_internal(
        154:                     source_agent_id,
        155:                     target_agent_id,
        156:                     sdk_message,
        157:                     message_type,
        158:                     wait_for_response,
        159:                     timeout,
        160:                 )
        161: 
        162:             # For external agents, check if SDK is initialized
        163:             observability.observe(


3. ConversationEvents.A2A_MESSAGE_SENT [DEBUG]
   Location: src/muxi/services/a2a/client.py:169
   Description: External agent {target_agent_id} requested
   Recommendation: REVIEW - DEBUG ConversationEvent, may be too granular for production

   CODE CONTEXT:
        159:                     timeout,
        160:                 )
        161: 
        162:             # For external agents, check if SDK is initialized
        163:             observability.observe(
        164:                 event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
        165:                 level=observability.EventLevel.DEBUG,
        166:                 data={"target_agent_id": target_agent_id, "routing": "external"},
        167:                 description=f"External agent {target_agent_id} requested",
        168:             )
   >>>  169: 
        170:             if not self.sdk_client:
        171:                 # External agents require the SDK client for proper routing
        172:                 # There's no effective fallback since _try_find_handler only checks
        173:                 # already registered handlers, which by definition won't include
        174:                 # external agents
        175:                 raise RuntimeError(
        176:                     f"Cannot route to external agent '{target_agent_id}': "
        177:                     "A2A SDK client not initialized"
        178:                 )
        179: 


   ... and 35 more events in this category


====================================================================================================
NEEDS_REVIEW: 3 events
====================================================================================================

1. ConversationEvents.AGENT_TOOL_CHAIN_COMPLETED [INFO]
   Location: src/muxi/formation/agents/agent.py:2134
   Description: Tool chain completed after {iteration} iterations and {total_tool_calls} tool calls
   Recommendation: REVIEW - Consider DEBUG level for granular processing steps

   CODE CONTEXT:
       2124:                     level=observability.EventLevel.WARNING,
       2125:                     data={
       2126:                         "agent_id": self.agent_id,
       2127:                         "error": str(e),
       2128:                     },
       2129:                     description=f"Failed to extract artifacts: {e}",
       2130:                 )
       2131: 
       2132:         # Emit tool chain completed event
       2133:         if iteration > 0:  # Only emit if we actually did tool chaining
   >>> 2134:             observability.observe(
       2135:                 event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_COMPLETED,
       2136:                 level=observability.EventLevel.INFO,
       2137:                 data={
       2138:                     "agent_id": self.agent_id,
       2139:                     "chain_id": chain_id,
       2140:                     "total_iterations": iteration,
       2141:                     "total_tool_calls": total_tool_calls,
       2142:                     "total_errors": len(error_history),
       2143:                     "reached_iteration_limit": iteration >= max_iterations,
       2144:                     "reached_call_limit": total_tool_calls >= max_total_calls,


2. ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_COMPLETED [INFO]
   Location: src/muxi/formation/agents/agent.py:2080
   Description: Tool chain iteration {iteration + 1} completed
   Recommendation: REVIEW - Consider DEBUG level for granular processing steps

   CODE CONTEXT:
       2070:                         current_content = (
       2071:                             reconsider_response["choices"][0]["message"].get("content", "") or ""
       2072:                         )
       2073:                     else:
       2074:                         current_content = str(reconsider_response)
       2075: 
       2076:                     current_raw_response = reconsider_response
       2077:                     content = current_content
       2078: 
       2079:             # Emit tool chain iteration completed event
   >>> 2080:             observability.observe(
       2081:                 event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_COMPLETED,
       2082:                 level=observability.EventLevel.INFO,
       2083:                 data={
       2084:                     "agent_id": self.agent_id,
       2085:                     "chain_id": chain_id,
       2086:                     "iteration": iteration + 1,
       2087:                     "tool_calls_executed": len(tool_results),
       2088:                     "errors_encountered": len(current_errors),
       2089:                     "total_tool_calls": total_tool_calls,
       2090:                     "continuing": bool(self._extract_tool_calls(current_raw_response)),


3. ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_STARTED [INFO]
   Location: src/muxi/formation/agents/agent.py:1778
   Description: Tool chain iteration {iteration + 1} started with {len(tool_calls)} tool calls
   Recommendation: REVIEW - Consider DEBUG level for granular processing steps

   CODE CONTEXT:
       1768:             elif isinstance(current_raw_response, dict) and "choices" in current_raw_response:
       1769:                 message = current_raw_response["choices"][0]["message"]
       1770:                 if "tool_calls" in message and message["tool_calls"]:
       1771:                     tool_calls = message["tool_calls"]
       1772: 
       1773:             # If no tool calls, break the loop
       1774:             if not tool_calls:
       1775:                 break
       1776: 
       1777:             # Emit tool chain iteration started event
   >>> 1778:             observability.observe(
       1779:                 event_type=observability.ConversationEvents.AGENT_TOOL_CHAIN_ITERATION_STARTED,
       1780:                 level=observability.EventLevel.INFO,
       1781:                 data={
       1782:                     "agent_id": self.agent_id,
       1783:                     "chain_id": chain_id,
       1784:                     "iteration": iteration + 1,
       1785:                     "total_iterations": max_iterations,
       1786:                     "tool_calls_count": len(tool_calls),
       1787:                     "total_tool_calls_so_far": total_tool_calls,
       1788:                     "has_previous_errors": len(error_history) > 0,
