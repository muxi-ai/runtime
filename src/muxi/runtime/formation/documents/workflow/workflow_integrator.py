"""
Document Workflow Integrator Implementation

This module implements document-based task generation and workflow enrichment,
creating actionable workflows from document analysis.

Features:
- Document-based task generation
- Workflow enrichment with document insights
- Follow-up suggestion generation
- Integration with existing workflow systems
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ....services import observability


@dataclass
class DocumentTask:
    """Represents a task generated from document analysis"""

    task_id: str
    title: str
    description: str
    priority: str  # "low", "medium", "high", "critical"
    category: str  # "action", "review", "decision", "research"
    source_document_id: str
    source_references: List[str]
    estimated_effort: Optional[str]
    dependencies: List[str]
    due_date: Optional[float]
    assignee: Optional[str]
    metadata: Dict[str, Any]
    created_at: float


@dataclass
class WorkflowEnrichment:
    """Represents workflow enrichment from document analysis"""

    enrichment_id: str
    workflow_id: str
    document_insights: List[str]
    suggested_improvements: List[str]
    risk_factors: List[str]
    optimization_opportunities: List[str]
    confidence_score: float
    timestamp: float


class DocumentWorkflowIntegrator:
    """
    Document-based task generation and workflow enrichment system.

    Analyzes documents to automatically generate actionable tasks and
    enrich existing workflows with document-derived insights.
    """

    def __init__(
        self,
        llm_model,
        persona_config: Optional[Dict[str, Any]] = None,
        workflow_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the document workflow integrator.

        Args:
            llm_model: Language model for task generation
            persona_config: Overlord persona configuration
            workflow_config: Workflow integration settings
        """
        self.llm_model = llm_model
        self.persona_config = persona_config or {}
        self.workflow_config = workflow_config or {}

        # Task and workflow tracking
        self._generated_tasks: Dict[str, DocumentTask] = {}
        self._workflow_enrichments: Dict[str, WorkflowEnrichment] = {}

        # Task generation prompts
        self._task_prompts = self._initialize_task_prompts()

    def _initialize_task_prompts(self) -> Dict[str, str]:
        """Initialize task generation prompts"""
        return {
            "action_tasks": """
            Analyze this document and identify specific action items that need to be completed.
            Focus on:
            - Concrete tasks mentioned or implied
            - Deadlines and time-sensitive items
            - Required approvals or decisions
            - Implementation steps

            Format each task with:
            - Clear, actionable title
            - Detailed description
            - Priority level (low/medium/high/critical)
            - Estimated effort if possible
            """,
            "decision_tasks": """
            Identify decisions that need to be made based on this document.
            Look for:
            - Options or alternatives presented
            - Recommendations requiring approval
            - Strategic choices to be made
            - Policy decisions needed

            For each decision task, include:
            - What decision needs to be made
            - Available options or context
            - Stakeholders involved
            - Timeline if specified
            """,
            "review_tasks": """
            Identify items that require review or evaluation based on this document.
            Focus on:
            - Documents or proposals to review
            - Performance metrics to evaluate
            - Compliance checks needed
            - Quality assurance requirements

            Include for each review task:
            - What needs to be reviewed
            - Review criteria or standards
            - Who should conduct the review
            - Expected timeline
            """,
            "research_tasks": """
            Identify research or investigation tasks suggested by this document.
            Look for:
            - Information gaps that need filling
            - Market research requirements
            - Technical investigations needed
            - Competitive analysis tasks

            For each research task, specify:
            - What needs to be researched
            - Key questions to answer
            - Information sources to explore
            - Expected deliverables
            """,
        }

    async def generate_tasks_from_document(
        self,
        document_id: str,
        document_content: str,
        document_metadata: Optional[Dict[str, Any]] = None,
        task_categories: Optional[List[str]] = None,
    ) -> List[DocumentTask]:
        """
        Generate actionable tasks from document analysis.

        Args:
            document_id: Unique document identifier
            document_content: Full document content
            document_metadata: Optional document metadata
            task_categories: Optional list of task categories to focus on

        Returns:
            List of DocumentTask objects
        """

        categories = task_categories or ["action_tasks", "decision_tasks", "review_tasks"]
        all_tasks = []

        for category in categories:
            try:
                tasks = await self._generate_tasks_for_category(
                    document_id, document_content, category, document_metadata
                )
                all_tasks.extend(tasks)
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "document_id": document_id,
                        "category": category,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                    description=f"Failed to generate tasks for document category {category}",
                )
                continue

        # Store generated tasks
        for task in all_tasks:
            self._generated_tasks[task.task_id] = task

        return all_tasks

    async def enrich_workflow_with_document(
        self,
        workflow_id: str,
        document_id: str,
        document_content: str,
        existing_workflow: Dict[str, Any],
    ) -> WorkflowEnrichment:
        """
        Enrich an existing workflow with document insights.

        Args:
            workflow_id: Unique workflow identifier
            document_id: Source document identifier
            document_content: Document content for analysis
            existing_workflow: Current workflow structure

        Returns:
            WorkflowEnrichment object with insights and suggestions
        """

        # Analyze document for workflow insights
        insights_prompt = f"""
        Analyze this document in the context of improving an existing workflow.

        Current workflow context:
        {existing_workflow.get('description', 'No description available')}

        Document content:
        {document_content}

        Provide insights on:
        1. How this document relates to the workflow
        2. Potential improvements or optimizations
        3. Risk factors or challenges identified
        4. New opportunities or capabilities

        Be specific and actionable in your recommendations.
        """

        try:
            insights_response = await self.llm_model.generate_response(insights_prompt)

            # Parse insights response
            parsed_insights = self._parse_workflow_insights(insights_response)

            # Create enrichment object
            enrichment = WorkflowEnrichment(
                enrichment_id=f"{workflow_id}_{document_id}_{int(time.time())}",
                workflow_id=workflow_id,
                document_insights=parsed_insights["insights"],
                suggested_improvements=parsed_insights["improvements"],
                risk_factors=parsed_insights["risks"],
                optimization_opportunities=parsed_insights["opportunities"],
                confidence_score=self._calculate_enrichment_confidence(parsed_insights),
                timestamp=time.time(),
            )

            # Store enrichment
            self._workflow_enrichments[enrichment.enrichment_id] = enrichment

            return enrichment

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow_id,
                    "document_id": document_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "enrich_workflow",
                },
                description="Failed to enrich workflow with document insights",
            )
            raise

    async def generate_follow_up_suggestions(
        self, document_id: str, user_query: str, document_content: str
    ) -> List[str]:
        """
        Generate follow-up suggestions based on document content and user query.

        Args:
            document_id: Document identifier
            user_query: User's original query or interest
            document_content: Document content

        Returns:
            List of follow-up suggestion strings
        """
        follow_up_prompt = f"""
        Based on the user's query and this document, suggest relevant follow-up questions
        or actions they might want to take.

        User query: {user_query}

        Document content: {document_content[:2000]}...

        Provide 3-5 specific, actionable follow-up suggestions that would help the user
        dive deeper into the topic or take next steps.
        """

        try:
            response = await self.llm_model.generate_response(follow_up_prompt)
            suggestions = self._parse_follow_up_suggestions(response)

            #     f"Generated {len(suggestions)} follow-up suggestions for document {document_id}"
            # )
            return suggestions

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "document_id": document_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "generate_followup_suggestions",
                },
                description="Failed to generate follow-up suggestions for document",
            )
            return []

    async def _generate_tasks_for_category(
        self,
        document_id: str,
        document_content: str,
        category: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentTask]:
        """Generate tasks for a specific category"""
        prompt = self._task_prompts.get(category, self._task_prompts["action_tasks"])

        full_prompt = f"""
        {prompt}

        Document content:
        {document_content}

        Please format your response as a structured list with clear task items.
        """

        try:
            response = await self.llm_model.generate_response(full_prompt)
            tasks = self._parse_task_response(response, document_id, category, document_metadata)
            return tasks

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "document_id": document_id,
                    "category": category,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "generate_tasks_for_category",
                },
                description=f"Failed to generate {category} tasks for document",
            )
            return []

    def _parse_task_response(
        self,
        response: str,
        document_id: str,
        category: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentTask]:
        """Parse LLM response into DocumentTask objects"""
        tasks = []
        lines = response.strip().split("\n")
        current_task = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for task indicators
            if (line.startswith("**") and line.endswith("**")) or (
                line.startswith("##") or line.startswith("###")
            ):
                # Save previous task if exists
                if current_task.get("title"):
                    task = self._create_task_from_parsed_data(
                        current_task, document_id, category, document_metadata
                    )
                    if task:
                        tasks.append(task)

                # Start new task
                current_task = {
                    "title": line.strip("*#").strip(),
                    "description": "",
                    "priority": "medium",
                    "effort": None,
                }

            elif line.startswith("- ") or line.startswith("• "):
                # Add to description
                if "description" in current_task:
                    current_task["description"] += f"\n{line}"
                else:
                    current_task["description"] = line

            elif "priority:" in line.lower():
                # Extract priority
                priority_text = line.lower().split("priority:")[1].strip()
                if any(p in priority_text for p in ["high", "critical"]):
                    current_task["priority"] = "high"
                elif "low" in priority_text:
                    current_task["priority"] = "low"
                else:
                    current_task["priority"] = "medium"

        # Save final task
        if current_task.get("title"):
            task = self._create_task_from_parsed_data(
                current_task, document_id, category, document_metadata
            )
            if task:
                tasks.append(task)

        return tasks

    def _create_task_from_parsed_data(
        self,
        task_data: Dict[str, Any],
        document_id: str,
        category: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DocumentTask]:
        """Create DocumentTask from parsed data"""
        if not task_data.get("title"):
            return None

        task_id = f"{document_id}_{category}_{int(time.time())}"

        # Map category to task category
        category_map = {
            "action_tasks": "action",
            "decision_tasks": "decision",
            "review_tasks": "review",
            "research_tasks": "research",
        }

        return DocumentTask(
            task_id=task_id,
            title=task_data["title"],
            description=task_data.get("description", ""),
            priority=task_data.get("priority", "medium"),
            category=category_map.get(category, "action"),
            source_document_id=document_id,
            source_references=[document_id],
            estimated_effort=task_data.get("effort"),
            dependencies=[],
            due_date=None,
            assignee=None,
            metadata=document_metadata or {},
            created_at=time.time(),
        )

    def _parse_workflow_insights(self, insights_response: str) -> Dict[str, List[str]]:
        """Parse workflow insights from LLM response"""
        sections = {"insights": [], "improvements": [], "risks": [], "opportunities": []}

        current_section = None
        lines = insights_response.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Identify sections
            if "insight" in line.lower() or "finding" in line.lower():
                current_section = "insights"
            elif "improvement" in line.lower() or "optimization" in line.lower():
                current_section = "improvements"
            elif "risk" in line.lower() or "challenge" in line.lower():
                current_section = "risks"
            elif "opportunit" in line.lower() or "potential" in line.lower():
                current_section = "opportunities"
            elif line.startswith("- ") or line.startswith("• "):
                if current_section:
                    sections[current_section].append(line[2:])

        return sections

    def _parse_follow_up_suggestions(self, response: str) -> List[str]:
        """Parse follow-up suggestions from LLM response"""
        suggestions = []
        lines = response.split("\n")

        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                suggestions.append(line[2:])
            elif line and not line.startswith("#") and "?" in line:
                # Likely a question suggestion
                suggestions.append(line)

        return suggestions[:5]  # Limit to 5 suggestions

    def _calculate_enrichment_confidence(self, insights: Dict[str, List[str]]) -> float:
        """Calculate confidence score for workflow enrichment"""
        base_confidence = 0.5

        # Increase confidence based on content quality
        if insights["insights"]:
            base_confidence += 0.2

        if insights["improvements"]:
            base_confidence += 0.15

        if insights["risks"]:
            base_confidence += 0.1

        if insights["opportunities"]:
            base_confidence += 0.15

        return min(base_confidence, 1.0)

    def get_tasks_by_document(self, document_id: str) -> List[DocumentTask]:
        """Get all tasks generated from a specific document"""
        return [
            task
            for task in self._generated_tasks.values()
            if task.source_document_id == document_id
        ]

    def get_tasks_by_category(self, category: str) -> List[DocumentTask]:
        """Get all tasks of a specific category"""
        return [task for task in self._generated_tasks.values() if task.category == category]

    def get_workflow_enrichments(self, workflow_id: str) -> List[WorkflowEnrichment]:
        """Get all enrichments for a specific workflow"""
        return [
            enrichment
            for enrichment in self._workflow_enrichments.values()
            if enrichment.workflow_id == workflow_id
        ]

    def get_integration_statistics(self) -> Dict[str, Any]:
        """Get statistics about workflow integration"""
        if not self._generated_tasks:
            return {"total_tasks": 0, "total_enrichments": 0}

        # Task statistics
        task_categories = {}
        task_priorities = {}

        for task in self._generated_tasks.values():
            task_categories[task.category] = task_categories.get(task.category, 0) + 1
            task_priorities[task.priority] = task_priorities.get(task.priority, 0) + 1

        # Enrichment statistics
        avg_confidence = 0.0
        if self._workflow_enrichments:
            total_confidence = sum(e.confidence_score for e in self._workflow_enrichments.values())
            avg_confidence = total_confidence / len(self._workflow_enrichments)

        return {
            "total_tasks": len(self._generated_tasks),
            "total_enrichments": len(self._workflow_enrichments),
            "task_categories": task_categories,
            "task_priorities": task_priorities,
            "avg_enrichment_confidence": avg_confidence,
            "unique_documents": len(
                set(task.source_document_id for task in self._generated_tasks.values())
            ),
        }
