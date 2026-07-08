"""
Trigger transformers: response formatting and outbound routing.

Transformers are declarative YAML files (in the formation's ``transformers/``
directory) that describe how to format an agent response and where to deliver
it. Triggers opt in via YAML frontmatter in their markdown templates:

    ---
    transformer: slack
    parse:
      message: $.event.text
      user_id: $.event.user
      context:
        channel: $.event.channel
    ---
    Respond to this Slack message: ${{ data.event.text }}

Transformer YAML (``transformers/slack.yaml``):

    name: slack
    endpoint:
      url: https://slack.com/api/chat.postMessage
      method: POST
    auth:
      type: bearer
      token: "${{ secrets.SLACK_BOT_TOKEN }}"
    body:
      channel: "${{ context.channel }}"
      text: "${{ response.content }}"

``endpoint.url`` is optional: a transformer may define only the payload
format and let the referencing trigger (``webhook:`` frontmatter) or
proactive channel (``url:`` key) supply the destination. When both exist,
the trigger/channel-supplied URL wins. A transformer with no URL anywhere
is a load-time error (see ``resolve_transformer_url``).

``transformer:`` and ``webhook:`` in trigger frontmatter therefore compose:
the transformer defines the payload format/auth/retry, the trigger's webhook
URL is the delivery destination. ``webhook:`` alone still delivers the raw
standard payload; ``transformer:`` alone delivers to the transformer's own
``endpoint.url``.

Bundled dormant templates: the runtime ships payload-format-only templates
(slack, telegram, discord, email) under ``builtin/transformers/`` next to
this module. ``load_transformer`` resolves formation-local files first, so
a formation ``transformers/<name>.yaml`` shadows a bundled template of the
same name (the same rule as built-in skills). Formations that never
reference a bundled name are completely unaffected.

Template values use the runtime-wide ``${{ ... }}`` syntax (the same syntax
used by trigger templates and formation secrets interpolation). Available
variables: ``response.content``, ``response.files``, ``response.metadata.*``,
``request.message``, ``request.user_id``, ``request.files``, ``context.*``,
``secrets.*``, ``agent.name``, and ``timestamp``.

Triggers without frontmatter are completely unaffected: parsing returns the
content unchanged and no transformer machinery is invoked.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from ...services import observability

# Trigger/transformer names: same charset as trigger name validation in the
# triggers route (prevents path traversal when resolving files on disk).
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# ${{ variable.path }} placeholders in transformer config values.
_PLACEHOLDER_PATTERN = re.compile(
    r"\$\{\{\s*([a-zA-Z0-9_](?:[a-zA-Z0-9_.-]*[a-zA-Z0-9_-])?)\s*\}\}"
)

# YAML frontmatter block at the very start of a trigger markdown file.
_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_AUTH_TYPES = {"bearer", "basic", "header"}
_ALLOWED_FORMATS = {"text", "markdown", "html"}

_ALLOWED_FRONTMATTER_KEYS = {"name", "type", "webhook", "transformer", "parse", "model", "channel"}

# Bundled dormant channel templates shipped with the runtime (payload formats
# only, no URLs). Formation-local transformers/<name>.yaml shadows a bundled
# template of the same name.
BUILTIN_TRANSFORMERS_DIR = Path(__file__).parent / "builtin" / "transformers"
_ALLOWED_PARSE_KEYS = {"message", "user_id", "context", "files"}


# ---------------------------------------------------------------------------
# Trigger frontmatter
# ---------------------------------------------------------------------------


def parse_trigger_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse optional YAML frontmatter from a trigger markdown template.

    Triggers without frontmatter are returned unchanged: ``({}, content)``.
    A leading ``---`` without a closing delimiter is treated as plain
    markdown (horizontal rule), not frontmatter.

    Args:
        content: Raw trigger file content

    Returns:
        Tuple of (frontmatter dict, template body without frontmatter)

    Raises:
        ValueError: If the frontmatter block is malformed (invalid YAML,
            non-mapping, unknown keys, or invalid routing fields)
    """
    if not content.startswith("---"):
        return {}, content

    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        # No closing delimiter: treat as plain markdown, not frontmatter
        return {}, content

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML in trigger frontmatter: {e}")

    body_start = match.end()
    if meta is None:
        return {}, content[body_start:]
    if not isinstance(meta, dict):
        raise ValueError("trigger frontmatter must be a YAML mapping")

    unknown = set(meta.keys()) - _ALLOWED_FRONTMATTER_KEYS
    if unknown:
        raise ValueError(
            f"unknown trigger frontmatter key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_FRONTMATTER_KEYS)}"
        )

    # 'webhook' and 'transformer' compose when both are present: the
    # transformer defines the payload format/auth/retry and the webhook URL
    # is the delivery destination. Alone, each keeps its original semantics
    # (webhook = raw standard payload, transformer = its own endpoint.url).
    webhook = meta.get("webhook")
    transformer = meta.get("transformer")
    if webhook is not None:
        if not isinstance(webhook, str) or not webhook.strip():
            raise ValueError("'webhook' must be a non-empty URL string")
        if not webhook.startswith(("http://", "https://")):
            raise ValueError("'webhook' must be an http(s) URL")
    if transformer is not None:
        if not isinstance(transformer, str) or not _NAME_PATTERN.match(transformer):
            raise ValueError(
                "'transformer' must be a name containing only letters, "
                "numbers, hyphens, and underscores"
            )

    parse_spec = meta.get("parse")
    if parse_spec is not None:
        _validate_parse_spec(parse_spec)

    model = meta.get("model")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("'model' must be a non-empty string (alias or provider/model)")

    channel = meta.get("channel")
    if channel is not None:
        if not isinstance(channel, str) or not _NAME_PATTERN.match(channel):
            raise ValueError(
                "'channel' must be a name containing only letters, numbers, "
                "hyphens, and underscores"
            )

    return meta, content[body_start:]


def _validate_parse_spec(parse_spec: Any) -> None:
    """Validate the ``parse:`` section of trigger frontmatter (fail fast)."""
    if not isinstance(parse_spec, dict):
        raise ValueError("'parse' must be a mapping")
    unknown = set(parse_spec.keys()) - _ALLOWED_PARSE_KEYS
    if unknown:
        raise ValueError(
            f"unknown 'parse' key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_PARSE_KEYS)}"
        )
    for key in ("message", "user_id", "files"):
        value = parse_spec.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"'parse.{key}' must be a path string (e.g. '$.event.text')")
    context = parse_spec.get("context")
    if context is not None:
        if not isinstance(context, dict):
            raise ValueError("'parse.context' must be a mapping of name -> path")
        for ctx_key, ctx_path in context.items():
            if not isinstance(ctx_path, str):
                raise ValueError(f"'parse.context.{ctx_key}' must be a path string")


def extract_path(data: Any, path: str) -> Any:
    """
    Extract a value from nested data using a simple dot path.

    Supports ``$.a.b``, ``a.b.c``, and list indexing via ``[0]`` or numeric
    segments (``$.items[0].name`` or ``items.0.name``). Returns ``None`` when
    any segment is missing (parse extraction is best-effort by design:
    platform payloads routinely omit optional fields like ``thread_ts``).

    Args:
        data: The payload to extract from
        path: Dot path expression

    Returns:
        The extracted value, or None if not found
    """
    if not isinstance(path, str) or not path.strip():
        return None

    normalized = path.strip()
    if normalized.startswith("$"):
        normalized = normalized[1:]
    # [0] -> .0 so everything splits uniformly on dots
    normalized = normalized.replace("[", ".").replace("]", "")
    segments = [s for s in normalized.split(".") if s]

    value = data
    for segment in segments:
        if isinstance(value, dict):
            if segment not in value:
                return None
            value = value[segment]
        elif isinstance(value, list):
            if not segment.lstrip("-").isdigit():
                return None
            index = int(segment)
            if not -len(value) <= index < len(value):
                return None
            value = value[index]
        else:
            return None
    return value


def extract_parse_values(parse_spec: Optional[Dict[str, Any]], data: Any) -> Dict[str, Any]:
    """
    Extract request values from trigger data per the frontmatter ``parse:`` spec.

    Args:
        parse_spec: The (already validated) parse section, or None
        data: The raw trigger request data

    Returns:
        Dict with keys: message, user_id, files, context
    """
    if not parse_spec:
        return {"message": None, "user_id": None, "files": None, "context": {}}

    _validate_parse_spec(parse_spec)

    context: Dict[str, Any] = {}
    for ctx_key, ctx_path in (parse_spec.get("context") or {}).items():
        context[ctx_key] = extract_path(data, ctx_path)

    user_id = None
    if parse_spec.get("user_id"):
        raw_user_id = extract_path(data, parse_spec["user_id"])
        if raw_user_id is not None:
            user_id = str(raw_user_id)

    message = None
    if parse_spec.get("message"):
        raw_message = extract_path(data, parse_spec["message"])
        if raw_message is not None:
            message = str(raw_message)

    files = None
    if parse_spec.get("files"):
        files = extract_path(data, parse_spec["files"])

    return {"message": message, "user_id": user_id, "files": files, "context": context}


# ---------------------------------------------------------------------------
# Transformer configuration
# ---------------------------------------------------------------------------


@dataclass
class TransformerAuth:
    """Authentication section of a transformer config."""

    type: str
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    header_name: Optional[str] = None
    header_value: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Any) -> "TransformerAuth":
        if not isinstance(raw, dict):
            raise ValueError("'auth' must be a mapping")
        auth_type = raw.get("type")
        if auth_type not in _ALLOWED_AUTH_TYPES:
            raise ValueError(
                f"'auth.type' must be one of {sorted(_ALLOWED_AUTH_TYPES)}, got {auth_type!r}"
            )
        required = {
            "bearer": ["token"],
            "basic": ["username", "password"],
            "header": ["header_name", "header_value"],
        }[auth_type]
        for key in required:
            value = raw.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"'auth.{key}' is required for auth type '{auth_type}'")
        return cls(
            type=auth_type,
            token=raw.get("token"),
            username=raw.get("username"),
            password=raw.get("password"),
            header_name=raw.get("header_name"),
            header_value=raw.get("header_value"),
        )


@dataclass
class ContentTransform:
    """Optional response-content transformation before body templating."""

    format: Optional[str] = None
    max_length: Optional[int] = None
    truncation_suffix: str = "..."

    @classmethod
    def from_dict(cls, raw: Any) -> "ContentTransform":
        if not isinstance(raw, dict):
            raise ValueError("'content_transform' must be a mapping")
        fmt = raw.get("format")
        if fmt is not None and fmt not in _ALLOWED_FORMATS:
            raise ValueError(
                f"'content_transform.format' must be one of {sorted(_ALLOWED_FORMATS)}, "
                f"got {fmt!r}"
            )
        max_length = raw.get("max_length")
        if max_length is not None:
            if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length <= 0:
                raise ValueError("'content_transform.max_length' must be a positive integer")
        suffix = raw.get("truncation_suffix", "...")
        if not isinstance(suffix, str):
            raise ValueError("'content_transform.truncation_suffix' must be a string")
        return cls(format=fmt, max_length=max_length, truncation_suffix=suffix)


@dataclass
class TransformerConfig:
    """Parsed and validated transformer definition.

    ``url`` is None for payload-format-only transformers (e.g. the bundled
    channel templates): the referencing trigger/channel must then supply the
    destination URL (see ``resolve_transformer_url``).
    """

    name: str
    url: Optional[str] = None
    method: str = "POST"
    version: Optional[str] = None
    auth: Optional[TransformerAuth] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    content_transform: Optional[ContentTransform] = None

    @classmethod
    def from_dict(cls, raw: Any) -> "TransformerConfig":
        """
        Build a TransformerConfig from a parsed YAML dict, failing fast on
        any structural problem with a descriptive error message.
        """
        if not isinstance(raw, dict):
            raise ValueError("transformer config must be a YAML mapping")

        name = raw.get("name")
        if not isinstance(name, str) or not _NAME_PATTERN.match(name):
            raise ValueError(
                "'name' is required and must contain only letters, numbers, "
                "hyphens, and underscores"
            )

        # 'endpoint' (and 'endpoint.url') is optional: payload-format-only
        # transformers rely on the referencing trigger/channel for the URL.
        endpoint = raw.get("endpoint")
        url = None
        method = "POST"
        if endpoint is not None:
            if not isinstance(endpoint, dict):
                raise ValueError("'endpoint' must be a mapping")
            url = endpoint.get("url")
            if url is not None and (not isinstance(url, str) or not url.strip()):
                raise ValueError("'endpoint.url' must be a non-empty string when present")
            method = endpoint.get("method", "POST")
            if not isinstance(method, str) or method.upper() not in _ALLOWED_METHODS:
                raise ValueError(
                    f"'endpoint.method' must be one of {sorted(_ALLOWED_METHODS)}, got {method!r}"
                )

        version = raw.get("version")
        if version is not None and not isinstance(version, str):
            raise ValueError("'version' must be a string")

        auth = None
        if raw.get("auth") is not None:
            auth = TransformerAuth.from_dict(raw["auth"])

        headers = raw.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("'headers' must be a mapping")
        for header_name, header_value in headers.items():
            if not isinstance(header_name, str) or not isinstance(header_value, str):
                raise ValueError("'headers' keys and values must be strings")

        body = raw.get("body")
        if body is not None and not isinstance(body, (dict, list, str)):
            raise ValueError("'body' must be a mapping, list, or string template")

        content_transform = None
        if raw.get("content_transform") is not None:
            content_transform = ContentTransform.from_dict(raw["content_transform"])

        return cls(
            name=name,
            url=url,
            method=method.upper(),
            version=version,
            auth=auth,
            headers=dict(headers),
            body=body,
            content_transform=content_transform,
        )


def load_transformer(formation_dir: Path, name: str) -> TransformerConfig:
    """
    Load and validate a transformer definition.

    Formation-local files are resolved first; when absent, the bundled
    dormant templates shipped with the runtime are consulted, so a
    formation ``transformers/<name>.yaml`` shadows a bundled template of
    the same name (the same shadowing rule as built-in skills). Bundled
    templates are inert until referenced by name.

    Args:
        formation_dir: Formation root directory
        name: Transformer name (resolves ``transformers/<name>.yaml``,
            then ``builtin/transformers/<name>.yaml``)

    Returns:
        Validated TransformerConfig

    Raises:
        ValueError: If the name is invalid, no file exists in either
            location, or the config fails validation
    """
    if not _NAME_PATTERN.match(name):
        raise ValueError(
            f"invalid transformer name {name!r}: must contain only letters, "
            "numbers, hyphens, and underscores"
        )

    transformers_dir = Path(formation_dir) / "transformers"
    for directory in (transformers_dir, BUILTIN_TRANSFORMERS_DIR):
        for suffix in (".yaml", ".yml"):
            candidate = directory / f"{name}{suffix}"
            if candidate.exists():
                try:
                    raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))
                except yaml.YAMLError as e:
                    raise ValueError(f"transformer '{name}' contains invalid YAML: {e}")
                config = TransformerConfig.from_dict(raw)
                if config.name != name:
                    raise ValueError(
                        f"transformer file '{candidate.name}' declares name "
                        f"{config.name!r}; it must match the filename"
                    )
                return config

    raise ValueError(
        f"transformer '{name}' not found in {transformers_dir} "
        "(and no bundled template has that name)"
    )


def resolve_transformer_url(
    transformer: TransformerConfig, override_url: Optional[str] = None
) -> str:
    """
    Resolve the delivery destination for a transformer.

    Resolution order: the trigger/channel-supplied URL first, then the
    transformer's own ``endpoint.url``. A transformer with no URL from
    either source is a configuration error (callers surface this at
    formation load time so a URL-less template referenced without a
    destination fails fast, not at delivery time).

    Args:
        transformer: The loaded transformer config
        override_url: URL supplied by the referencing trigger (``webhook:``
            frontmatter) or proactive channel (``url:`` key), if any

    Returns:
        The URL to deliver to (may still contain ``${{ ... }}`` placeholders)

    Raises:
        ValueError: If neither the caller nor the transformer supplies a URL
    """
    url = override_url or transformer.url
    if not url:
        raise ValueError(
            f"transformer '{transformer.name}' defines no 'endpoint.url' and the "
            "referencing trigger/channel supplies no destination URL; add "
            "'endpoint.url' to the transformer, a 'webhook:' to the trigger "
            "frontmatter, or a 'url:' to the proactive channel declaration"
        )
    return url


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _resolve_variable(path: str, variables: Dict[str, Any]) -> Any:
    """
    Resolve a dotted variable path against the template variables.

    Missing ``secrets.*`` references raise (a misconfigured integration must
    not silently send requests with empty credentials); any other missing
    path resolves to None (platform context is routinely sparse).
    """
    keys = path.split(".")
    value: Any = variables
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.lstrip("-").isdigit():
            index = int(key)
            if -len(value) <= index < len(value):
                value = value[index]
            else:
                return None
        else:
            if keys[0] == "secrets":
                raise ValueError(f"secret '{'.'.join(keys[1:])}' is not available")
            return None
    return value


def render_template_string(template: str, variables: Dict[str, Any]) -> Any:
    """
    Render a single template string.

    If the whole string is exactly one placeholder, the resolved value is
    returned natively (lists, dicts, and numbers survive un-stringified so
    e.g. ``attachments: "${{ response.files }}"`` yields a real list).
    Otherwise placeholders are substituted as strings, with None rendered
    as an empty string.
    """
    stripped = template.strip()
    if template == stripped:
        whole = _PLACEHOLDER_PATTERN.fullmatch(stripped)
        if whole:
            return _resolve_variable(whole.group(1), variables)

    def _substitute(match: "re.Match[str]") -> str:
        resolved = _resolve_variable(match.group(1), variables)
        return "" if resolved is None else str(resolved)

    return _PLACEHOLDER_PATTERN.sub(_substitute, template)


def render_template_value(value: Any, variables: Dict[str, Any]) -> Any:
    """
    Recursively render template placeholders in a config value.

    Dict entries that render to None are dropped (e.g. an absent
    ``thread_ts`` should not be sent as an explicit null).
    """
    if isinstance(value, str):
        return render_template_string(value, variables)
    if isinstance(value, dict):
        rendered = {}
        for key, item in value.items():
            rendered_item = render_template_value(item, variables)
            if rendered_item is not None:
                rendered[key] = rendered_item
        return rendered
    if isinstance(value, list):
        return [render_template_value(item, variables) for item in value]
    return value


def collect_secret_names(config: TransformerConfig, *extra_values: Any) -> Set[str]:
    """
    Collect all ``${{ secrets.* }}`` names referenced by a transformer.

    ``extra_values`` allows callers to include additional template strings
    in the scan (e.g. a trigger/channel-supplied destination URL, which may
    itself reference a secret such as a Slack incoming-webhook URL).
    """
    secret_names: Set[str] = set()

    def _scan(value: Any) -> None:
        if isinstance(value, str):
            for match in _PLACEHOLDER_PATTERN.finditer(value):
                parts = match.group(1).split(".")
                if parts[0] == "secrets" and len(parts) > 1:
                    secret_names.add(parts[1])
        elif isinstance(value, dict):
            for item in value.values():
                _scan(item)
        elif isinstance(value, list):
            for item in value:
                _scan(item)

    _scan(config.url)
    _scan(config.headers)
    _scan(config.body)
    if config.auth:
        _scan(config.auth.token)
        _scan(config.auth.username)
        _scan(config.auth.password)
        _scan(config.auth.header_value)
    for extra in extra_values:
        _scan(extra)
    return secret_names


async def resolve_secrets(secret_names: Set[str], secrets_manager: Any) -> Dict[str, str]:
    """
    Resolve referenced secrets via the formation SecretsManager.

    Raises:
        ValueError: If a referenced secret is missing or no secrets manager
            is available while secrets are referenced
    """
    if not secret_names:
        return {}
    if secrets_manager is None:
        raise ValueError(
            f"transformer references secrets {sorted(secret_names)} but no "
            "secrets manager is available"
        )
    resolved: Dict[str, str] = {}
    for secret_name in sorted(secret_names):
        value = await secrets_manager.get_secret(secret_name)
        if value is None:
            raise ValueError(f"secret '{secret_name}' not found in formation secrets")
        resolved[secret_name] = value
    return resolved


# ---------------------------------------------------------------------------
# Content transformation
# ---------------------------------------------------------------------------

_MD_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n?|```")
_MD_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_ITALIC = re.compile(r"\*([^*]+)\*|(?<![a-zA-Z0-9_])_([^_]+)_(?![a-zA-Z0-9_])")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def _markdown_to_text(content: str) -> str:
    """Strip common markdown syntax, leaving plain text (for SMS etc.)."""
    text = _MD_CODE_FENCE.sub("", content)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_BOLD.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_ITALIC.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_LINK.sub(r"\1 (\2)", text)
    text = _MD_HEADER.sub("", text)
    return text.strip()


def _markdown_to_html(content: str) -> str:
    """Minimal markdown-to-HTML conversion (inline styles + paragraphs)."""
    html = html_escape(content, quote=False)
    html = _MD_INLINE_CODE.sub(r"<code>\1</code>", html)
    html = _MD_BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", html)
    html = _MD_ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", html)

    def _link(m: "re.Match[str]") -> str:
        href = m.group(2)
        if href.lower().startswith(("http://", "https://")):
            return f'<a href="{href}">{m.group(1)}</a>'
        return m.group(1)

    html = _MD_LINK.sub(_link, html)
    paragraphs = [p.strip().replace("\n", "<br/>") for p in html.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def apply_content_transform(content: str, transform: Optional[ContentTransform]) -> str:
    """
    Apply the transformer's ``content_transform`` section to response content.

    ``format: text`` strips markdown, ``format: html`` renders minimal HTML,
    ``format: markdown`` (or no format) passes content through. Truncation
    (``max_length`` + ``truncation_suffix``) applies after formatting and
    the result never exceeds ``max_length`` characters.
    """
    if transform is None:
        return content

    result = content
    if transform.format == "text":
        result = _markdown_to_text(result)
    elif transform.format == "html":
        result = _markdown_to_html(result)

    if transform.max_length is not None and len(result) > transform.max_length:
        suffix = transform.truncation_suffix
        cut = max(transform.max_length - len(suffix), 0)
        result = result[:cut] + suffix[: transform.max_length - cut]

    return result


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def extract_response_files(response: Any) -> List[Dict[str, Any]]:
    """
    Extract file attachments from an agent response, when present.

    Supports unified-response dicts (content items of type ``file``) and
    objects exposing a ``files`` attribute. Returns an empty list otherwise.
    """
    if isinstance(response, dict):
        items = response.get("response") or response.get("content") or []
        if isinstance(items, list):
            return [
                item["file"]
                for item in items
                if isinstance(item, dict) and item.get("type") == "file" and item.get("file")
            ]
        return []
    files = getattr(response, "files", None)
    if isinstance(files, list):
        return files
    return []


def build_transformer_variables(
    *,
    response_content: str,
    response_files: Optional[List[Dict[str, Any]]] = None,
    response_metadata: Optional[Dict[str, Any]] = None,
    request_message: Optional[str] = None,
    request_user_id: Optional[str] = None,
    request_files: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None,
    agent_name: Optional[str] = None,
    secrets: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Assemble the template variable namespace for transformer rendering."""
    return {
        "response": {
            "content": response_content,
            "files": response_files or [],
            "metadata": response_metadata or {},
        },
        "request": {
            "message": request_message,
            "user_id": request_user_id,
            "files": request_files or [],
        },
        "context": context or {},
        "agent": {"name": agent_name},
        "secrets": secrets or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def deliver_via_transformer(
    *,
    webhook_manager: Any,
    secrets_manager: Any,
    transformer: TransformerConfig,
    response_content: str,
    response: Any = None,
    response_metadata: Optional[Dict[str, Any]] = None,
    request_message: Optional[str] = None,
    request_user_id: Optional[str] = None,
    request_files: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None,
    agent_name: Optional[str] = None,
    request_id: str,
    formation_id: Optional[str] = None,
    fallback_webhook_url: Optional[str] = None,
    url_override: Optional[str] = None,
) -> bool:
    """
    Format an agent response with a transformer and deliver it.

    ``url_override`` is the trigger/channel-supplied destination URL; it
    takes precedence over the transformer's own ``endpoint.url`` (the
    transformer+webhook composition mechanism).

    On rendering or delivery failure, the standard MUXI payload is delivered
    to ``fallback_webhook_url`` (the formation's default async webhook) with
    ``transformer_error`` metadata, per the PRD error-handling contract.

    Returns:
        True if the transformer endpoint accepted the delivery
    """
    endpoint_url = url_override or transformer.url
    attempts = 0
    last_error: Optional[str] = None
    try:
        secrets = await resolve_secrets(
            collect_secret_names(transformer, url_override), secrets_manager
        )
        content = apply_content_transform(response_content, transformer.content_transform)
        variables = build_transformer_variables(
            response_content=content,
            response_files=extract_response_files(response),
            response_metadata=response_metadata,
            request_message=request_message,
            request_user_id=request_user_id,
            request_files=request_files,
            context=context,
            agent_name=agent_name,
            secrets=secrets,
        )

        # Trigger/channel-supplied URL first, transformer endpoint.url second
        effective_url = resolve_transformer_url(transformer, url_override)
        rendered_url = render_template_string(effective_url, variables)
        if not isinstance(rendered_url, str) or not rendered_url.strip():
            raise ValueError("delivery URL rendered to an empty value")
        endpoint_url = rendered_url

        headers = {
            key: str(render_template_value(value, variables) or "")
            for key, value in transformer.headers.items()
        }
        body = render_template_value(transformer.body, variables)

        basic_auth: Optional[Tuple[str, str]] = None
        if transformer.auth:
            auth = transformer.auth
            # Auth fields are guaranteed non-empty for their type by
            # TransformerAuth.from_dict; the `or ""` keeps mypy satisfied.
            if auth.type == "bearer":
                token = render_template_string(auth.token or "", variables)
                headers["Authorization"] = f"Bearer {token}"
            elif auth.type == "basic":
                basic_auth = (
                    str(render_template_string(auth.username or "", variables) or ""),
                    str(render_template_string(auth.password or "", variables) or ""),
                )
            elif auth.type == "header" and auth.header_name:
                headers[auth.header_name] = str(
                    render_template_string(auth.header_value or "", variables) or ""
                )

        success, last_error, attempts = await webhook_manager.deliver_raw(
            url=endpoint_url,
            method=transformer.method,
            headers=headers,
            body=body,
            basic_auth=basic_auth,
            request_id=request_id,
            delivery_type="transformer",
            delivery_name=transformer.name,
        )
        if success:
            return True

    except ValueError as e:
        last_error = str(e)
        observability.observe(
            event_type=observability.ConversationEvents.WEBHOOK_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "request_id": request_id,
                "type": "transformer",
                "transformer": transformer.name,
                "error": last_error,
            },
            description=f"Transformer '{transformer.name}' rendering failed: {last_error}",
        )

    # Fallback: deliver standard payload to the default async webhook with
    # transformer error metadata so the failure is not silent.
    if fallback_webhook_url:
        fallback_payload = {
            "request_id": request_id,
            "formation_id": formation_id,
            "user_id": request_user_id,
            "status": "completed",
            "response": [{"type": "text", "text": response_content}],
            "transformer_error": {
                "transformer": transformer.name,
                "endpoint": endpoint_url,
                "attempts": attempts,
                "last_error": last_error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        await webhook_manager.deliver_raw(
            url=fallback_webhook_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=fallback_payload,
            request_id=request_id,
            delivery_type="transformer_fallback",
            delivery_name=transformer.name,
        )

    return False
