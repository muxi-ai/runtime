import asyncio
from typing import Optional, Dict, Any, List, Tuple
import json
import re
from ...observability import ConversationEventType, SystemEventType, EventLevel, ObservabilityManager

from .types import (
    Workflow, SubTask, TaskStatus, WorkflowStatus, ApprovalStatus,
    TaskInput, TaskOutput, RequestAnalysis,
    generate_workflow_id, generate_task_id, validate_workflow_dag,
    build_execution_phases
)
from ...llm import LLM


class TaskDecomposer:
    """
    Core decomposition engine using advanced prompting strategies.

    Breaks down complex requests into executable workflows with plan preview
    capabilities for user approval.
    """

    def __init__(self, llm: Optional[LLM] = None):
        """
        Initialize the task decomposer.

        Args:
            llm: Optional LLM for intelligent decomposition. Falls back to heuristics if None.
        """
        self.llm = llm

    async def decompose_request(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None,
        requires_approval: bool = False
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
                workflow = self._heuristic_decompose_request(
                    workflow_id, request, analysis
                )

            # Generate plan preview if user approval required
            if requires_approval:
                workflow.requires_approval = True
                workflow.plan_preview = await self._generate_plan_preview(
                    workflow, request
                )
                workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL

            # Validate workflow structure
            validated_workflow = self._validate_workflow(workflow)

            #  Decomposer info - add observability event
                f"Decomposed request into workflow {workflow_id} with "
                f"{len(validated_workflow.tasks)} tasks"
            )

            return validated_workflow

        except Exception as e:
            #  Decomposer error - add observability event
            # Return minimal fallback workflow
            return self._create_fallback_workflow(request)

    async def modify_workflow(
        self,
        workflow: Workflow,
        modification_instructions: str,
        context: Optional[Dict[str, Any]] = None
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
            #  Decomposer error - add observability event
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
        analysis: Optional[RequestAnalysis] = None
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

        try:
            response = await self.llm.generate(decomposition_prompt, max_tokens=2000)
            workflow = self._parse_llm_decomposition(workflow_id, request, response)
            return workflow

        except Exception as e:
            #  Decomposer warning - add observability event
            return self._heuristic_decompose_request(workflow_id, request, analysis)

    def _create_decomposition_prompt(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        analysis: Optional[RequestAnalysis] = None
    ) -> str:
        """
        Create sophisticated decomposition prompt for LLM.

        Args:
            request: User's request
            context: Optional conversation context
            analysis: Optional analysis results

        Returns:
            Decomposition prompt for LLM
        """
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

        return f"""
You are an expert workflow designer. Break down this user request into a structured workflow of interconnected tasks.

User Request: "{request}"{context_info}{analysis_info}

Please analyze the request using chain-of-thought reasoning and create a workflow with the following structure:

WORKFLOW_ANALYSIS:
[Think through the logical steps required, what capabilities are needed, and how tasks depend on each other]

TASKS:
For each task, provide:
Task_ID: [unique identifier like task_1, task_2, etc.]
Description: [clear description of what this task accomplishes]
Required_Capabilities: [list capabilities like research, writing, data_analysis, coding, etc.]
Dependencies: [list of task IDs that must complete before this task, use "none" if no dependencies]
Estimated_Complexity: [1-10 scale]
Inputs: [what inputs this task needs]
Outputs: [what this task produces]

EXECUTION_STRATEGY:
[Explain the optimal execution order and which tasks can run in parallel]

Guidelines:
1. Break complex work into logical, manageable steps
2. Identify clear dependencies between tasks
3. Design for parallel execution where possible
4. Each task should have clear inputs and outputs
5. Map tasks to appropriate agent capabilities
6. Ensure the workflow accomplishes the original request

Example capabilities to choose from:
- research: Web research, information gathering
- writing: Content creation, documentation
- data_analysis: Processing and analyzing data
- coding: Programming and development
- design: Visual design and mockups
- business_analysis: Strategy and business insights
- file_operations: File processing and management
- communication: Messaging and notifications

Provide a clear, structured response that can be parsed into executable tasks.
"""

    def _parse_llm_decomposition(
        self,
        workflow_id: str,
        request: str,
        response: str
    ) -> Workflow:
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

            # Extract tasks section
            tasks_section = re.search(r'TASKS:(.*?)(?=EXECUTION_STRATEGY:|$)', response, re.DOTALL | re.IGNORECASE)
            if not tasks_section:
                # Fallback if structure is different
                return self._heuristic_decompose_request(workflow_id, request)

            tasks_text = tasks_section.group(1)

            # Parse individual tasks
            task_blocks = re.split(r'Task_ID:', tasks_text)[1:]  # Skip empty first element

            for block in task_blocks:
                try:
                    task = self._parse_task_block(block.strip())
                    if task:
                        tasks[task.id] = task
                except Exception as e:
                    #  Decomposer warning - add observability event
                    continue

            if not tasks:
                # If no tasks parsed, create fallback
                return self._heuristic_decompose_request(workflow_id, request)

            workflow = Workflow(
                id=workflow_id,
                user_request=request,
                tasks=tasks,
                status=WorkflowStatus.PENDING
            )

            return workflow

        except Exception as e:
            #  Decomposer error - add observability event
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
            lines = block.split('\n')
            task_data = {}

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    value = value.strip()
                    task_data[key] = value

            # Extract required fields
            task_id = task_data.get('task_id', generate_task_id())
            description = task_data.get('description', 'Task description')

            # Parse capabilities
            capabilities_text = task_data.get('required_capabilities', 'general')
            if capabilities_text.startswith('[') and capabilities_text.endswith(']'):
                capabilities_text = capabilities_text[1:-1]
            required_capabilities = [cap.strip() for cap in capabilities_text.split(',')]

            # Parse dependencies
            dependencies_text = task_data.get('dependencies', 'none')
            dependencies = []
            if dependencies_text.lower() != 'none':
                if dependencies_text.startswith('[') and dependencies_text.endswith(']'):
                    dependencies_text = dependencies_text[1:-1]
                dependencies = [dep.strip() for dep in dependencies_text.split(',') if dep.strip()]

            # Parse complexity
            complexity = 5.0
            try:
                complexity = float(task_data.get('estimated_complexity', 5.0))
            except (ValueError, TypeError):
                pass

            return SubTask(
                id=task_id,
                description=description,
                required_capabilities=required_capabilities,
                dependencies=dependencies,
                estimated_complexity=complexity,
                status=TaskStatus.PENDING
            )

        except Exception as e:
            #  Decomposer error - add observability event
            return None

    def _heuristic_decompose_request(
        self,
        workflow_id: str,
        request: str,
        analysis: Optional[RequestAnalysis] = None
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
                'keywords': ['research', 'investigate', 'study', 'analyze'],
                'description': 'Research and gather information',
                'capabilities': ['research', 'web_search'],
                'complexity': 6
            },
            {
                'keywords': ['write', 'draft', 'create', 'compose'],
                'description': 'Create written content',
                'capabilities': ['writing'],
                'complexity': 7,
                'dependencies': []  # Will be set based on other tasks
            },
            {
                'keywords': ['analyze', 'process', 'examine'],
                'description': 'Analyze data and information',
                'capabilities': ['data_analysis'],
                'complexity': 6
            },
            {
                'keywords': ['implement', 'build', 'develop', 'code'],
                'description': 'Implement solution',
                'capabilities': ['coding', 'development'],
                'complexity': 8
            },
            {
                'keywords': ['design', 'mockup', 'wireframe'],
                'description': 'Create design deliverables',
                'capabilities': ['design'],
                'complexity': 6
            }
        ]

        # Generate tasks based on patterns found
        task_counter = 1
        for pattern in task_patterns:
            if any(keyword in request_lower for keyword in pattern['keywords']):
                task_id = f"task_{task_counter}"

                # Set dependencies (writing usually comes after research)
                dependencies = []
                if 'writing' in pattern['capabilities'] and any(t for t in tasks.values() if 'research' in t.required_capabilities):
                    dependencies = [t.id for t in tasks.values() if 'research' in t.required_capabilities]

                task = SubTask(
                    id=task_id,
                    description=pattern['description'],
                    required_capabilities=pattern['capabilities'],
                    dependencies=dependencies,
                    estimated_complexity=pattern['complexity'],
                    status=TaskStatus.PENDING
                )

                tasks[task_id] = task
                task_counter += 1

        # If no patterns matched, create a general task
        if not tasks:
            task = SubTask(
                id="task_1",
                description=f"Complete request: {request[:100]}...",
                required_capabilities=['general'],
                dependencies=[],
                estimated_complexity=5.0,
                status=TaskStatus.PENDING
            )
            tasks["task_1"] = task

        return Workflow(
            id=workflow_id,
            user_request=request,
            tasks=tasks,
            status=WorkflowStatus.PENDING
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
            plan_prompt = f"""
Convert this technical workflow into a clear, natural plan that a user can easily understand and approve.

Original Request: {original_request}

Technical Workflow:
{self._workflow_to_text(workflow)}

Instructions:
1. Explain the approach in conversational language
2. Outline the main steps in logical order
3. Mention which specialists will be involved
4. Explain why this approach makes sense
5. Estimate overall timeline
6. Ask for approval to proceed

Format as a natural conversation from the overlord's perspective.
Use "I will..." statements and explain the reasoning.
Keep it concise but comprehensive.
"""

            plan_preview = await self.llm.generate(plan_prompt, max_tokens=800)
            return plan_preview

        except Exception as e:
            #  Decomposer error - add observability event
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
                f"Here's my plan to handle your request: \"{original_request}\"\n",
                "## Proposed Approach\n"
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

            plan_lines.extend([
                f"\n**Estimated completion time: {time_estimate}**\n",
                "Does this approach work for you? Would you like me to proceed, or should I adjust anything?"
            ])

            return "\n".join(plan_lines)

        except Exception as e:
            #  Decomposer error - add observability event
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
            lines.append(f"  Dependencies: {', '.join(task.dependencies) if task.dependencies else 'None'}")
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
                #  Decomposer warning - add observability event
                workflow = self._fix_workflow_cycles(workflow)

            # Build execution phases
            try:
                build_execution_phases(workflow)
            except Exception as e:
                #  Decomposer warning - add observability event

            return workflow

        except Exception as e:
            #  Decomposer error - add observability event
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
                task.dependencies = [task_ids[i-1]]

        #  Decomposer info - add observability event
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
            status=TaskStatus.PENDING
        )

        return Workflow(
            id=workflow_id,
            user_request=request,
            tasks={"fallback_task": task},
            status=WorkflowStatus.PENDING
        )

    async def _llm_modify_workflow(
        self,
        workflow: Workflow,
        modification_instructions: str,
        context: Optional[Dict[str, Any]] = None
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
        #  Decomposer info - add observability event
        return workflow

    def _heuristic_modify_workflow(
        self,
        workflow: Workflow,
        modification_instructions: str
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
        #  Decomposer info - add observability event
        return workflow


class ApprovalManager:
    """Handle plan approval workflow"""

    async def present_plan_for_approval(self, workflow: Workflow) -> str:
        """Present plan to user and return formatted message"""

        if not workflow.plan_preview:
            raise ValueError("Workflow missing plan preview")

        workflow.approval_status = ApprovalStatus.AWAITING_APPROVAL
        return workflow.plan_preview

    async def process_approval_response(
        self,
        workflow: Workflow,
        user_response: str
    ) -> Tuple[ApprovalStatus, Optional[str]]:
        """
        Process user's approval response

        Returns: (new_status, optional_instructions)
        """

        response_lower = user_response.lower()

        # Approval indicators
        if any(phrase in response_lower for phrase in [
            "yes", "proceed", "go ahead", "approved", "looks good",
            "perfect", "that works", "sounds good", "ok", "okay"
        ]):
            workflow.approval_status = ApprovalStatus.APPROVED
            return ApprovalStatus.APPROVED, None

        # Rejection indicators
        elif any(phrase in response_lower for phrase in [
            "no", "don't", "reject", "different approach", "not right"
        ]):
            workflow.approval_status = ApprovalStatus.REJECTED
            return ApprovalStatus.REJECTED, user_response

        # Modification requests
        elif any(phrase in response_lower for phrase in [
            "but", "instead", "change", "modify", "adjust", "add", "remove"
        ]):
            workflow.approval_status = ApprovalStatus.MODIFIED
            return ApprovalStatus.MODIFIED, user_response

        # Unclear response - ask for clarification
        else:
            return ApprovalStatus.AWAITING_APPROVAL, "I want to make sure I understand correctly. Should I proceed with this plan, or would you like me to adjust something?"
