from typing import Optional, Dict, Any, Tuple
import re
from pathlib import Path

from ...datatypes.workflow import (
    Workflow,
    SubTask,
    TaskStatus,
    WorkflowStatus,
    ApprovalStatus,
    RequestAnalysis,
    generate_workflow_id,
    generate_task_id,
    validate_workflow_dag,
    build_execution_phases,
)
from ...services.llm import LLM
from ...services import observability


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

            #  Decomposer info - TODO: add observability
            #     f"Decomposed request into workflow {workflow_id} with "
            #     f"{len(validated_workflow.tasks)} tasks"
            # )

            return validated_workflow

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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
        decomposition_prompt = self._create_decomposition_prompt(request, context, analysis)

        # Debug: Log the actual prompt being sent to LLM
        capabilities_info = self._get_available_capabilities_info()
        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,
            level=observability.EventLevel.INFO,  # Changed to INFO so it shows up
            data={
                "service": "task_decomposer",
                "prompt_length": len(decomposition_prompt),
                "capabilities_info": capabilities_info,
                "full_prompt": (
                    decomposition_prompt[:1000] + "..."
                    if len(decomposition_prompt) > 1000
                    else decomposition_prompt
                ),
            },
            description="TaskDecomposer using dynamic capabilities",
        )

        # DEBUG: Print full decomposition prompt to console for debugging tests
        print("\n" + "=" * 80)
        print("📋 FULL DECOMPOSITION PROMPT:")
        print("=" * 80)
        print(decomposition_prompt)
        print("=" * 80)

        try:
            response = await self.llm.generate_text(decomposition_prompt, max_tokens=2000)

            # DEBUG: Print LLM response for debugging
            print("\n" + "🤖 LLM DECOMPOSITION RESPONSE:")
            print("=" * 80)
            print(response)
            print("=" * 80)

            workflow = self._parse_llm_decomposition(workflow_id, request, response)

            # DEBUG: Print parsed workflow info
            print(f"\n📋 PARSED WORKFLOW: {len(workflow.tasks)} tasks")
            for task_id, task in workflow.tasks.items():
                print(f"  - {task_id}: {task.description}")
                print(f"    Capabilities: {task.required_capabilities}")
            print()

            return workflow

        except Exception as e:
            #  Decomposer warning - TODO: add observability
            print(f"\n❌ LLM DECOMPOSITION FAILED: {type(e).__name__}: {e}")
            print("🔄 Falling back to heuristic decomposition")
            return self._heuristic_decompose_request(workflow_id, request, analysis)

    def _create_decomposition_prompt(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None,
    ) -> str:
        """
        Create sophisticated decomposition prompt for LLM from template file.

        Args:
            request: User's request
            context: Optional conversation context
            analysis: Optional analysis results

        Returns:
            Decomposition prompt for LLM
        """
        # Read the prompt template from file
        template_path = Path(__file__).parent / "decomposition_prompt.md"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            # Fallback to basic template if file not found
            template = (
                "<user_request>{{request}}</user_request>\n"
                "<context>{{context_info}}</context>\n"
                "<analysis>{{analysis_info}}</analysis>\n"
                "<capabilities>{{capabilities_info}}</capabilities>"
            )

        # Prepare template variables
        context_info = ""
        if context:
            context_info = f"\nContext: {context}"

        analysis_info = ""
        if analysis:
            analysis_info = f"""
Analysis Results:
- Complexity Score: {analysis.complexity_score}/10
- Required Capabilities: {', '.join(analysis.required_capabilities)}
- Implicit Subtasks: {', '.join(analysis.implicit_subtasks)}
"""

        capabilities_info = self._get_available_capabilities_info()

        # Replace template placeholders
        return (
            template.replace("{{request}}", request)
            .replace("{{context_info}}", context_info)
            .replace("{{analysis_info}}", analysis_info)
            .replace("{{capabilities_info}}", capabilities_info)
        )

    def _get_available_capabilities_info(self) -> str:
        """
        Dynamically generate information about available agent capabilities and MCP tools.

        Returns:
            Formatted string with current agent capabilities and available tools
        """
        info_parts = ["Available agent capabilities and tools:\n"]

        # Get agent capabilities
        if self.agent_registry:
            # # DEBUG: Log agent registry for troubleshooting
            # print(f"\n🏗️  DEBUG TASKDECOMPOSER AGENT REGISTRY:")
            # print(f"  Registry size: {len(self.agent_registry)}")
            # for agent_id, agent in self.agent_registry.items():
            #     specialties = getattr(agent, 'specialties', [])
            #     print(f"  - {agent_id}: {specialties}")
            # print("  " + "="*60)

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

                # Add agent description if available
                if agent_description:
                    info_parts.append(f"  Best for: {agent_description}")
                elif specialties:
                    # Generic description based on capabilities
                    capability_str = ", ".join(specialties)
                    info_parts.append(
                        f"  Best for: Tasks requiring {capability_str} capabilities"
                    )

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
        research_caps = [cap for cap in all_capabilities if 'research' in cap.lower()]
        if research_caps:
            caps_str = "' or '".join(research_caps)
            info_parts.append(
                f"- Research/info gathering → use capability: '{caps_str}'"
            )

        # Find actual writing-related capabilities
        writing_caps = [cap for cap in all_capabilities if 'writing' in cap.lower() or 'documentation' in cap.lower()]
        if writing_caps:
            caps_str = "' or '".join(writing_caps)
            info_parts.append(
                f"- Content creation/docs → use capability: '{caps_str}'"
            )

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
            tasks_section = re.search(
                r"###\s*TASKS:(.*?)(?=###\s*EXECUTION_STRATEGY:|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if not tasks_section:
                tasks_section = re.search(
                    r"\*\*TASKS:\*\*(.*?)(?=\*\*EXECUTION_STRATEGY:\*\*|$)",
                    response,
                    re.DOTALL | re.IGNORECASE,
                )
            if not tasks_section:
                # Fallback to plain text format
                tasks_section = re.search(
                    r"TASKS:(.*?)(?=EXECUTION_STRATEGY:|$)", response, re.DOTALL | re.IGNORECASE
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
                # Fallback to plain text format
                task_blocks = re.split(r"Task_ID:\s*", tasks_text)
            task_blocks = task_blocks[1:]  # Skip empty first element

            for block in task_blocks:
                try:
                    task = self._parse_task_block(block.strip())
                    if task:
                        tasks[task.id] = task
                except Exception as e:
                    #  Decomposer warning - TODO: add observability
                    _ = e  # remove this after implementing observability
                    continue

            if not tasks:
                # If no tasks parsed, create fallback
                # print(f"⚠️  WARNING: No tasks parsed from LLM response")
                # print(f"Task blocks found: {len(task_blocks)}")
                # if task_blocks:
                #     print(f"First block preview: {task_blocks[0][:200]}...")
                return self._heuristic_decompose_request(workflow_id, request)

            workflow = Workflow(
                id=workflow_id, user_request=request, tasks=tasks, status=WorkflowStatus.PENDING
            )

            return workflow

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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

            # DEBUG: Log capability assignment for troubleshooting platform tasks
            # if any(platform in str(required_capabilities) for platform in ['linear', 'github', 'jira', 'slack']):
            #     print(f"\n🎯 DEBUG PLATFORM TASK DECOMPOSITION:")
            #     print(f"  Task ID: {task_id}")
            #     print(f"  Task description: {description}")
            #     print(f"  Raw capabilities text: '{capabilities_text}'")
            #     print(f"  Parsed capabilities: {required_capabilities}")
            #     print("  " + "="*60)

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

            return SubTask(
                id=task_id,
                description=description,
                required_capabilities=required_capabilities,
                dependencies=dependencies,
                estimated_complexity=complexity,
                status=TaskStatus.PENDING,
            )

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            plan_prompt = (
                "Convert this technical workflow into a clear plan that a user can easily understand and approve.\n\n"
                f"Original Request: {original_request}\n\n"
                f"Technical Workflow:\n"
                f"{self._workflow_to_text(workflow)}\n\n"
                "Instructions:\n"
                "1. Start with \"Here's my proposed approach for your request:\"\n"
                "2. Explain the workflow steps in logical order\n"
                "3. Mention which specialists will be involved for each phase\n"
                "4. IMPORTANT: Preserve the exact task descriptions from the workflow - do NOT reinterpret or rename them\n"  # noqa: E501
                "5. If a task involves creating issues/tickets on any platform, keep that description - do NOT call it \"Implement Solution\" or \"Development\"\n"  # noqa: E501
                "6. Explain why this approach makes sense\n"
                "7. End with \"Does this approach work for you? Should I proceed with this plan?\"\n\n"
                "Use a direct, professional tone. Accurately represent what each task will do based on its description.\n"  # noqa: E501
                "Keep it concise but comprehensive.\n\n"
                "IMPORTANT: Always reply in the same language as the user's original request\n"
            )

            plan_preview = await self.llm.generate_text(plan_prompt, max_tokens=800)
            return plan_preview

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            estimated_minutes = total_complexity * 5  # Rough estimate

            if estimated_minutes < 10:
                time_estimate = "5-10 minutes"
            elif estimated_minutes < 30:
                time_estimate = "15-30 minutes"
            elif estimated_minutes < 60:
                time_estimate = "30-60 minutes"
            else:
                time_estimate = f"{estimated_minutes//60}+ hours"

            plan_lines.extend(
                [
                    f"\n**Estimated completion time: {time_estimate}**\n",
                    "Does this approach work for you? "
                    "Would you like me to proceed, or should I adjust anything?",
                ]
            )

            return "\n".join(plan_lines)

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
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
                #  Decomposer warning - TODO: add observability
                workflow = self._fix_workflow_cycles(workflow)

            # Build execution phases
            try:
                build_execution_phases(workflow)
            except Exception as e:
                #  Decomposer warning - TODO: add observability
                _ = e  # remove this after implementing observability

            return workflow

        except Exception as e:
            #  Decomposer error - TODO: add observability
            _ = e  # remove this after implementing observability
            return workflow

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

        #  Decomposer info - TODO: add observability
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
        #  Decomposer info - TODO: add observability
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
        #  Decomposer info - TODO: add observability
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
                event_type=observability.ErrorEvents.VALIDATION_ERROR,
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
