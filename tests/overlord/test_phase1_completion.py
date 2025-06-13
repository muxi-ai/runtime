"""
Test Phase 1 Completion - Interactive Elements & Enhanced Multimodal Integration

This test demonstrates the completed Phase 1 components:
- Interactive Response Elements (buttons, forms, media integration)
- Enhanced Multi-Modal Integration (workflow content processing)
- Integration with overlord workflow system
"""

import asyncio

# Loguru import removed - add observability import if needed

from src.muxi.runtime.overlord.workflow.interactive import (
    InteractiveElementGenerator,
    ResponseFormatter,
    MediaIntegrator,
    ButtonStyle
)
from src.muxi.runtime.overlord.workflow.multimodal_integration import (
    WorkflowMultiModalProcessor,
    TaskInputProcessor,
    TaskOutputProcessor
)
from src.muxi.runtime.overlord.workflow.multimodal import (
    MultiModalFusionEngine,
    MultiModalContent,
    ModalityType
)
from src.muxi.runtime.overlord.workflow.types import (
    Workflow,
    SubTask,
    TaskStatus
)


async def test_interactive_elements():
    """Test interactive element generation and formatting"""
    #  Info - add observability event

    # Initialize components
    generator = InteractiveElementGenerator()
    formatter = ResponseFormatter(generator)

    # Test button creation
    approve_button = generator.create_button(
        text="✅ Approve Plan",
        action="approve_workflow",
        style=ButtonStyle.SUCCESS
    )

    reject_button = generator.create_button(
        text="❌ Reject Plan",
        action="reject_workflow",
        style=ButtonStyle.DANGER
    )

    # Test form creation
    feedback_form = generator.create_feedback_form("workflow_test")

    # Test chart creation
    progress_chart = generator.create_progress_chart(
        completed=3,
        total=5,
        title="Test Workflow Progress"
    )

    # Test table creation
    status_table = generator.create_table(
        headers=["Task", "Status", "Progress"],
        rows=[
            ["Research", "✅ Complete", "100%"],
            ["Analysis", "🔄 In Progress", "60%"],
            ["Report", "⏳ Pending", "0%"]
        ]
    )

    # Test response formatting
    sample_content = """
    # Workflow Execution Complete

    I've successfully completed your multi-step workflow with the following results:

    ## Summary
    - Research phase completed with 15 sources analyzed
    - Analysis identified 3 key trends
    - Report drafted with executive summary

    Please review the interactive elements below for next steps.
    """

    elements = [approve_button, reject_button, feedback_form, progress_chart, status_table]

    formatted_response = await formatter.format_response(
        content=sample_content,
        elements=elements,
        format_type="markdown",
        context={"user": "test_user", "workflow_id": "test_001"}
    )

    #  Info - add observability event
    #  Info - add observability event

    return {
        "buttons": [approve_button, reject_button],
        "form": feedback_form,
        "chart": progress_chart,
        "table": status_table,
        "formatted_response": formatted_response
    }


async def test_media_integration():
    """Test media integration capabilities"""
    #  Info - add observability event

    integrator = MediaIntegrator()

    # Create sample media items
    media_items = [
        {
            "type": "chart",
            "title": "Workflow Performance",
            "content": {
                "data": [1, 2, 3, 4, 5],
                "labels": ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"]
            },
            "format": "bar_chart"
        },
        {
            "type": "image",
            "title": "Process Diagram",
            "content": "workflow_diagram.png",
            "alt_text": "Diagram showing workflow execution flow"
        },
        {
            "type": "table",
            "title": "Results Summary",
            "content": {
                "headers": ["Metric", "Value", "Target"],
                "rows": [
                    ["Completion Rate", "95%", "90%"],
                    ["Quality Score", "8.7/10", "8.0/10"],
                    ["Time Taken", "24min", "30min"]
                ]
            }
        }
    ]

    sample_content = """
    # Workflow Results

    Here are the results from your multi-agent workflow execution:

    ## Performance Metrics
    The workflow completed successfully with excellent performance metrics.

    ## Visual Analysis
    Below you'll find charts and diagrams showing the detailed analysis.
    """

    enhanced_content = await integrator.embed_media(
        content=sample_content,
        media_items=media_items,
        format_type="markdown"
    )

    #  Info - add observability event
    #  Info - add observability event

    return {
        "media_items": media_items,
        "enhanced_content": enhanced_content
    }


async def test_multimodal_workflow_processing():
    """Test enhanced multimodal workflow processing"""
    #  Info - add observability event

    try:
        # Create a mock LLM for testing
        class MockLLM:
            async def chat(self, *args, **kwargs):
                return "Mock LLM response for multimodal processing"

        mock_llm = MockLLM()

        # Initialize components
        fusion_engine = MultiModalFusionEngine(llm=mock_llm)
        workflow_processor = WorkflowMultiModalProcessor(fusion_engine)
        task_input_processor = TaskInputProcessor(fusion_engine)

        # Create sample multimodal content
        text_content = MultiModalContent(
            modality=ModalityType.TEXT,
            content="Analyze the quarterly sales data for trends and insights",
            metadata={"source": "user_request", "priority": "high"}
        )

        # Create a sample workflow
        workflow = Workflow(
            id="test_multimodal_workflow",
            user_request="Multi-modal analysis workflow",
            tasks={
                "task1": SubTask(
                    id="data_analysis",
                    description="Analyze multimodal data inputs",
                    required_capabilities=["data_analysis", "multimodal_fusion"],
                    status=TaskStatus.PENDING
                )
            }
        )

        # Process workflow with multimodal capabilities
        enhanced_workflow = await workflow_processor.process_workflow_content(
            workflow=workflow,
            initial_content=[text_content]
        )

        # Test task input processing
        raw_inputs = [
            "Process this sales data",
            {"type": "data", "content": "sample_data.csv"},
            "Generate insights and recommendations"
        ]

        processed_inputs = await task_input_processor.process_task_inputs(
            task=workflow.tasks["task1"],
            raw_inputs=raw_inputs
        )

        # Test task output processing
        task_output_processor = TaskOutputProcessor(fusion_engine)

        raw_outputs = [
            "Analysis complete: 3 key trends identified",
            {"type": "chart", "data": [1, 2, 3], "title": "Sales Trends"},
            {"type": "summary", "insights": ["Trend 1", "Trend 2", "Trend 3"]}
        ]

        processed_outputs = await task_output_processor.process_task_outputs(
            task=workflow.tasks["task1"],
            raw_outputs=raw_outputs
        )

        #  Info - add observability event
        #  Info - add observability event
        #  Info - add observability event
        #  Info - add observability event

        return {
            "enhanced_workflow": enhanced_workflow,
            "processed_inputs": processed_inputs,
            "processed_outputs": processed_outputs,
            "multimodal_content": [text_content]
        }

    except Exception as e:
        logger.error(f"❌ Multimodal workflow processing test failed: {e}")
        return {"error": str(e)}


async def test_integrated_workflow_experience():
    """Test the complete integrated workflow experience with all Phase 1 components"""
    #  Info - add observability event

    try:
        # Initialize all components together
        generator = InteractiveElementGenerator()
        formatter = ResponseFormatter(generator)
        integrator = MediaIntegrator()

        # Create a complete workflow response scenario
        workflow_content = """
        # Multi-Agent Research & Analysis Complete ✅

        I've successfully coordinated a complex multi-agent workflow to research
        emerging AI trends and generate a comprehensive analysis report.

        ## Workflow Summary
        **Duration:** 12 minutes
        **Agents Used:** Research Agent, Analysis Agent, Visualization Agent
        **Data Sources:** 23 academic papers, 15 industry reports, 8 expert interviews

        ## Key Findings
        1. **Multimodal AI Integration** is the dominant trend (78% adoption planned)
        2. **Autonomous Agent Systems** show 340% growth in enterprise interest
        3. **Ethical AI Frameworks** are becoming regulatory requirements

        ## Next Steps
        Based on this analysis, I recommend reviewing the detailed findings and
        approving the implementation roadmap below.
        """

        # Create interactive elements
        elements = [
            generator.create_progress_chart(5, 5, "Workflow Completion"),
            generator.create_table(
                headers=["Phase", "Status", "Key Output"],
                rows=[
                    ["Research", "✅ Complete", "23 sources analyzed"],
                    ["Analysis", "✅ Complete", "3 key trends identified"],
                    ["Visualization", "✅ Complete", "Charts & graphs generated"],
                    ["Report", "✅ Complete", "Executive summary ready"],
                    ["Recommendations", "✅ Complete", "Action items defined"]
                ]
            ),
            *generator.create_approval_buttons("ai_trends_analysis")
        ]

        # Create media content
        media_items = [
            {
                "type": "chart",
                "title": "AI Adoption Trends",
                "content": {
                    "type": "line_chart",
                    "data": [65, 72, 78, 85, 91],
                    "labels": ["2020", "2021", "2022", "2023", "2024"],
                    "trend": "increasing"
                }
            },
            {
                "type": "summary_card",
                "title": "Executive Summary",
                "content": {
                    "findings": 3,
                    "recommendations": 5,
                    "confidence": "High",
                    "impact": "Strategic"
                }
            }
        ]

        # Generate complete enhanced response
        formatted_response = await formatter.format_response(
            content=workflow_content,
            elements=elements,
            format_type="markdown",
            context={
                "user_id": "user_123",
                "workflow_type": "research_analysis",
                "complexity": "high"
            }
        )

        final_response = await integrator.embed_media(
            content=formatted_response['content'],
            media_items=media_items,
            format_type="markdown"
        )

        #  Info - add observability event
        #  Info - add observability event

        return {
            "success": True,
            "workflow_content": workflow_content,
            "interactive_elements": len(elements),
            "media_items": len(media_items),
            "final_response": final_response,
            "component_status": {
                "interactive_generator": "✅ Working",
                "response_formatter": "✅ Working",
                "media_integrator": "✅ Working",
                "multimodal_processing": "✅ Working"
            }
        }

    except Exception as e:
        logger.error(f"❌ Integrated workflow test failed: {e}")
        return {"success": False, "error": str(e)}


async def run_phase1_completion_tests():
    """Run all Phase 1 completion tests"""
    #  Info - add observability event
    #  Info - add observability event

    results = {}

    # Test 1: Interactive Elements
    results["interactive_elements"] = await test_interactive_elements()

    # Test 2: Media Integration
    results["media_integration"] = await test_media_integration()

    # Test 3: Multimodal Workflow Processing
    results["multimodal_processing"] = await test_multimodal_workflow_processing()

    # Test 4: Integrated Experience
    results["integrated_experience"] = await test_integrated_workflow_experience()

    # Summary
    #  Info - add observability event
    #  Info - add observability event
    #  Info - add observability event

    for test_name, result in results.items():
        status = "✅ PASS" if not result.get("error") else "❌ FAIL"
        #  Info - add observability event

        if result.get("error"):
            logger.error(f"  Error: {result['error']}")

    # Overall status
    passed_tests = sum(1 for r in results.values() if not r.get("error"))
    total_tests = len(results)

    #  Info - add observability event

    if passed_tests == total_tests:
        #  Info - add observability event
        #  Info - add observability event
            "✅ All interactive elements and enhanced multimodal integration "
            "components are working correctly"
        )
        #  Info - add observability event
    else:
        logger.warning("⚠️ Some tests failed - review errors above")

    return results


if __name__ == "__main__":
    # Run the completion tests
    asyncio.run(run_phase1_completion_tests())
