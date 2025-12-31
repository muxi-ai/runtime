import json
from typing import Dict, Any, List
from .base import BaseFormatter


class ElasticFormatter(BaseFormatter):
    """Elasticsearch bulk API formatter."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.index_name = config.get("index", "muxi-logs")

    @property
    def content_type(self) -> str:
        return "application/x-ndjson"

    def format_event(self, event: Dict[str, Any]) -> str:
        # Elasticsearch bulk format requires action line + document line
        action_line = json.dumps({"index": {"_index": self.index_name, "_type": "_doc"}})

        document = self._add_metadata(event)
        document_line = json.dumps(document)

        return f"{action_line}\n{document_line}"

    def format_batch(self, events: List[Dict[str, Any]]) -> str:
        lines = []
        for event in events:
            lines.append(self.format_event(event))
        return "\n".join(lines) + "\n"  # Bulk API requires trailing newline
