"""
Interactive Response Elements Generator

This module provides rich interactive elements for enhanced user experiences,
including buttons, forms, visualizations, and rich media integration.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from ...utils.id_generator import generate_nanoid

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
        element_id = kwargs.get("element_id", f"btn_{generate_nanoid()}")

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
        element_id = kwargs.get("element_id", f"form_{generate_nanoid()}")

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
        element_id = kwargs.get("element_id", f"chr_{generate_nanoid()}")

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
        element_id = kwargs.get("element_id", f"tbl_{generate_nanoid()}")

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
                    f"<p><strong>{title}</strong><br><em>{description}</em></p>"
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
