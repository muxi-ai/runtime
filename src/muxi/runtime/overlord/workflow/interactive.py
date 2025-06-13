"""
Interactive Response Elements Generator

This module provides rich interactive elements for enhanced user experiences,
including buttons, forms, visualizations, and rich media integration.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

# Loguru import removed - add observability import


class ElementType(Enum):
    """Types of interactive elements"""

    BUTTON = "button"
    FORM = "form"
    MENU = "menu"
    CHART = "chart"
    IMAGE = "image"
    TABLE = "table"
    CODE = "code"
    LINK = "link"
    MEDIA = "media"


class ButtonStyle(Enum):
    """Button styling options"""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"
    INFO = "info"


@dataclass
class InteractiveElement:
    """Base class for interactive elements"""

    element_id: str
    element_type: ElementType
    content: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Positioning and layout
    position: Optional[str] = None  # "inline", "block", "float"
    width: Optional[str] = None
    height: Optional[str] = None


@dataclass
class ButtonElement(InteractiveElement):
    """Interactive button element"""

    text: str = ""
    action: str = ""  # Action to trigger when clicked
    style: ButtonStyle = ButtonStyle.PRIMARY
    disabled: bool = False

    def __post_init__(self):
        self.element_type = ElementType.BUTTON
        self.content = {
            "text": self.text,
            "action": self.action,
            "style": self.style.value,
            "disabled": self.disabled,
        }


@dataclass
class FormElement(InteractiveElement):
    """Interactive form element"""

    title: str = ""
    fields: List[Dict[str, Any]] = field(default_factory=list)
    submit_action: str = ""
    cancel_action: Optional[str] = None

    def __post_init__(self):
        self.element_type = ElementType.FORM
        self.content = {
            "title": self.title,
            "fields": self.fields,
            "submit_action": self.submit_action,
            "cancel_action": self.cancel_action,
        }


@dataclass
class ChartElement(InteractiveElement):
    """Chart/visualization element"""

    chart_type: str = ""  # "bar", "line", "pie", "scatter", etc.
    data: Dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None

    def __post_init__(self):
        self.element_type = ElementType.CHART
        self.content = {"chart_type": self.chart_type, "data": self.data, "title": self.title}


@dataclass
class TableElement(InteractiveElement):
    """Table display element"""

    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    sortable: bool = True
    searchable: bool = True

    def __post_init__(self):
        self.element_type = ElementType.TABLE
        self.content = {
            "headers": self.headers,
            "rows": self.rows,
            "sortable": self.sortable,
            "searchable": self.searchable,
        }


class InteractiveElementGenerator:
    """
    Generates interactive elements for enhanced user experiences.

    Produces rich UI components including buttons, forms, charts, and media
    that can be embedded in responses to create engaging interactions.
    """

    def __init__(self):
        self.element_cache: Dict[str, InteractiveElement] = {}
        self.templates: Dict[str, Dict[str, Any]] = self._load_templates()

    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load predefined templates for common interactive elements"""
        return {
            "approval_buttons": {
                "approve": {"text": "✅ Approve", "style": "success"},
                "reject": {"text": "❌ Reject", "style": "danger"},
                "modify": {"text": "✏️ Modify", "style": "warning"},
            },
            "navigation_buttons": {
                "continue": {"text": "Continue →", "style": "primary"},
                "back": {"text": "← Back", "style": "secondary"},
                "cancel": {"text": "Cancel", "style": "secondary"},
            },
            "feedback_form": {
                "title": "Feedback",
                "fields": [
                    {"name": "rating", "type": "range", "min": 1, "max": 5, "label": "Rating"},
                    {"name": "comments", "type": "textarea", "label": "Comments", "optional": True},
                ],
            },
        }

    def create_button(
        self,
        text: str,
        action: str,
        style: ButtonStyle = ButtonStyle.PRIMARY,
        disabled: bool = False,
        **kwargs,
    ) -> ButtonElement:
        """Create an interactive button element"""
        element_id = kwargs.get("element_id", f"btn_{uuid.uuid4().hex[:8]}")

        button = ButtonElement(
            element_id=element_id,
            element_type=ElementType.BUTTON,
            content={},  # Will be set in __post_init__
            text=text,
            action=action,
            style=style,
            disabled=disabled,
            **kwargs,
        )

        self.element_cache[element_id] = button
        return button

    def create_approval_buttons(self, context: str = "") -> List[ButtonElement]:
        """Create standard approval button set"""
        context_suffix = f"_{context}" if context else ""

        buttons = []
        for action, config in self.templates["approval_buttons"].items():
            button = self.create_button(
                text=config["text"],
                action=f"{action}{context_suffix}",
                style=ButtonStyle(config["style"]),
            )
            buttons.append(button)

        return buttons

    def create_form(
        self,
        title: str,
        fields: List[Dict[str, Any]],
        submit_action: str,
        cancel_action: Optional[str] = None,
        **kwargs,
    ) -> FormElement:
        """Create an interactive form element"""
        element_id = kwargs.get("element_id", f"form_{uuid.uuid4().hex[:8]}")

        form = FormElement(
            element_id=element_id,
            element_type=ElementType.FORM,
            content={},  # Will be set in __post_init__
            title=title,
            fields=fields,
            submit_action=submit_action,
            cancel_action=cancel_action,
            **kwargs,
        )

        self.element_cache[element_id] = form
        return form

    def create_feedback_form(self, context: str = "general") -> FormElement:
        """Create a standard feedback form"""
        template = self.templates["feedback_form"]

        return self.create_form(
            title=template["title"],
            fields=template["fields"],
            submit_action=f"submit_feedback_{context}",
            cancel_action=f"cancel_feedback_{context}",
        )

    def create_chart(
        self, chart_type: str, data: Dict[str, Any], title: Optional[str] = None, **kwargs
    ) -> ChartElement:
        """Create a chart/visualization element"""
        element_id = kwargs.get("element_id", f"chart_{uuid.uuid4().hex[:8]}")

        chart = ChartElement(
            element_id=element_id,
            element_type=ElementType.CHART,
            content={},  # Will be set in __post_init__
            chart_type=chart_type,
            data=data,
            title=title,
            **kwargs,
        )

        self.element_cache[element_id] = chart
        return chart

    def create_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        sortable: bool = True,
        searchable: bool = True,
        **kwargs,
    ) -> TableElement:
        """Create a table element"""
        element_id = kwargs.get("element_id", f"table_{uuid.uuid4().hex[:8]}")

        table = TableElement(
            element_id=element_id,
            element_type=ElementType.TABLE,
            content={},  # Will be set in __post_init__
            headers=headers,
            rows=rows,
            sortable=sortable,
            searchable=searchable,
            **kwargs,
        )

        self.element_cache[element_id] = table
        return table

    def create_progress_chart(
        self, completed: int, total: int, title: str = "Progress"
    ) -> ChartElement:
        """Create a progress visualization"""
        percentage = (completed / total * 100) if total > 0 else 0

        data = {
            "labels": ["Completed", "Remaining"],
            "datasets": [
                {
                    "data": [completed, total - completed],
                    "backgroundColor": ["#4CAF50", "#E0E0E0"],
                    "borderWidth": 0,
                }
            ],
        }

        return self.create_chart(
            chart_type="doughnut",
            data=data,
            title=f"{title}: {completed}/{total} ({percentage:.1f}%)",
        )

    def create_workflow_status_table(self, workflow_data: Dict[str, Any]) -> TableElement:
        """Create a table showing workflow status"""
        headers = ["Task", "Status", "Progress", "Agent"]
        rows = []

        tasks = workflow_data.get("tasks", {})
        for task_id, task_info in tasks.items():
            status = task_info.get("status", "unknown")
            progress = task_info.get("progress", 0)
            agent = task_info.get("assigned_agent", "Unassigned")

            # Add status emoji
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
            }.get(status, "❓")

            rows.append(
                [
                    task_info.get("description", task_id),
                    f"{status_emoji} {status.title()}",
                    f"{progress}%",
                    agent,
                ]
            )

        return self.create_table(headers=headers, rows=rows, title="Workflow Status")


class ResponseFormatter:
    """
    Formats responses with rich content and interactive elements.

    Converts plain text responses into rich, engaging formats with
    embedded interactive elements, media, and enhanced formatting.
    """

    def __init__(self, element_generator: InteractiveElementGenerator):
        self.element_generator = element_generator
        self.format_processors = {
            "markdown": self._process_markdown,
            "html": self._process_html,
            "json": self._process_json,
            "plain": self._process_plain,
        }

    async def format_response(
        self,
        content: str,
        elements: List[InteractiveElement] = None,
        format_type: str = "markdown",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Format response with rich content and interactive elements.

        Args:
            content: Base response content
            elements: Interactive elements to embed
            format_type: Output format ("markdown", "html", "json")
            context: Additional context for formatting

        Returns:
            Formatted response with embedded elements
        """
        try:
            elements = elements or []
            context = context or {}

            # Process base content
            processor = self.format_processors.get(format_type, self._process_markdown)
            formatted_content = await processor(content, context)

            # Embed interactive elements
            embedded_content = await self._embed_elements(formatted_content, elements, format_type)

            # Generate response metadata
            metadata = {
                "format": format_type,
                "has_interactive_elements": len(elements) > 0,
                "element_count": len(elements),
                "element_types": [elem.element_type.value for elem in elements],
                "formatting_timestamp": datetime.now().isoformat(),
            }

            return {
                "content": embedded_content,
                "elements": [self._serialize_element(elem) for elem in elements],
                "metadata": metadata,
            }

        except Exception as e:
            #  Error - add observability event
            return {
                "content": content,
                "elements": [],
                "metadata": {"format": "plain", "error": str(e)},
            }

    async def _process_markdown(self, content: str, context: Dict[str, Any]) -> str:
        """Process content as enhanced markdown"""
        # Add markdown enhancements
        enhanced_content = content

        # Add syntax highlighting hints
        if "```" in content:
            enhanced_content = self._enhance_code_blocks(enhanced_content)

        # Add table formatting
        if "|" in content and "\n" in content:
            enhanced_content = self._enhance_tables(enhanced_content)

        # Add emoji support
        enhanced_content = self._add_emoji_enhancements(enhanced_content)

        return enhanced_content

    async def _process_html(self, content: str, context: Dict[str, Any]) -> str:
        """Process content as HTML"""
        # Convert markdown-like syntax to HTML
        html_content = content.replace("\n", "<br>")
        html_content = self._markdown_to_html(html_content)

        return f"<div class='response-content'>{html_content}</div>"

    async def _process_json(self, content: str, context: Dict[str, Any]) -> str:
        """Process content as structured JSON"""
        return json.dumps({"type": "response", "content": content, "context": context}, indent=2)

    async def _process_plain(self, content: str, context: Dict[str, Any]) -> str:
        """Process content as plain text"""
        return content

    async def _embed_elements(
        self, content: str, elements: List[InteractiveElement], format_type: str
    ) -> str:
        """Embed interactive elements into formatted content"""
        if not elements:
            return content

        embedded_content = content

        # Add elements section
        if format_type == "markdown":
            embedded_content += "\n\n---\n\n"
            for element in elements:
                embedded_content += self._element_to_markdown(element) + "\n\n"

        elif format_type == "html":
            embedded_content += "\n<div class='interactive-elements'>\n"
            for element in elements:
                embedded_content += self._element_to_html(element) + "\n"
            embedded_content += "</div>"

        return embedded_content

    def _element_to_markdown(self, element: InteractiveElement) -> str:
        """Convert element to markdown representation"""
        if element.element_type == ElementType.BUTTON:
            style_emoji = {
                "primary": "🔵",
                "success": "✅",
                "warning": "⚠️",
                "danger": "❌",
                "info": "ℹ️",
            }.get(element.content.get("style", "primary"), "🔘")

            return f"{style_emoji} **{element.content['text']}** `[{element.content['action']}]`"

        elif element.element_type == ElementType.FORM:
            form_md = f"### 📝 {element.content['title']}\n\n"
            for form_field in element.content["fields"]:
                form_md += f"- **{form_field['label']}**: _{form_field['type']}_\n"
            return form_md

        elif element.element_type == ElementType.CHART:
            return (
                f"📊 **{element.content.get('title', 'Chart')}** "
                f"`[{element.content['chart_type']}]`"
            )

        elif element.element_type == ElementType.TABLE:
            table_md = "| " + " | ".join(element.content["headers"]) + " |\n"
            table_md += "|" + "---|" * len(element.content["headers"]) + "\n"
            for row in element.content["rows"]:
                table_md += "| " + " | ".join(str(cell) for cell in row) + " |\n"
            return table_md

        return f"🔧 **Interactive Element**: {element.element_type.value}"

    def _element_to_html(self, element: InteractiveElement) -> str:
        """Convert element to HTML representation"""
        element_html = (
            '<div class="interactive-element" '
            f'data-type="{element.element_type.value}" '
            f'data-id="{element.element_id}">'
        )

        if element.element_type == ElementType.BUTTON:
            element_html += (
                f'<button class="btn btn-{element.content["style"]}" '
                f'data-action="{element.content["action"]}">'
            )
            element_html += element.content["text"]
            element_html += "</button>"

        elif element.element_type == ElementType.TABLE:
            element_html += '<table class="data-table">'
            element_html += "<thead><tr>"
            for header in element.content["headers"]:
                element_html += f"<th>{header}</th>"
            element_html += "</tr></thead><tbody>"
            for row in element.content["rows"]:
                element_html += "<tr>"
                for cell in row:
                    element_html += f"<td>{cell}</td>"
                element_html += "</tr>"
            element_html += "</tbody></table>"

        element_html += "</div>"
        return element_html

    def _serialize_element(self, element: InteractiveElement) -> Dict[str, Any]:
        """Serialize element for JSON transport"""
        return {
            "id": element.element_id,
            "type": element.element_type.value,
            "content": element.content,
            "metadata": element.metadata,
            "position": element.position,
            "width": element.width,
            "height": element.height,
        }

    def _enhance_code_blocks(self, content: str) -> str:
        """Enhance code blocks with language detection"""
        # Simple enhancement - in production would use more sophisticated detection
        enhanced = content.replace("```\n", "```python\n")  # Default to Python
        return enhanced

    def _enhance_tables(self, content: str) -> str:
        """Enhance table formatting"""
        # Add table styling classes
        return content

    def _add_emoji_enhancements(self, content: str) -> str:
        """Add contextual emojis to enhance readability"""
        emoji_replacements = {
            "✅ Success": "✅ **Success**",
            "❌ Error": "❌ **Error**",
            "⚠️ Warning": "⚠️ **Warning**",
            "ℹ️ Info": "ℹ️ **Info**",
        }

        enhanced = content
        for original, replacement in emoji_replacements.items():
            enhanced = enhanced.replace(original, replacement)

        return enhanced

    def _markdown_to_html(self, content: str) -> str:
        """Basic markdown to HTML conversion"""
        # Simple conversions - in production would use a proper markdown parser
        html_content = content
        html_content = html_content.replace("**", "<strong>").replace("**", "</strong>")
        html_content = html_content.replace("*", "<em>").replace("*", "</em>")
        return html_content


class MediaIntegrator:
    """
    Integrates rich media content into responses.

    Handles embedding of images, charts, files, and other media
    into response content with proper formatting and accessibility.
    """

    def __init__(self):
        self.supported_media_types = {
            "image": ["png", "jpg", "jpeg", "gif", "svg", "webp"],
            "video": ["mp4", "webm", "ogg"],
            "audio": ["mp3", "wav", "ogg", "m4a"],
            "document": ["pdf", "doc", "docx", "txt", "md"],
        }

    async def embed_media(
        self, content: str, media_items: List[Dict[str, Any]], format_type: str = "markdown"
    ) -> str:
        """
        Embed media items into content.

        Args:
            content: Base content
            media_items: List of media items to embed
            format_type: Output format

        Returns:
            Content with embedded media
        """
        if not media_items:
            return content

        embedded_content = content

        for media_item in media_items:
            embedded_content += "\n\n"
            embedded_content += await self._embed_single_media(media_item, format_type)

        return embedded_content

    async def _embed_single_media(self, media_item: Dict[str, Any], format_type: str) -> str:
        """Embed a single media item"""
        media_type = media_item.get("type", "unknown")
        url = media_item.get("url", "")
        title = media_item.get("title", "Media")
        description = media_item.get("description", "")

        if format_type == "markdown":
            if media_type == "image":
                return (
                    f"![{title}]({url})\n\n*{description}*" if description else f"![{title}]({url})"
                )
            elif media_type == "video":
                return f"🎥 **{title}**\n\n[Watch Video]({url})\n\n*{description}*"
            elif media_type == "audio":
                return f"🎵 **{title}**\n\n[Listen]({url})\n\n*{description}*"
            elif media_type == "document":
                return f"📄 **{title}**\n\n[Download]({url})\n\n*{description}*"

        elif format_type == "html":
            if media_type == "image":
                return (
                    f'<img src="{url}" alt="{title}" title="{title}"><p><em>{description}</em></p>'
                )
            elif media_type == "video":
                return (
                    f'<video controls><source src="{url}" type="video/mp4"></video>'
                    f'<p><strong>{title}</strong><br><em>{description}</em></p>'
                )

        return f"📎 **{title}**: {url}"

    def create_chart_from_data(
        self, data: Dict[str, Any], chart_type: str = "bar", title: str = "Chart"
    ) -> Dict[str, Any]:
        """Create chart configuration from data"""
        return {
            "type": "chart",
            "title": title,
            "config": {
                "type": chart_type,
                "data": data,
                "options": {
                    "responsive": True,
                    "plugins": {"title": {"display": True, "text": title}},
                },
            },
        }
