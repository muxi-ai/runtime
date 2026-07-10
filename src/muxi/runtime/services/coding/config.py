"""
Coding-agent delegation configuration (the top-level ``coding:`` block).

Parses and fail-fast-validates the formation surface for delegating coding
tasks to external headless CLIs (claude-code, droid, ...). The block is
optional: formations without it get no parsing, no service, and no
``delegate_coding`` tool (inert when unconfigured, pinned by unit test).

Two validation layers, mirroring the rbac/middleware convention:

- ``parse_coding_config`` -- structural (schema, enums, adapter shape,
  secrets-placement rule). Reused by the FormationValidator so the
  validator and the runtime can never disagree.
- ``validate_coding_runtime`` -- environment-dependent (binary on PATH,
  workdir roots exist, groups exist when RBAC is active). Called from
  ``Formation._setup_coding`` at load, never at delegation time.

Secrets rule (PRD D11): ``${{ secrets.* }}`` resolves in ``env:`` ONLY.
A secrets reference anywhere else in the block -- ``extra_args``
especially -- is a load error pointing at ``env:`` (argv is visible to
every user on the host via ``ps``; environment variables are not).
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

# Bundled adapter templates ship as dormant content next to the channel
# transformer templates (same convention: inert until referenced by name,
# formation-local file shadows the bundled one, inline form as escape hatch).
BUILTIN_ADAPTERS_DIR = (
    Path(__file__).parent.parent.parent / "formation" / "background" / "builtin" / "coding"
)

# Formation-local adapter files live in <formation_dir>/coding/<name>.yaml
FORMATION_ADAPTER_SUBDIR = "coding"

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_SECRETS_PATTERN = re.compile(r"\$\{\{\s*secrets\.\w+\s*\}\}")
_DURATION_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$")
_DURATION_FACTORS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, None: 1.0}

_ALLOWED_CODING_KEYS = {
    "client",
    "command",
    "args",
    "output",
    "parse",
    "model",
    "workdirs",
    "cleanup",
    "groups",
    "extra_args",
    "env",
    "timeout",
    "max_concurrent",
}
_INLINE_ADAPTER_KEYS = {"command", "args", "output", "parse"}
_ALLOWED_ADAPTER_KEYS = {"name", "command", "args", "output", "parse", "forbidden_extra_args"}
_ALLOWED_ARGS_KEYS = {"base", "prompt", "session", "session_new", "session_resume", "model"}
_ALLOWED_PARSE_KEYS = {"result", "session_id"}

OUTPUT_MODES = ("stream-json", "json", "text")
CLEANUP_MODES = ("delete", "keep")

DEFAULT_TIMEOUT_SECONDS = 30 * 60  # 30m
DEFAULT_MAX_CONCURRENT = 3


class CodingConfigError(ValueError):
    """Raised for any invalid ``coding:`` configuration (fail fast at load)."""


def parse_duration(value: Union[str, int, float], *, key: str) -> float:
    """Parse a duration string (``500ms``/``30s``/``30m``/``2h``) to seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
    elif isinstance(value, str):
        match = _DURATION_PATTERN.match(value)
        if not match:
            raise CodingConfigError(
                f"coding.{key} must be a duration like '30m', '90s' or '2h', got: {value!r}"
            )
        seconds = float(match.group(1)) * _DURATION_FACTORS[match.group(2)]
    else:
        raise CodingConfigError(f"coding.{key} must be a duration string, got: {value!r}")
    if seconds <= 0:
        raise CodingConfigError(f"coding.{key} must be positive, got: {value!r}")
    return seconds


def _require_str_list(value: Any, *, key: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodingConfigError(f"{key} must be a list of strings, got: {value!r}")
    return list(value)


def _find_secret_refs(value: Any, path: str, hits: List[str]) -> None:
    """Collect dotted paths of ``${{ secrets.* }}`` references in a subtree."""
    if isinstance(value, str):
        if _SECRETS_PATTERN.search(value):
            hits.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            _find_secret_refs(item, f"{path}.{key}" if path else str(key), hits)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _find_secret_refs(item, f"{path}[{index}]", hits)


@dataclass(frozen=True)
class AdapterConfig:
    """A resolved coding-CLI adapter (bundled template, local file, or inline)."""

    command: str
    prompt: Union[List[str], str]  # arg fragment containing {prompt}, or "stdin"
    base: List[str] = field(default_factory=list)
    session: Optional[List[str]] = None  # one idempotent create-or-resume flag
    session_new: Optional[List[str]] = None  # distinct create fragment
    session_resume: Optional[List[str]] = None  # distinct resume fragment
    model: Optional[List[str]] = None  # appended only when a model value is set
    output: str = "text"
    parse_result: Optional[str] = None
    parse_session_id: Optional[str] = None
    forbidden_extra_args: List[str] = field(default_factory=list)
    name: Optional[str] = None  # template name; None for inline adapters

    @property
    def generates_session_id(self) -> bool:
        """MUXI supplies the session id (idempotent flag or create/resume pair)."""
        return self.session is not None or self.session_new is not None

    @property
    def captures_session_id(self) -> bool:
        """The tool assigns the id; MUXI captures it from parsed output."""
        return self.session is None and self.session_new is None and self.session_resume is not None

    @property
    def supports_resume(self) -> bool:
        return self.session is not None or self.session_resume is not None


@dataclass
class CodingConfig:
    """Parsed top-level ``coding:`` block."""

    adapter: AdapterConfig
    client: Optional[str]  # bundled/local template name; None for inline adapters
    workdirs: List[str]
    model: Optional[str] = None
    cleanup: str = "delete"
    groups: List[str] = field(default_factory=list)
    extra_args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    # Set by validate_coding_runtime (absolute, symlink-resolved roots in
    # declaration order; parallel to ``workdirs``).
    resolved_workdirs: List[str] = field(default_factory=list)


def _parse_fragment(
    value: Any, *, key: str, placeholder: str, required_placeholder: bool = True
) -> List[str]:
    fragment = _require_str_list(value, key=key)
    if not fragment:
        raise CodingConfigError(f"{key} must not be empty")
    if required_placeholder and not any(placeholder in part for part in fragment):
        raise CodingConfigError(f"{key} must contain the {placeholder} placeholder")
    return fragment


def _parse_adapter(raw: Dict[str, Any], *, source: str) -> AdapterConfig:
    """Parse and validate an adapter definition (template file or inline form)."""
    if not isinstance(raw, dict):
        raise CodingConfigError(f"{source}: adapter definition must be a mapping")

    unknown = sorted(set(raw) - _ALLOWED_ADAPTER_KEYS)
    if unknown:
        raise CodingConfigError(
            f"{source}: unknown adapter key(s) {unknown}; "
            f"supported keys are {sorted(_ALLOWED_ADAPTER_KEYS)}"
        )

    secret_hits: List[str] = []
    _find_secret_refs(raw, "", secret_hits)
    if secret_hits:
        raise CodingConfigError(
            f"{source}: ${{{{ secrets.* }}}} is not allowed in adapter definitions "
            f"(found at {secret_hits}); credentials belong in coding.env -- the only "
            "place secrets resolve (argv is ps-visible, the environment is not)"
        )

    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        raise CodingConfigError(f"{source}: adapter 'command' must be a non-empty string")

    args = raw.get("args")
    if not isinstance(args, dict):
        raise CodingConfigError(f"{source}: adapter 'args' must be a mapping")
    unknown_args = sorted(set(args) - _ALLOWED_ARGS_KEYS)
    if unknown_args:
        raise CodingConfigError(
            f"{source}: unknown args key(s) {unknown_args}; "
            f"supported keys are {sorted(_ALLOWED_ARGS_KEYS)}"
        )

    prompt_raw = args.get("prompt")
    prompt: Union[List[str], str]
    if prompt_raw == "stdin":
        prompt = "stdin"
    elif prompt_raw is None:
        raise CodingConfigError(
            f"{source}: args.prompt is required (a fragment containing "
            "{prompt}, or the literal string 'stdin')"
        )
    else:
        prompt = _parse_fragment(prompt_raw, key=f"{source}: args.prompt", placeholder="{prompt}")

    base = _require_str_list(args.get("base", []), key=f"{source}: args.base")

    session = args.get("session")
    session_new = args.get("session_new")
    session_resume = args.get("session_resume")
    if session is not None and (session_new is not None or session_resume is not None):
        raise CodingConfigError(
            f"{source}: define either a single idempotent 'session' fragment OR the "
            "'session_new'/'session_resume' pair, not both"
        )
    if session_new is not None and session_resume is None:
        raise CodingConfigError(
            f"{source}: args.session_new requires args.session_resume "
            "(a session that can be created but never resumed is dead config)"
        )
    if session is not None:
        session = _parse_fragment(session, key=f"{source}: args.session", placeholder="{id}")
    if session_new is not None:
        session_new = _parse_fragment(
            session_new, key=f"{source}: args.session_new", placeholder="{id}"
        )
    if session_resume is not None:
        session_resume = _parse_fragment(
            session_resume, key=f"{source}: args.session_resume", placeholder="{id}"
        )

    model = args.get("model")
    if model is not None:
        model = _parse_fragment(model, key=f"{source}: args.model", placeholder="{model}")

    output = raw.get("output", "text")
    if output not in OUTPUT_MODES:
        raise CodingConfigError(
            f"{source}: output must be one of {list(OUTPUT_MODES)}, got: {output!r}"
        )

    parse_spec = raw.get("parse") or {}
    if not isinstance(parse_spec, dict):
        raise CodingConfigError(f"{source}: 'parse' must be a mapping")
    unknown_parse = sorted(set(parse_spec) - _ALLOWED_PARSE_KEYS)
    if unknown_parse:
        raise CodingConfigError(
            f"{source}: unknown parse key(s) {unknown_parse}; "
            f"supported keys are {sorted(_ALLOWED_PARSE_KEYS)}"
        )
    for key, selector in parse_spec.items():
        if not isinstance(selector, str) or not selector.strip():
            raise CodingConfigError(f"{source}: parse.{key} must be a non-empty selector string")
    if parse_spec and output == "text":
        raise CodingConfigError(
            f"{source}: parse selectors have no effect with output: text "
            "(text mode treats the full stdout as the result)"
        )

    forbidden_extra_args = _require_str_list(
        raw.get("forbidden_extra_args", []), key=f"{source}: forbidden_extra_args"
    )

    adapter = AdapterConfig(
        command=command.strip(),
        prompt=prompt,
        base=base,
        session=session,
        session_new=session_new,
        session_resume=session_resume,
        model=model,
        output=output,
        parse_result=parse_spec.get("result"),
        parse_session_id=parse_spec.get("session_id"),
        forbidden_extra_args=forbidden_extra_args,
        name=raw.get("name"),
    )

    if adapter.captures_session_id:
        if adapter.output == "text":
            raise CodingConfigError(
                f"{source}: a tool-assigned-session adapter (session_resume only) "
                "cannot use output: text -- the session id must be captured from "
                "parsed output"
            )
        if not adapter.parse_session_id:
            raise CodingConfigError(
                f"{source}: a tool-assigned-session adapter (session_resume only) "
                "requires parse.session_id to capture the id from output"
            )

    return adapter


def list_bundled_adapters() -> List[str]:
    """Names of the bundled dormant adapter templates."""
    if not BUILTIN_ADAPTERS_DIR.is_dir():
        return []
    return sorted(
        path.stem
        for path in BUILTIN_ADAPTERS_DIR.iterdir()
        if path.suffix in (".yaml", ".yml") and path.is_file()
    )


def resolve_adapter_template(name: str, formation_dir: Optional[str]) -> AdapterConfig:
    """
    Resolve a named adapter template.

    Formation-local ``coding/<name>.yaml`` shadows the bundled template of
    the same name -- the same shadowing rule as built-in skills and channel
    transformers.
    """
    if not isinstance(name, str) or not _NAME_PATTERN.match(name):
        raise CodingConfigError(
            f"coding.client must be a template name matching [a-zA-Z0-9_-]+, got: {name!r}"
        )

    candidates: List[Path] = []
    if formation_dir:
        local_dir = Path(formation_dir) / FORMATION_ADAPTER_SUBDIR
        candidates.extend(local_dir / f"{name}{suffix}" for suffix in (".yaml", ".yml"))
    candidates.extend(BUILTIN_ADAPTERS_DIR / f"{name}{suffix}" for suffix in (".yaml", ".yml"))

    for candidate in candidates:
        if candidate.is_file():
            try:
                raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                raise CodingConfigError(f"adapter template {candidate} is not valid YAML: {e}")
            adapter = _parse_adapter(raw, source=str(candidate))
            if adapter.name != name:
                raise CodingConfigError(
                    f"adapter template {candidate} declares name {adapter.name!r} "
                    f"but the filename requires {name!r}"
                )
            return adapter

    bundled = list_bundled_adapters()
    raise CodingConfigError(
        f"coding.client {name!r} names no bundled or formation-local adapter "
        f"(bundled templates: {bundled}; formation-local files live in "
        f"{FORMATION_ADAPTER_SUBDIR}/<name>.yaml), and no inline adapter is defined"
    )


def parse_coding_config(
    raw: Any,
    formation_dir: Optional[str] = None,
    *,
    resolve_client: bool = True,
) -> Optional[CodingConfig]:
    """
    Parse the top-level ``coding:`` block.

    Returns None when the block is absent (the whole feature stays inert).
    Raises CodingConfigError on any structural problem -- a formation-load
    error, never a delegation-time surprise.

    ``resolve_client=False`` skips named-template resolution (used by the
    structural validator, which may not know the formation directory);
    ``Formation._setup_coding`` always resolves.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CodingConfigError("'coding' must be a mapping")

    unknown = sorted(set(raw) - _ALLOWED_CODING_KEYS)
    if unknown:
        raise CodingConfigError(
            f"'coding' has unknown key(s) {unknown}; "
            f"supported keys are {sorted(_ALLOWED_CODING_KEYS)}"
        )

    # Secrets-placement rule (D11): references may appear under env: ONLY.
    secret_hits: List[str] = []
    for key, value in raw.items():
        if key == "env":
            continue
        _find_secret_refs(value, key, secret_hits)
    if secret_hits:
        raise CodingConfigError(
            f"${{{{ secrets.* }}}} references are only resolved under coding.env "
            f"(found at {secret_hits}); move the value into coding.env -- argv is "
            "visible to every user on the host via ps, environment variables are not"
        )

    client = raw.get("client")
    inline_keys = sorted(_INLINE_ADAPTER_KEYS & set(raw))
    if client is not None and inline_keys:
        raise CodingConfigError(
            f"coding.client and the inline adapter form are mutually exclusive "
            f"(client {client!r} given alongside inline key(s) {inline_keys})"
        )
    if client is None and not inline_keys:
        raise CodingConfigError(
            "coding requires either 'client' (a bundled or formation-local adapter "
            "template name) or an inline adapter ('command' + 'args')"
        )

    if client is not None:
        if resolve_client:
            adapter = resolve_adapter_template(client, formation_dir)
        else:
            # Structural-only pass: the name pattern is still checked.
            if not isinstance(client, str) or not _NAME_PATTERN.match(client):
                raise CodingConfigError(
                    f"coding.client must be a template name matching "
                    f"[a-zA-Z0-9_-]+, got: {client!r}"
                )
            adapter = None
    else:
        adapter = _parse_adapter(
            {key: raw[key] for key in _INLINE_ADAPTER_KEYS if key in raw},
            source="coding (inline adapter)",
        )

    workdirs = raw.get("workdirs")
    if workdirs is None:
        raise CodingConfigError(
            "coding.workdirs is required: declare at least one root directory "
            "(each delegation runs in a fresh <root>/<user_id>/<request_id> dir)"
        )
    workdirs = _require_str_list(workdirs, key="coding.workdirs")
    if not workdirs or not all(entry.strip() for entry in workdirs):
        raise CodingConfigError("coding.workdirs must contain at least one non-empty path")

    model = raw.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise CodingConfigError(f"coding.model must be a non-empty string, got: {model!r}")

    cleanup = raw.get("cleanup", "delete")
    if cleanup not in CLEANUP_MODES:
        raise CodingConfigError(
            f"coding.cleanup must be one of {list(CLEANUP_MODES)}, got: {cleanup!r}"
        )

    groups = _require_str_list(raw.get("groups", []) or [], key="coding.groups")
    if not all(isinstance(g, str) and g.strip() for g in groups):
        raise CodingConfigError("coding.groups entries must be non-empty group names")

    extra_args = _require_str_list(raw.get("extra_args", []) or [], key="coding.extra_args")

    env = raw.get("env", {}) or {}
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        raise CodingConfigError("coding.env must be a mapping of string names to string values")

    timeout_seconds = float(DEFAULT_TIMEOUT_SECONDS)
    if "timeout" in raw:
        timeout_seconds = parse_duration(raw["timeout"], key="timeout")

    max_concurrent = raw.get("max_concurrent", DEFAULT_MAX_CONCURRENT)
    if not isinstance(max_concurrent, int) or isinstance(max_concurrent, bool):
        raise CodingConfigError(
            f"coding.max_concurrent must be an integer >= 1, got: {max_concurrent!r}"
        )
    if max_concurrent < 1:
        raise CodingConfigError(
            f"coding.max_concurrent must be an integer >= 1, got: {max_concurrent!r}"
        )

    if adapter is not None:
        _check_adapter_constraints(adapter, model=model, extra_args=extra_args)

    return CodingConfig(
        adapter=adapter,
        client=client,
        workdirs=workdirs,
        model=model.strip() if isinstance(model, str) else None,
        cleanup=cleanup,
        groups=[g.strip() for g in groups],
        extra_args=extra_args,
        env=dict(env),
        timeout_seconds=timeout_seconds,
        max_concurrent=max_concurrent,
    )


def _check_adapter_constraints(
    adapter: AdapterConfig, *, model: Optional[str], extra_args: List[str]
) -> None:
    """Cross-checks between the block and its resolved adapter."""
    if model and adapter.model is None:
        raise CodingConfigError(
            "coding.model is set but the adapter defines no args.model fragment "
            "to pass it through"
        )
    if adapter.forbidden_extra_args:
        offending = sorted({arg for arg in extra_args if arg in set(adapter.forbidden_extra_args)})
        if offending:
            raise CodingConfigError(
                f"coding.extra_args must not include {offending}: MUXI sets the "
                "subprocess working directory (each delegation runs in a fresh "
                "directory under a declared workdirs root)"
            )


def validate_coding_runtime(
    config: CodingConfig,
    *,
    formation_dir: Optional[str],
    known_groups: Optional[set] = None,
) -> None:
    """
    Environment-dependent fail-fast checks, run at formation load.

    - the adapter binary is on PATH (or an absolute path that exists);
      installation and authentication stay the developer's business
    - every workdirs root exists and is a directory (symlink-resolved);
      resolved roots are stored on ``config.resolved_workdirs``
    - when RBAC is active (``known_groups`` is not None), every
      ``coding.groups`` entry names an existing group
    """
    command = config.adapter.command
    if os.path.isabs(command):
        if not (os.path.isfile(command) and os.access(command, os.X_OK)):
            raise CodingConfigError(
                f"coding adapter binary not found or not executable: {command} "
                "(MUXI only verifies presence; installing and authenticating the "
                "tool is the developer's responsibility)"
            )
    elif shutil.which(command) is None:
        raise CodingConfigError(
            f"coding adapter binary {command!r} not found on PATH "
            "(MUXI only verifies presence; installing and authenticating the "
            "tool is the developer's responsibility)"
        )

    resolved: List[str] = []
    for entry in config.workdirs:
        root = entry
        if not os.path.isabs(root):
            if not formation_dir:
                raise CodingConfigError(
                    f"coding.workdirs entry {entry!r} is relative but the formation "
                    "directory is not available to resolve it"
                )
            root = os.path.normpath(os.path.join(formation_dir, root))
        root = os.path.realpath(root)
        if not os.path.isdir(root):
            raise CodingConfigError(
                f"coding.workdirs root does not exist or is not a directory: "
                f"{entry!r} (resolved to {root})"
            )
        resolved.append(root)
    config.resolved_workdirs = resolved

    if known_groups is not None and config.groups:
        missing = sorted(set(config.groups) - set(known_groups))
        if missing:
            raise CodingConfigError(
                f"coding.groups names group(s) {missing} but no matching file "
                f"exists in groups/ (known groups: {sorted(known_groups)})"
            )


def find_workdir_root(config: CodingConfig, workdir: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Resolve the tool's ``workdir`` parameter to a declared root.

    Returns (resolved_root, declared_entry). ``workdir=None`` selects the
    first declared root. Raises CodingConfigError for anything outside the
    allowlist (surfaced as a friendly tool error, never an exception into
    the turn).
    """
    if not config.resolved_workdirs:
        raise CodingConfigError("no resolved workdir roots (formation load incomplete)")
    if workdir is None or not str(workdir).strip():
        return config.resolved_workdirs[0], config.workdirs[0]
    requested = str(workdir).strip()
    for declared, resolved_root in zip(config.workdirs, config.resolved_workdirs):
        if requested == declared or os.path.realpath(requested) == resolved_root:
            return resolved_root, declared
    raise CodingConfigError(
        f"workdir {requested!r} is not a declared coding.workdirs root "
        f"(declared roots: {config.workdirs})"
    )
