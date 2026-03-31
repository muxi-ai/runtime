import re
from typing import Any, Dict, List, Optional, Tuple

from ...datatypes.workflow import (
    ApprovalStatus,
    RequestAnalysis,
    SubTask,
    TaskStatus,
    Workflow,
    WorkflowStatus,
    build_execution_phases,
    generate_task_id,
    generate_workflow_id,
    validate_workflow_dag,
)
from ...services import observability
from ...services.llm import LLM


class TaskDecomposer:
    """
    Core decomposition engine using advanced prompting strategies.

    Breaks down complex requests into executable workflows with plan preview
    capabilities for user approval.
    """

    def __init__(
        self, llm: Optional[LLM] = None, agent_registry: Optional[Dict] = None, mcp_service=None
    ):
        """
        Initialize the task decomposer.

        Args:
            llm: Optional LLM for intelligent decomposition. Falls back to heuristics if None.
            agent_registry: Registry of available agents with their capabilities
            mcp_service: MCP service for discovering available tools
        """
        self.llm = llm
        self.agent_registry = agent_registry or {}
        self.mcp_service = mcp_service

    async def decompose_request(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None,
        requires_approval: bool = False,
    ) -> Workflow:
        """
        Break down complex request into executable workflow.

        Strategy:
        1. Chain-of-thought analysis of request requirements
        2. Identify logical steps and dependencies
        3. Map steps to capability requirements
        4. Generate task graph with validation
        5. Optimize for parallel execution where possible
        6. Generate human-readable plan if approval required

        Args:
            request: User's original request
            context: Optional conversation context
            analysis: Optional pre-computed request analysis
            requires_approval: Whether to generate plan preview for approval

        Returns:
            Workflow with tasks and optional plan preview
        """
        try:
            workflow_id = generate_workflow_id()

            # For template-mode SOPs, attempt deterministic parsing first.
            # The enhanced_message from overlord wraps the SOP in <sop>...</sop> and the
            # original request in <user_request>...</user_request>.
            workflow = None
            if context and context.get("sop_mode") == "template":
                sop_match = re.search(r"<sop>\s*(.*?)\s*</sop>", request, re.DOTALL)
                user_req_match = re.search(
                    r"<user_request>\s*(.*?)\s*</user_request>", request, re.DOTALL
                )
                if sop_match:
                    sop_content = sop_match.group(1)
                    user_request_text = user_req_match.group(1) if user_req_match else request
                    workflow = self._parse_template_sop_deterministic(
                        sop_content=sop_content,
                        user_request=user_request_text,
                        sop_id=context.get("sop_id", ""),
                    )

            if workflow is None:
                if self.llm:
                    # Use LLM for sophisticated decomposition
                    workflow = await self._llm_decompose_request(
                        workflow_id, request, context, analysis
                    )
                else:
                    # Fall back to heuristic decomposition
                    workflow = self._heuristic_decompose_request(workflow_id, request, analysis)

            # Generate plan preview if user approval required
            if requires_approval:
                workflow.requires_approval = True
                workflow.plan_preview = await self._generate_plan_preview(workflow, request)
                workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

            # Validate workflow structure
            validated_workflow = self._validate_workflow(workflow)

            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow_id,
                    "task_count": len(validated_workflow.tasks),
                    "requires_approval": validated_workflow.requires_approval,
                },
                description=(
                    f"Decomposed request into workflow {workflow_id} with "
                    f"{len(validated_workflow.tasks)} tasks"
                ),
            )

            return validated_workflow

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "decompose_request",
                },
                description="Workflow decomposition failed, using fallback workflow",
            )
            # Return minimal fallback workflow
            return self._create_fallback_workflow(request)

    async def modify_workflow(
        self,
        workflow: Workflow,
        modification_instructions: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """
        Modify an existing workflow based on user feedback.

        Args:
            workflow: Original workflow to modify
            modification_instructions: User's requested changes
            context: Optional context for modifications

        Returns:
            Modified workflow with updated plan preview
        """
        try:
            if self.llm:
                modified_workflow = await self._llm_modify_workflow(
                    workflow, modification_instructions, context
                )
            else:
                # Simple heuristic modification
                modified_workflow = self._heuristic_modify_workflow(
                    workflow, modification_instructions
                )

            # Regenerate plan preview
            modified_workflow.plan_preview = await self._generate_plan_preview(
                modified_workflow, workflow.user_request
            )
            modified_workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

            return self._validate_workflow(modified_workflow)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "modify_workflow",
                },
                description="Workflow modification failed, returning original",
            )
            return workflow  # Return original on error

    async def _generate_plan_preview(self, workflow: Workflow, original_request: str) -> str:
        """
        Generate human-readable plan preview for user approval.

        Args:
            workflow: Workflow to generate preview for
            original_request: Original user request

        Returns:
            Human-readable plan description
        """
        if self.llm:
            return await self._llm_generate_plan_preview(workflow, original_request)
        else:
            return self._heuristic_generate_plan_preview(workflow, original_request)

    async def _llm_decompose_request(
        self,
        workflow_id: str,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None,
    ) -> Workflow:
        """
        Use LLM to decompose request into workflow.

        Args:
            workflow_id: Unique workflow identifier
            request: User's request
            context: Optional conversation context
            analysis: Optional pre-computed analysis

        Returns:
            LLM-generated workflow
        """
        # Safety: Truncate very large requests to prevent recursion in LLM processing
        # Large requests with deeply nested context can cause stack overflow
        max_request_length = 50000  # 50k chars should be plenty
        truncated_request = (
            request
            if len(request) <= max_request_length
            else (request[:max_request_length] + "\n\n[... request truncated for safety ...]")
        )

        system_prompt, user_content = self._create_decomposition_messages(
            truncated_request, context, analysis
        )

        # Skip observability call that might trigger recursion
        # Debug logging is commented out to avoid potential issues:
        # prompt_length = len(system_prompt) + len(user_content)
        # print(f"🔍 Decomposition prompt size: {prompt_length:,} chars, request size: {len(request):,} chars")

        try:
            # Event 5: COMMENTED OUT - duplicate planning event
            from ...services import streaming  # Still need import for other uses

            # streaming.stream(
            #     "planning",
            #     "Analyzing how to break down this complex request...",
            #     stage="decomposition_start",
            #     complexity_score=analysis.complexity_score if analysis else None,
            #     request_type=analysis.request_type if analysis and hasattr(analysis, 'request_type') else None
            # )
            # Safety check: Limit prompt size to prevent recursion issues
            # Very large prompts (>100k chars) can cause recursion in LLM processing
            total_size = len(system_prompt) + len(user_content)
            if total_size > 100000:
                raise ValueError(
                    f"Decomposition prompt too large ({total_size} chars), using heuristic"
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            response_obj = await self.llm.chat(messages, max_tokens=2000)

            # Check cancellation after LLM call
            from ..background.cancellation import check_cancellation_from_context

            if context and context.get("request_tracker"):
                await check_cancellation_from_context(context["request_tracker"])

            response = (
                response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            )

            # # DEBUG: Print LLM response for debugging
            # print("\n" + "🤖 LLM DECOMPOSITION RESPONSE:")
            # print("=" * 80)
            # print(response)
            # print("=" * 80)

            workflow = self._parse_llm_decomposition(workflow_id, request, response)

            # DEBUG: Print parsed workflow info
            # print(f"\n📋 PARSED WORKFLOW: {len(workflow.tasks)} tasks")
            # for task_id, task in workflow.tasks.items():
            #     print(f"  - {task_id}: {task.description}")
            #     print(f"    Capabilities: {task.required_capabilities}")
            # print()

            # Emit streaming event with decomposition results
            streaming.stream(
                "planning",
                f"I've broken this down into {len(workflow.tasks)} tasks to complete.",
                stage="decomposition_complete",
                task_count=len(workflow.tasks),
                workflow_id=workflow.id if workflow else None,
                decomposition_details=response,
                is_llm_response=True,
            )

            return workflow

        except RecursionError:
            # Handle RecursionError specially to avoid cascading logging errors
            # This can occur with very large/complex prompts
            print("\n⚠️  LLM decomposition hit recursion limit, using heuristic decomposition")

            # Emit streaming event without trying to stringify the error
            # (which could trigger more recursion)
            streaming.stream(
                "planning",
                "Using alternative approach to break down the request...",
                stage="decomposition_fallback",
                error_reason="Recursion limit exceeded",
            )

            return self._heuristic_decompose_request(workflow_id, request, analysis)

        except Exception as e:
            # Log decomposition failure and fall back to heuristic
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "workflow_id": workflow_id,
                    "error_type": type(e).__name__,
                    "error": str(e)[:200],  # Truncate long errors
                    "fallback": "heuristic_decomposition",
                    "request_length": len(request),
                },
                description="LLM-based workflow decomposition failed, falling back to heuristic decomposition",
            )

            # Keep stderr output for immediate visibility
            import sys

            sys.stderr.write(f"\n⚠️  LLM decomposition failed: {type(e).__name__}\n")
            sys.stderr.write("   Falling back to heuristic decomposition\n")
            sys.stderr.flush()

            # Emit streaming event for fallback
            # Sanitize and truncate error message for streaming
            error_msg = str(e).strip() if e else ""
            if error_msg:
                # Remove newlines and limit length
                error_msg = error_msg.replace("\n", " ").replace("\r", "")[:200]
            else:
                error_msg = "LLM decomposition failed"

            streaming.stream(
                "planning",
                "Using alternative approach to break down the request...",
                stage="decomposition_fallback",
                error_reason=error_msg,
            )

            return self._heuristic_decompose_request(workflow_id, request, analysis)

    def _create_decomposition_messages(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None,
    ) -> tuple:
        """
        Create system and user messages for LLM decomposition.

        Args:
            request: User's request
            context: Optional conversation context
            analysis: Optional analysis results

        Returns:
            Tuple of (system_prompt, user_content) for proper caching
        """
        # Read the prompt template from PromptLoader
        from ..prompts.loader import PromptLoader

        try:
            template = PromptLoader.get("decomposition_prompt.md")
        except KeyError:
            # Fallback to basic template if file not found
            template = (
                "<user_request>{{request}}</user_request>\n"
                "<context>{{context_info}}</context>\n"
                "<analysis>{{analysis_info}}</analysis>\n"
                "<capabilities>{{capabilities_info}}</capabilities>"
            )

        # Prepare context info
        context_info = ""
        if context:
            # Safety: Ensure context doesn't contain circular references
            # Convert to string carefully to avoid recursion
            try:
                # Limit context representation to prevent recursion
                if isinstance(context, dict):
                    # Only include safe, simple values
                    safe_context = {}
                    for k, v in context.items():
                        if isinstance(v, (str, int, float, bool, list, tuple)):
                            safe_context[k] = v
                        else:
                            safe_context[k] = str(type(v).__name__)
                    context_info = f"\nContext: {safe_context}"
                else:
                    context_info = f"\nContext: {type(context).__name__}"
            except Exception as e:
                # Log context serialization failure for debugging
                observability.observe(
                    event_type=observability.SystemEvents.EXTENSION_FAILED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "context_type": type(context).__name__ if context else None,
                    },
                    description=f"Failed to serialize context for decomposition: {str(e)}",
                )
                context_info = "\nContext: <unavailable>"

        # Prepare analysis info
        analysis_info = ""
        if analysis:
            analysis_info = f"""
Analysis Results:
- Complexity Score: {analysis.complexity_score}/10
- Required Capabilities: {', '.join(analysis.required_capabilities)}
- Implicit Subtasks: {', '.join(analysis.implicit_subtasks)}
"""

        capabilities_info = self._get_available_capabilities_info()

        # System prompt: template with placeholder for request (instructions)
        system_prompt = (
            template.replace("{{request}}", "[USER REQUEST BELOW]")
            .replace("{{context_info}}", context_info)
            .replace("{{analysis_info}}", analysis_info)
            .replace("{{capabilities_info}}", capabilities_info)
        )

        # User content: the actual request
        return system_prompt, request

    def _get_available_capabilities_info(self) -> str:
        """
        Dynamically generate information about available agent capabilities and MCP tools.

        Returns:
            Formatted string with current agent capabilities and available tools
        """
        info_parts = ["Available agent capabilities and tools:\n"]

        # Get agent capabilities
        if self.agent_registry:

            info_parts.append("**Available Agents and Their Capabilities:**")
            for agent_id, agent in self.agent_registry.items():
                # Get all agent attributes
                agent_name = getattr(agent, "name", agent_id)
                agent_description = getattr(agent, "description", "")
                agent_role = getattr(agent, "role", "general")

                # Try multiple ways to get specialties/capabilities
                specialties = (
                    getattr(agent, "specialization", None)
                    or getattr(agent, "specialties", None)
                    or getattr(agent, "capabilities", None)
                    or []
                )

                # Format agent info with name, description, and capabilities
                info_parts.append(f"\n**{agent_name}** (ID: {agent_id})")
                if agent_description:
                    info_parts.append(f"  Description: {agent_description}")
                info_parts.append(f"  Role: {agent_role}")

                if specialties:
                    specialty_list = ", ".join(specialties)
                    info_parts.append(f"  Capabilities: {specialty_list}")
                else:
                    info_parts.append("  Capabilities: general-purpose")

                # Add "Best for" only when no description exists but specialties do
                if not agent_description and specialties:
                    # Generic description based on capabilities
                    capability_str = ", ".join(specialties)
                    info_parts.append(f"  Best for: Tasks requiring {capability_str} capabilities")

            info_parts.append("")
        else:
            info_parts.append("**No agent registry available**")
            info_parts.append("")

        # Get MCP tool capabilities
        if self.mcp_service:
            try:
                # Get available servers and their tools
                servers = getattr(self.mcp_service, "servers", {})
                if servers:
                    info_parts.append("**Available MCP Tools:**")
                    for server_id, server_info in servers.items():
                        capabilities = (
                            server_info.get("capabilities", [])
                            if isinstance(server_info, dict)
                            else []
                        )
                        if capabilities:
                            cap_list = ", ".join(capabilities)
                            info_parts.append(f"- {server_id}: {cap_list}")
                    info_parts.append("")
            except Exception:
                # If MCP introspection fails, continue without it
                pass

        # Add dynamic guidance for task mapping based on available capabilities
        info_parts.append("**Task Mapping Guidelines:**")

        # Collect all unique capabilities
        all_capabilities = set()
        capability_examples = {}

        if self.agent_registry:
            for agent_id, agent in self.agent_registry.items():
                specialties = (
                    getattr(agent, "specialization", None)
                    or getattr(agent, "specialties", None)
                    or getattr(agent, "capabilities", None)
                    or []
                )
                for capability in specialties:
                    all_capabilities.add(capability)
                    if capability not in capability_examples:
                        capability_examples[capability] = getattr(agent, "name", agent_id)

        # Generate dynamic guidelines based on actual capabilities
        info_parts.append("- Match task requirements to agent capabilities listed above")
        info_parts.append("- Consider each agent's description and what they're 'Best for'")

        # Add specific guidance for known capability patterns
        # Find actual research-related capabilities
        research_caps = [cap for cap in all_capabilities if "research" in cap.lower()]
        if research_caps:
            caps_str = "' or '".join(research_caps)
            info_parts.append(f"- Research/info gathering → use capability: '{caps_str}'")

        # Find actual writing-related capabilities
        writing_caps = [
            cap
            for cap in all_capabilities
            if "writing" in cap.lower() or "documentation" in cap.lower()
        ]
        if writing_caps:
            caps_str = "' or '".join(writing_caps)
            info_parts.append(f"- Content creation/docs → use capability: '{caps_str}'")

        if "analysis" in all_capabilities or "data_analysis" in all_capabilities:
            info_parts.append(
                "- Data analysis → use capability: 'analysis' or 'data_analysis' exactly as shown"
            )

        # Check for platform capabilities (without hardcoding specific platforms)
        platform_capabilities = [
            cap
            for cap in all_capabilities
            if cap
            not in [
                "research",
                "writing",
                "analysis",
                "coding",
                "development",
                "general",
                "web_search",
                "documentation",
                "data_analysis",
            ]
        ]

        if platform_capabilities:
            cap_list = ", ".join(platform_capabilities)
            info_parts.append(f"- Platform operations (issues, tickets) → use EXACTLY: {cap_list}")
            info_parts.append(
                "- DO NOT use 'project-management' or 'issue-tracking' - use the exact capability name shown above"
            )
            info_parts.append(
                "- Platform operations are simple API calls (complexity 1-3), NOT coding tasks"
            )

        if "coding" in all_capabilities or "development" in all_capabilities:
            info_parts.append(
                "- Software development → agents with 'coding'/'development' capabilities"
            )
            info_parts.append("- Only use coding agents for actual development, not API operations")

        info_parts.append("")

        return "\n".join(info_parts)

    def _parse_llm_decomposition(self, workflow_id: str, request: str, response: str) -> Workflow:
        """
        Parse LLM decomposition response into Workflow object.

        Args:
            workflow_id: Workflow identifier
            request: Original user request
            response: LLM decomposition response

        Returns:
            Parsed Workflow object
        """
        try:
            tasks = {}

            # Extract tasks section - handle markdown formatting
            # LLM may use "## TASKS", "### TASKS:", "**TASKS:**", or "TASKS:" formats
            tasks_section = re.search(
                r"#{2,3}\s*TASKS:?(.*?)(?=#{2,3}\s*EXECUTION_STRATEGY|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if not tasks_section:
                tasks_section = re.search(
                    r"\*\*TASKS:?\*\*(.*?)(?=\*\*EXECUTION_STRATEGY:?\*\*|$)",
                    response,
                    re.DOTALL | re.IGNORECASE,
                )
            if not tasks_section:
                # Fallback to plain text format
                tasks_section = re.search(
                    r"TASKS:?(.*?)(?=EXECUTION_STRATEGY:?|$)", response, re.DOTALL | re.IGNORECASE
                )
            if not tasks_section:
                # Fallback if structure is different
                print("⚠️  WARNING: Could not find TASKS section in LLM response")
                print(f"Response preview: {response[:500]}...")
                return self._heuristic_decompose_request(workflow_id, request)

            tasks_text = tasks_section.group(1)

            # Parse individual tasks - handle markdown formatting and numbered lists
            # Try different patterns to split tasks
            task_blocks = re.split(r"\d+\.\s*\*\*Task_ID\*\*:\s*", tasks_text)
            if len(task_blocks) == 1:
                task_blocks = re.split(r"-\s*\*\*Task_ID\*\*:\s*", tasks_text)
            if len(task_blocks) == 1:
                task_blocks = re.split(r"\*\*Task_ID:\*\*", tasks_text)
            if len(task_blocks) == 1:
                # Split on markdown headers like "### Task_1" or "### Task_1:"
                task_blocks = re.split(r"###\s*Task_\d+:?\s*\n", tasks_text)
            if len(task_blocks) == 1:
                # Fallback to plain text format
                task_blocks = re.split(r"Task_ID:\s*", tasks_text)
            task_blocks = task_blocks[1:]  # Skip empty first element

            for block in task_blocks:
                try:
                    task = self._parse_task_block(block.strip())
                    if task:
                        if task.id in tasks:
                            # Duplicate task IDs indicate malformed LLM output; keep first occurrence.
                            observability.observe(
                                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                                level=observability.EventLevel.WARNING,
                                data={
                                    "task_id": task.id,
                                    "operation": "parse_task_block",
                                },
                                description=f"Duplicate task ID '{task.id}' in LLM output; keeping first",
                            )
                        else:
                            tasks[task.id] = task
                except Exception as e:
                    observability.observe(
                        event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "error_type": type(e).__name__,
                            "error": str(e),
                            "operation": "parse_task_block",
                        },
                        description="Failed to parse individual task block, skipping",
                    )
                    continue

            if not tasks:
                return self._heuristic_decompose_request(workflow_id, request)

            # Strip dependency references that point to non-existent tasks.
            # These arise when the LLM hallucinates task IDs or when the parser
            # drops a block, turning valid deps into phantom refs that
            # validate_workflow_dag() mistakes for cycles.
            valid_ids = set(tasks.keys())
            phantom_deps_found = False
            for task in tasks.values():
                filtered = [d for d in task.dependencies if d in valid_ids]
                if len(filtered) != len(task.dependencies):
                    phantom_deps_found = True
                    task.dependencies = filtered
            if phantom_deps_found:
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "workflow_id": workflow_id,
                        "operation": "strip_phantom_deps",
                    },
                    description="Stripped dependency references to non-existent tasks from LLM output",
                )

            workflow = Workflow(
                id=workflow_id, user_request=request, tasks=tasks, status=WorkflowStatus.PENDING
            )

            return workflow

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "llm_decompose",
                },
                description="LLM decomposition failed, using heuristic fallback",
            )
            return self._heuristic_decompose_request(workflow_id, request)

    def _parse_task_block(self, block: str) -> Optional[SubTask]:
        """
        Parse individual task block from LLM response.

        Args:
            block: Text block for one task

        Returns:
            Parsed SubTask or None if parsing fails
        """
        try:
            lines = block.split("\n")
            task_data = {}

            for line in lines:
                # Skip empty lines
                if not line.strip():
                    continue
                # Handle lines with dashes and stars
                line = line.strip().lstrip("-").strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    # Clean up markdown formatting from key and value
                    key = key.strip().lower().replace(" ", "_").replace("*", "")
                    value = value.strip().replace("*", "").strip()
                    task_data[key] = value

            # Extract required fields
            task_id = task_data.get("task_id", generate_task_id())
            description = task_data.get("description", "Task description")

            # Parse capabilities
            capabilities_text = task_data.get("required_capabilities", "general")
            if capabilities_text.startswith("[") and capabilities_text.endswith("]"):
                capabilities_text = capabilities_text[1:-1]
            required_capabilities = [cap.strip() for cap in capabilities_text.split(",")]

            # Parse dependencies
            dependencies_text = task_data.get("dependencies", "none")
            dependencies = []
            if dependencies_text.lower() != "none":
                if dependencies_text.startswith("[") and dependencies_text.endswith("]"):
                    dependencies_text = dependencies_text[1:-1]
                dependencies = [dep.strip() for dep in dependencies_text.split(",") if dep.strip()]

            # Parse complexity
            complexity = 5.0
            try:
                complexity = float(task_data.get("estimated_complexity", 5.0))
            except (ValueError, TypeError):
                pass

            # Parse assigned agent (from SOP [agent:name] directives in template mode)
            # The LLM may output "Agent:", "Assigned_Agent:", or "Assigned Agent:" —
            # after key normalization these become "agent", "assigned_agent", etc.
            assigned_agent = task_data.get("assigned_agent") or task_data.get("agent") or None
            if assigned_agent and assigned_agent.lower() == "none":
                assigned_agent = None

            return SubTask(
                id=task_id,
                description=description,
                required_capabilities=required_capabilities,
                dependencies=dependencies,
                estimated_complexity=complexity,
                assigned_agent_id=assigned_agent,
                status=TaskStatus.PENDING,
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "parse_task",
                },
                description="Failed to parse task from block",
            )
            return None

    def _heuristic_decompose_request(
        self, workflow_id: str, request: str, analysis: Optional[RequestAnalysis] = None
    ) -> Workflow:
        """
        Use heuristic rules to decompose request when LLM is unavailable.

        Args:
            workflow_id: Workflow identifier
            request: User's request
            analysis: Optional analysis results

        Returns:
            Heuristically-generated workflow
        """
        request_lower = request.lower()
        tasks = {}

        # Common task patterns
        task_patterns = [
            {
                "keywords": ["research", "investigate", "study", "analyze"],
                "description": "Research and gather information",
                "capabilities": ["research", "web_search"],
                "complexity": 6,
            },
            {
                "keywords": ["write", "draft", "create", "compose"],
                "description": "Create written content",
                "capabilities": ["writing"],
                "complexity": 7,
                "dependencies": [],  # Will be set based on other tasks
            },
            {
                "keywords": ["analyze", "process", "examine"],
                "description": "Analyze data and information",
                "capabilities": ["data_analysis"],
                "complexity": 6,
            },
            {
                "keywords": ["implement", "build", "develop", "code"],
                "description": "Implement solution",
                "capabilities": ["coding", "development"],
                "complexity": 8,
            },
            {
                "keywords": ["design", "mockup", "wireframe"],
                "description": "Create design deliverables",
                "capabilities": ["design"],
                "complexity": 6,
            },
        ]

        # Generate tasks based on patterns found
        task_counter = 1
        for pattern in task_patterns:
            if any(keyword in request_lower for keyword in pattern["keywords"]):
                task_id = f"tsk_{task_counter}"

                # Set dependencies (writing usually comes after research)
                dependencies = []
                if "writing" in pattern["capabilities"] and any(
                    t for t in tasks.values() if "research" in t.required_capabilities
                ):
                    dependencies = [
                        t.id for t in tasks.values() if "research" in t.required_capabilities
                    ]

                task = SubTask(
                    id=task_id,
                    description=pattern["description"],
                    required_capabilities=pattern["capabilities"],
                    dependencies=dependencies,
                    estimated_complexity=pattern["complexity"],
                    status=TaskStatus.PENDING,
                )

                tasks[task_id] = task
                task_counter += 1

        # If no patterns matched, create a general task
        if not tasks:
            task = SubTask(
                id="task_1",
                description=f"Complete request: {request[:100]}...",
                required_capabilities=["general"],
                dependencies=[],
                estimated_complexity=5.0,
                status=TaskStatus.PENDING,
            )
            tasks["task_1"] = task

        return Workflow(
            id=workflow_id, user_request=request, tasks=tasks, status=WorkflowStatus.PENDING
        )

    async def _llm_generate_plan_preview(self, workflow: Workflow, original_request: str) -> str:
        """
        Generate human-readable plan preview using LLM.

        Args:
            workflow: Workflow to preview
            original_request: Original user request

        Returns:
            Human-readable plan preview
        """
        try:
            system_prompt = (
                "Convert technical workflows into clear plans that users can easily understand and approve.\n\n"
                "Instructions:\n"
                '1. Start with "Here\'s my proposed approach for your request:"\n'
                "2. Explain the workflow steps in logical order\n"
                "3. Mention which specialists will be involved for each phase\n"
                "4. IMPORTANT: Preserve the exact task descriptions from the workflow - do NOT reinterpret or rename them\n"  # noqa: E501
                '5. If a task involves creating issues/tickets on any platform, keep that description - do NOT call it "Implement Solution" or "Development"\n'  # noqa: E501
                "6. Explain why this approach makes sense\n"
                '7. End with "Does this approach work for you? Should I proceed with this plan?"\n\n'
                "Use a direct, professional tone. Accurately represent what each task will do based on its description.\n"  # noqa: E501
                "Keep it concise but comprehensive.\n\n"
                "IMPORTANT: Always reply in the same language as the user's original request\n"
            )

            user_content = (
                f"Original Request: {original_request}\n\n"
                f"Technical Workflow:\n"
                f"{self._workflow_to_text(workflow)}"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            response_obj = await self.llm.chat(messages, max_tokens=800)
            plan_preview = (
                response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            )
            return plan_preview

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "generate_plan_preview",
                },
                description="LLM plan preview generation failed, using heuristic",
            )
            return self._heuristic_generate_plan_preview(workflow, original_request)

    def _heuristic_generate_plan_preview(self, workflow: Workflow, original_request: str) -> str:
        """
        Generate basic plan preview using heuristics.

        Args:
            workflow: Workflow to preview
            original_request: Original user request

        Returns:
            Basic plan preview
        """
        try:
            # Build execution phases for logical ordering
            try:
                phases = build_execution_phases(workflow)
            except Exception:
                # Fallback if dependency resolution fails
                phases = [[task_id for task_id in workflow.tasks.keys()]]

            plan_lines = [
                f'Here\'s my plan to handle your request: "{original_request}"\n',
                "## Proposed Approach\n",
            ]

            for i, phase in enumerate(phases, 1):
                if len(phases) > 1:
                    plan_lines.append(f"### Phase {i}:")

                for task_id in phase:
                    task = workflow.tasks[task_id]
                    capabilities_str = ", ".join(task.required_capabilities)
                    plan_lines.append(f"- {task.description} (using {capabilities_str})")

                if len(phases) > 1:
                    plan_lines.append("")

            # Estimate timeline
            total_complexity = sum(task.estimated_complexity for task in workflow.tasks.values())
            estimated_minutes = total_complexity * 0.5  # Rough estimate

            if estimated_minutes < 5:
                time_estimate = "under 5 minutes"
            elif estimated_minutes < 10:
                time_estimate = "5-10 minutes"
            elif estimated_minutes < 30:
                time_estimate = "15-30 minutes"
            elif estimated_minutes < 60:
                time_estimate = "30-60 minutes"
            else:
                time_estimate = f"{estimated_minutes//60}+ hours"

            plan_lines.extend(
                [
                    f"\n**Estimated completion time is {time_estimate}**\n",
                    "Does this approach work for you? "
                    "Would you like me to proceed, or should I adjust anything?",
                ]
            )

            return "\n".join(plan_lines)

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "heuristic_plan_preview",
                },
                description="Heuristic plan preview generation failed",
            )
            return f"""
I'll work on your request: "{original_request}"

My approach will involve {len(workflow.tasks)} main tasks to complete this work effectively.

Would you like me to proceed with this plan?
"""

    def _workflow_to_text(self, workflow: Workflow) -> str:
        """
        Convert workflow to text representation for prompts.

        Args:
            workflow: Workflow to convert

        Returns:
            Text representation of workflow
        """
        lines = []
        for task_id, task in workflow.tasks.items():
            lines.append(f"Task {task_id}: {task.description}")
            lines.append(f"  Capabilities: {', '.join(task.required_capabilities)}")
            lines.append(
                f"  Dependencies: {', '.join(task.dependencies) if task.dependencies else 'None'}"
            )
            lines.append(f"  Complexity: {task.estimated_complexity}/10")
            lines.append("")

        return "\n".join(lines)

    def _validate_workflow(self, workflow: Workflow) -> Workflow:
        """
        Validate and potentially fix workflow structure.

        Args:
            workflow: Workflow to validate

        Returns:
            Validated workflow
        """
        try:
            # Validate DAG structure
            if not validate_workflow_dag(workflow):
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "workflow_id": workflow.id,
                        "operation": "validate_dag",
                    },
                    description="Workflow contains cycles, attempting to fix",
                )
                workflow = self._fix_workflow_cycles(workflow)

            # Build execution phases
            try:
                build_execution_phases(workflow)
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "workflow_id": workflow.id,
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "operation": "build_execution_phases",
                    },
                    description="Failed to build execution phases for workflow",
                )

            return workflow

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow.id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "validate_workflow",
                },
                description="Workflow validation failed, returning unvalidated workflow",
            )
            return workflow

    # Compiled regexes for the deterministic SOP parser (module-level singletons via class attrs)
    _SOP_HEADING_RE = re.compile(
        r'^(#{1,4})\s+(.+?)\s*$',
        re.MULTILINE,
    )
    _SOP_STEP_TITLE_RE = re.compile(
        r'^(?:Step\s+)?(\d+)(?:\s*[:\.]\s*(.+))?$',
        re.IGNORECASE,
    )
    _SOP_AGENT_RE = re.compile(r'\[agent:([^\]]+)\]', re.IGNORECASE)
    _SOP_MCP_RE = re.compile(r'\[mcp:([^\]]+)\]', re.IGNORECASE)
    _SOP_PARALLEL_RE = re.compile(r'\[parallel\]', re.IGNORECASE)
    _SOP_DIRECTIVE_RE = re.compile(r'\[[^\]]+\]')

    def _parse_template_sop_deterministic(
        self, sop_content: str, user_request: str, sop_id: str = ""
    ) -> Optional[Workflow]:
        """
        Parse a template-mode SOP markdown directly into a Workflow without LLM involvement.

        Handles:
        - ## Step N / ### Step N headings (with optional `: Title`)
        - [agent:name] -> assigned_agent_id
        - [mcp:tool]   -> required_capabilities hint
        - [parallel]   -> step has no prior dependencies (parallel group)
        - Section headings containing "parallel" -> all step children are parallel

        Steps default to sequential (step N depends on N-1).  A step with [parallel] or
        under a "parallel" section header has no dependencies; the first non-parallel step
        after such a group depends on all members of that group (fan-in).

        Returns None when fewer than 2 steps are detected (caller falls back to LLM).
        """
        # Strip YAML frontmatter if present
        content = sop_content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        # Collect all headings with position, level, title, step metadata
        all_headings: List[Dict] = []
        for m in self._SOP_HEADING_RE.finditer(content):
            level = len(m.group(1))
            title = m.group(2).strip()
            step_m = self._SOP_STEP_TITLE_RE.match(title)
            is_step = bool(step_m)
            all_headings.append(
                {
                    "pos": m.start(),
                    "end": m.end(),
                    "level": level,
                    "title": title,
                    "is_step": is_step,
                    "step_num": int(step_m.group(1)) if step_m else None,
                    "step_title": (
                        (step_m.group(2) or "").strip() if step_m else ""
                    ),
                    "is_parallel_section": (
                        "parallel" in title.lower() and not is_step
                    ),
                }
            )

        step_headings = [h for h in all_headings if h["is_step"]]
        if len(step_headings) < 2:
            return None

        # Determine which step numbers fall under a "parallel" section heading.
        # A parallel section spans from its heading to the next same-or-higher-level heading.
        parallel_from_section: set = set()
        for h in all_headings:
            if not h["is_parallel_section"]:
                continue
            section_end = len(content)
            for other in all_headings:
                if other["pos"] > h["pos"] and other["level"] <= h["level"] and not other["is_step"]:
                    section_end = other["pos"]
                    break
            for sh in step_headings:
                if h["end"] <= sh["pos"] < section_end:
                    parallel_from_section.add(sh["step_num"])

        # Extract body text and directives for each step
        steps: List[Dict] = []
        for i, sh in enumerate(step_headings):
            body_start = sh["end"]
            # Body ends at the next heading (step or otherwise)
            next_pos = len(content)
            for other in all_headings:
                if other["pos"] > sh["pos"] and other["pos"] < next_pos:
                    next_pos = other["pos"]
            body = content[body_start:next_pos].strip()

            agent_m = self._SOP_AGENT_RE.search(body)
            assigned_agent = agent_m.group(1).strip() if agent_m else None
            mcp_tools = [m.group(1).strip() for m in self._SOP_MCP_RE.finditer(body)]
            is_parallel = (
                bool(self._SOP_PARALLEL_RE.search(body))
                or sh["step_num"] in parallel_from_section
            )

            # Clean description: strip directive tags, collapse excessive blank lines
            description = self._SOP_DIRECTIVE_RE.sub("", body).strip()
            description = re.sub(r"\n{3,}", "\n\n", description)
            if not description:
                description = sh["step_title"] or f"Step {sh['step_num']}"
            if len(description) > 500:
                description = description[:500].rsplit(" ", 1)[0] + "..."
            if sh["step_title"]:
                description = f"{sh['step_title']}: {description}"

            steps.append(
                {
                    "num": sh["step_num"],
                    "description": description,
                    "assigned_agent": assigned_agent,
                    "mcp_tools": mcp_tools,
                    "is_parallel": is_parallel,
                }
            )

        if len(steps) < 2:
            return None

        # Build SubTask objects with dependency logic
        workflow_id = generate_workflow_id()
        tasks: Dict[str, SubTask] = {}
        task_id_list: List[str] = []
        parallel_group: List[str] = []

        for step in steps:
            task_id = f"task_{step['num']}"

            caps: List[str] = list(step["mcp_tools"])
            if not caps and step["assigned_agent"]:
                caps = [step["assigned_agent"]]
            if not caps:
                caps = ["general"]

            if step["is_parallel"]:
                deps: List[str] = []
                parallel_group.append(task_id)
            else:
                if parallel_group:
                    deps = list(parallel_group)
                    parallel_group = []
                elif task_id_list:
                    deps = [task_id_list[-1]]
                else:
                    deps = []

            tasks[task_id] = SubTask(
                id=task_id,
                description=step["description"],
                required_capabilities=caps,
                dependencies=deps,
                estimated_complexity=3.0,
                status=TaskStatus.PENDING,
                assigned_agent_id=step["assigned_agent"],
            )
            task_id_list.append(task_id)

        observability.observe(
            event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "workflow_id": workflow_id,
                "task_count": len(tasks),
                "method": "deterministic_sop_template",
                "sop_id": sop_id,
                "parallel_steps": len(parallel_from_section),
            },
            description=(
                f"Parsed SOP template deterministically: {len(tasks)} tasks, "
                f"{len(parallel_from_section)} parallel"
            ),
        )

        return Workflow(
            id=workflow_id,
            user_request=user_request,
            tasks=tasks,
            status=WorkflowStatus.PENDING,
        )

    def _fix_workflow_cycles(self, workflow: Workflow) -> Workflow:
        """
        Attempt to fix circular dependencies in workflow.

        Args:
            workflow: Workflow with potential cycles

        Returns:
            Fixed workflow
        """
        # Simple fix: remove all dependencies and make tasks sequential
        task_ids = list(workflow.tasks.keys())

        for i, task_id in enumerate(task_ids):
            task = workflow.tasks[task_id]
            if i == 0:
                task.dependencies = []
            else:
                task.dependencies = [task_ids[i - 1]]

        observability.observe(
            event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "workflow_id": workflow.id,
                "task_count": len(workflow.tasks),
                "method": "fix_circular_dependencies",
            },
            description=f"Fixed circular dependencies in workflow {workflow.id}",
        )
        return workflow

    def _create_fallback_workflow(self, request: str) -> Workflow:
        """
        Create minimal fallback workflow when decomposition fails.

        Args:
            request: Original user request

        Returns:
            Simple fallback workflow
        """
        workflow_id = generate_workflow_id()
        task = SubTask(
            id="fallback_task",
            description=f"Handle request: {request}",
            required_capabilities=["general"],
            dependencies=[],
            estimated_complexity=5.0,
            status=TaskStatus.PENDING,
        )

        return Workflow(
            id=workflow_id,
            user_request=request,
            tasks={"fallback_task": task},
            status=WorkflowStatus.PENDING,
        )

    async def _llm_modify_workflow(
        self,
        workflow: Workflow,
        modification_instructions: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """
        Use LLM to modify workflow based on user feedback.

        Args:
            workflow: Original workflow
            modification_instructions: User's modification requests
            context: Optional context

        Returns:
            Modified workflow
        """
        # This is a placeholder for LLM-based workflow modification
        # For now, return the original workflow
        observability.observe(
            event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "workflow_id": workflow.id,
                "method": "llm_modify_workflow",
            },
            description=f"Modified workflow {workflow.id} using LLM",
        )
        return workflow

    def _heuristic_modify_workflow(
        self, workflow: Workflow, modification_instructions: str
    ) -> Workflow:
        """
        Simple heuristic workflow modification.

        Args:
            workflow: Original workflow
            modification_instructions: User's modification requests

        Returns:
            Modified workflow (currently just returns original)
        """
        # Simple heuristic modification - just return original for now
        observability.observe(
            event_type=observability.ConversationEvents.WORKFLOW_DECOMPOSITION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "workflow_id": workflow.id,
                "method": "heuristic_modify_workflow",
            },
            description=f"Modified workflow {workflow.id} using heuristic approach",
        )
        return workflow


class ApprovalManager:
    """Handle plan approval workflow"""

    async def present_plan_for_approval(self, workflow: Workflow) -> str:
        """Present plan to user and return formatted message"""

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_PLANNING_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "approval_manager_present",
                "workflow_id": workflow.id,
                "has_plan_preview": workflow.plan_preview is not None,
            },
            description="ApprovalManager.present_plan_for_approval called",
        )

        if not workflow.plan_preview:
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"service": "approval_manager_error", "workflow_id": workflow.id},
                description="Workflow missing plan preview - raising ValueError",
            )
            raise ValueError("Workflow missing plan preview")

        workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "service": "approval_manager_success",
                "workflow_id": workflow.id,
                "plan_length": len(workflow.plan_preview),
            },
            description="ApprovalManager.present_plan_for_approval completed successfully",
        )

        return workflow.plan_preview

    async def process_approval_response(
        self, workflow: Workflow, user_response: str
    ) -> Tuple[ApprovalStatus, Optional[str]]:
        """
        Process user's approval response

        Returns: (new_status, optional_instructions)
        """

        response_lower = user_response.lower()

        # Approval indicators
        if any(
            phrase in response_lower
            for phrase in [
                "yes",
                "proceed",
                "go ahead",
                "approved",
                "looks good",
                "perfect",
                "that works",
                "sounds good",
                "ok",
                "okay",
            ]
        ):
            workflow.approval_status = ApprovalStatus.APPROVED
            return ApprovalStatus.APPROVED, None

        # Rejection indicators
        elif any(
            phrase in response_lower
            for phrase in ["no", "don't", "reject", "different approach", "not right"]
        ):
            workflow.approval_status = ApprovalStatus.REJECTED
            return ApprovalStatus.REJECTED, user_response

        # Modification requests
        elif any(
            phrase in response_lower
            for phrase in ["but", "instead", "change", "modify", "adjust", "add", "remove"]
        ):
            workflow.approval_status = ApprovalStatus.MODIFIED
            return ApprovalStatus.MODIFIED, user_response

        # Unclear response - ask for clarification
        else:
            return (
                ApprovalStatus.AWAITING_APPROVAL,
                "I want to make sure I understand correctly. "
                "Should I proceed with this plan, or would you like me to adjust something?",
            )
