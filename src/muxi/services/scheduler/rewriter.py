"""
MUXI Scheduler Prompt Rewriter

Transforms natural language scheduling requests into executable prompts
optimized for scheduled execution through the MUXI formation.

Key Features:
- Context preservation for scheduled execution
- Temporal adjustment for "now" vs scheduled time
- User intent clarification and expansion
- Formation-aware prompt optimization
- Multi-language support through LLM processing

Transformation Examples:
- "Check my email" → "Check email for new messages and summarize important items"
- "Remind me about the meeting" → "Send reminder: You have a meeting scheduled"
- "Generate daily report" → "Generate and deliver daily activity report for [current date]"
- "Monitor system status" → "Check system health and alert if any issues found"

The rewriter ensures prompts are:
1. Self-contained (no ambiguous references)
2. Actionable (clear instructions for AI execution)
3. Context-aware (understands it's running scheduled)
4. Time-sensitive (handles temporal references appropriately)
"""

import re
from typing import Dict, Optional, Any

from .. import observability
from ...services.llm import LLM


class PromptRewriter:
    """
    Natural language prompt rewriter for scheduled execution.

    Transforms user scheduling requests into optimized execution prompts
    that work well in scheduled/automated contexts.
    """

    def __init__(self):
        """Initialize prompt rewriter."""
        self.llm = None  # Will be initialized when needed

        # Common transformations for scheduled contexts
        self.scheduled_context_patterns = {
            'check': 'Check and report on',
            'remind me': 'Send reminder:',
            'tell me': 'Provide update on',
            'show me': 'Display information about',
            'let me know': 'Notify about',
            'update me': 'Provide status update on',
        }

        # Temporal reference transformations
        self.temporal_transforms = {
            'now': 'at this scheduled time',
            'right now': 'at this scheduled time',
            'currently': 'at this scheduled time',
            'today': 'for today',
            'this morning': 'this morning',
            'this afternoon': 'this afternoon',
            'this evening': 'this evening',
        }

        pass  # REMOVED: init-phase observe() call

    async def _get_llm(self) -> Optional[LLM]:
        """Get LLM instance for prompt processing."""
        if not self.llm:
            try:
                self.llm = LLM()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.LLM_INITIALIZATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description="Failed to initialize LLM for prompt rewriting"
                )
                return None
        return self.llm

    async def rewrite_for_execution(self, original_prompt: str,
                                    schedule_context: Optional[str] = None) -> str:
        """
        Rewrite original prompt for scheduled execution.

        Args:
            original_prompt: Original natural language request
            schedule_context: Optional schedule context information

        Returns:
            Rewritten prompt optimized for execution
        """
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "original_length": len(original_prompt),
                "has_schedule_context": bool(schedule_context),
                "component": "prompt_rewriter"
            },
            description="Starting prompt rewriting for scheduled execution"
        )

        # Use LLM-based rewriting directly (pattern-based removed)
        rewritten = await self._llm_rewrite_prompt(original_prompt, schedule_context)

        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "original_prompt": original_prompt,
                "rewritten_prompt": rewritten,
                "method": "llm_based",
                "component": "prompt_rewriter"
            },
            description="Prompt rewritten using LLM"
        )

        return rewritten

    async def _try_pattern_rewriting(self, prompt: str) -> str:
        """
        Try pattern-based rewriting for common cases.

        Args:
            prompt: Original prompt

        Returns:
            Rewritten prompt or original if no patterns matched
        """
        prompt_lower = prompt.lower().strip()

        # Apply scheduled context transformations
        for pattern, replacement in self.scheduled_context_patterns.items():
            if prompt_lower.startswith(pattern):
                rest_of_prompt = prompt[len(pattern):].strip()
                return f"{replacement} {rest_of_prompt}".strip()

        # Apply temporal transformations
        rewritten = prompt
        for temporal_ref, replacement in self.temporal_transforms.items():
            rewritten = rewritten.replace(temporal_ref, replacement)

        # Add context if it looks like a command without clear action
        simple_commands = ['email', 'status', 'report', 'weather', 'news']
        if prompt_lower in simple_commands:
            return f"Check and provide update on {prompt_lower}"

        # If prompt is very short, expand it
        if len(prompt.split()) <= 2 and not prompt.endswith('?'):
            return f"Provide information and status update on: {prompt}"

        return rewritten

    async def _llm_rewrite_prompt(self, original_prompt: str,
                                  schedule_context: Optional[str] = None) -> str:
        """
        Rewrite prompt using LLM for complex cases.

        Args:
            original_prompt: Original natural language request
            schedule_context: Optional schedule context

        Returns:
            Rewritten prompt optimized for execution
        """
        llm = await self._get_llm()

        if not llm:
            # Simple fallback when LLM unavailable
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.WARNING,
                description="LLM unavailable for prompt rewriting, using original prompt"
            )
            return original_prompt

        context_info = f"\nSchedule Context: {schedule_context}" if schedule_context else ""

        from ...formation.prompts.loader import PromptLoader
        prompt = PromptLoader.get(
            'scheduler_prompt_rewriter.md',
            original_prompt=original_prompt,
            context_info=context_info
        )

        try:
            response = await llm.generate_text(prompt)
            rewritten = response.strip()

            # Ensure we got a reasonable response
            if len(rewritten) > 0 and rewritten != original_prompt:
                return rewritten
            else:
                # Fallback to simple pattern rewriting
                return f"Execute scheduled task: {original_prompt}"

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "original_prompt": original_prompt,
                    "error": str(e)
                },
                description=f"LLM prompt rewriting failed: {e}"
            )
            # Fallback to simple enhancement
            return f"Execute scheduled task: {original_prompt}"

    async def enhance_for_formation(self, prompt: str, formation_config: Dict[str, Any]) -> str:
        """
        Enhance prompt based on formation configuration and capabilities.

        Args:
            prompt: Base prompt to enhance
            formation_config: Formation configuration dict

        Returns:
            Enhanced prompt optimized for the formation
        """
        observability.observe(
            event_type=observability.ConversationEvents.PROMPT_FORMATION_ENHANCEMENT_STARTED,
            level=observability.EventLevel.INFO,
            data={"original_length": len(prompt)},
            description="Starting formation-specific prompt enhancement"
        )

        # Get available agents and their capabilities
        agents = formation_config.get('agents', [])
        available_capabilities = []

        for agent in agents:
            if isinstance(agent, dict):
                agent_id = agent.get('id', '')
                specialization = agent.get('specialization', '')
                if specialization:
                    available_capabilities.append(f"{agent_id}: {specialization}")

        # Get available MCP tools
        mcp_servers = formation_config.get('mcp', {}).get('servers', [])
        available_tools = []

        for server in mcp_servers:
            if isinstance(server, dict):
                server_id = server.get('id', '')
                description = server.get('description', '')
                if description:
                    available_tools.append(f"{server_id}: {description}")

        if not available_capabilities and not available_tools:
            # No enhancement needed if no capabilities info
            return prompt

        llm = await self._get_llm()

        if not llm:
            # No enhancement possible without LLM
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.WARNING,
                description="LLM unavailable for formation enhancement, returning original prompt"
            )
            return prompt

        capabilities_info = ""
        if available_capabilities:
            capabilities_info += "\nAvailable Agents:\n" + "\n".join(f"- {cap}" for cap in available_capabilities)

        if available_tools:
            capabilities_info += "\nAvailable Tools:\n" + "\n".join(f"- {tool}" for tool in available_tools)

        from ...formation.prompts.loader import PromptLoader
        enhancement_prompt = PromptLoader.get(
            'scheduler_enhancement.md',
            prompt=prompt,
            capabilities_info=capabilities_info
        )

        try:
            response = await llm.generate_text(enhancement_prompt)
            enhanced = response.strip()

            if len(enhanced) > 0 and enhanced != prompt:
                observability.observe(
                    event_type=observability.ConversationEvents.PROMPT_FORMATION_ENHANCED,
                    level=observability.EventLevel.INFO,
                    data={
                        "original_prompt": prompt,
                        "enhanced_prompt": enhanced,
                        "capabilities_count": len(available_capabilities) + len(available_tools)
                    },
                    description="Prompt enhanced for formation capabilities"
                )
                return enhanced

            return prompt

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "original_prompt": prompt,
                    "error": str(e)
                },
                description=f"Formation prompt enhancement failed: {e}"
            )
            return prompt

    async def add_scheduling_context(self, prompt: str, schedule_info: Dict[str, Any]) -> str:
        """
        Add scheduling context information to the prompt.

        Args:
            prompt: Base prompt
            schedule_info: Dictionary with schedule information
                - frequency: How often it runs
                - next_run: When it will run next
                - timezone: Timezone information
                - user_id: User who created the schedule

        Returns:
            Prompt with scheduling context added
        """
        context_parts = []

        if schedule_info.get('frequency'):
            context_parts.append(f"This is a scheduled task that runs {schedule_info['frequency']}")

        if schedule_info.get('timezone'):
            context_parts.append(f"in {schedule_info['timezone']} timezone")

        if schedule_info.get('user_id'):
            context_parts.append(f"for user {schedule_info['user_id']}")

        if context_parts:
            context_prefix = f"[Scheduled Task Context: {'. '.join(context_parts)}]\n\n"
            return context_prefix + prompt

        return prompt

    async def validate_execution_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Validate that an execution prompt is suitable for scheduled execution.

        Args:
            prompt: Execution prompt to validate

        Returns:
            Validation result dict with 'valid', 'issues', and 'suggestions' keys
        """
        issues = []
        suggestions = []

        # Check for common issues
        prompt_lower = prompt.lower()

        # Check for ambiguous references
        ambiguous_words = ['this', 'that', 'here', 'there', 'it']
        for word in ambiguous_words:
            if f' {word} ' in f' {prompt_lower} ':
                issues.append(f"Contains ambiguous reference: '{word}'")
                suggestions.append(f"Replace '{word}' with specific reference")

        # Check for temporal issues
        problematic_temporals = ['right now', 'currently', 'at the moment']
        for temporal in problematic_temporals:
            if temporal in prompt_lower:
                issues.append(f"Contains problematic temporal reference: '{temporal}'")
                suggestions.append(f"Replace '{temporal}' with 'at this scheduled time' or similar")

        # Check for interactivity assumptions
        interactive_words = ['show me', 'tell me', 'let me know']
        has_interactive = any(word in prompt_lower for word in interactive_words)

        if has_interactive and 'send' not in prompt_lower and 'notify' not in prompt_lower:
            suggestions.append("Consider adding delivery mechanism (e.g., 'send summary', 'notify via webhook')")

        # Check prompt length
        if len(prompt.split()) < 3:
            issues.append("Prompt may be too short for clear execution")
            suggestions.append("Add more context about expected action and output")

        # Check for action words
        action_words = ['check', 'get', 'fetch', 'generate', 'create', 'send', 'notify', 'report', 'update', 'monitor']
        has_action = any(word in prompt_lower for word in action_words)

        if not has_action:
            issues.append("Prompt lacks clear action verb")
            suggestions.append("Add action verb (check, generate, send, etc.)")

        validation_result = {
            'valid': len(issues) == 0,
            'issues': issues,
            'suggestions': suggestions,
            'score': max(0, 10 - len(issues) * 2)  # Simple scoring system
        }

        observability.observe(
            event_type=observability.ConversationEvents.PROMPT_VALIDATION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "prompt_length": len(prompt),
                "valid": validation_result['valid'],
                "issues_count": len(issues),
                "suggestions_count": len(suggestions),
                "score": validation_result['score']
            },
            description="Execution prompt validation completed"
        )

        return validation_result

    def _enhanced_pattern_rewrite(self, original_prompt: str, schedule_context: Optional[str] = None) -> str:
        """
        Enhanced pattern-based rewriting without LLM.

        Args:
            original_prompt: Original natural language request
            schedule_context: Optional schedule context

        Returns:
            Enhanced prompt for scheduled execution
        """
        # Start with basic pattern rewriting
        rewritten = self._try_pattern_rewriting(original_prompt)

        # Add schedule context if available
        if schedule_context:
            rewritten = f"[Scheduled Context: {schedule_context}] {rewritten}"

        # Enhance with common scheduled execution patterns
        enhancements = [
            # Make it more specific for automation
            (r'^(check|get|fetch) (.+)$', r'\1 \2 and provide a summary'),
            (r'^(tell|show) (.+)$', r'Report on \2'),
            (r'^(remind|alert) (.+)$', r'Send notification: \2'),
            (r'^(update|status) (.+)$', r'Provide status update on \2'),
            (r'^(monitor) (.+)$', r'Monitor \2 and report any changes'),
        ]

        for pattern, replacement in enhancements:
            if re.match(pattern, rewritten.lower()):
                rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
                break

        # Ensure it's actionable
        action_words = ['check', 'get', 'send', 'report', 'provide', 'monitor', 'generate']
        if not any(word in rewritten.lower() for word in action_words):
            rewritten = f"Execute and report on: {rewritten}"

        return rewritten

    async def generate_execution_summary_prompt(self, original_request: str,
                                                schedule_pattern: str) -> str:
        """
        Generate a prompt for summarizing execution results.

        Args:
            original_request: Original user request
            schedule_pattern: Schedule pattern (e.g., "daily", "weekly")

        Returns:
            Prompt for summarizing execution results
        """
        return f"""
Summarize the execution results for the scheduled task: "{original_request}"

This task runs {schedule_pattern}. Provide a concise summary that includes:
1. What was accomplished
2. Key findings or information discovered
3. Any issues or errors encountered
4. Next steps or recommendations if applicable

Keep the summary focused and actionable for the user who scheduled this task.
"""
