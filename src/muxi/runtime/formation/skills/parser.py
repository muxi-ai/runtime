import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Matches ${{ secrets.SECRET_NAME }} with flexible whitespace
_SECRETS_REF_PATTERN = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", re.IGNORECASE)


@dataclass
class SkillMetadata:
    """Tier 1: loaded at startup (~100 tokens per skill)."""

    name: str
    description: str
    path: Path
    base_dir: Path
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    required_secrets: List[str] = field(default_factory=list)


@dataclass
class SkillContent:
    """Tier 2: loaded on activation."""

    metadata: SkillMetadata
    body: str
    resources: List[str] = field(default_factory=list)


# SKILL.md name validation pattern (per spec)
_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def parse_skill_md(path: Path) -> tuple[SkillMetadata, str, list]:
    """
    Parse a SKILL.md file into metadata + body.

    Follows the Agent Skills specification for frontmatter parsing with
    lenient validation for cross-client compatibility.

    Args:
        path: Absolute path to SKILL.md

    Returns:
        Tuple of (SkillMetadata, body_text, warnings)

    Raises:
        ValueError: If frontmatter is missing/unparseable or description is empty
    """
    raw = path.read_text(encoding="utf-8")

    # Extract frontmatter between --- delimiters
    if not raw.startswith("---"):
        raise ValueError(f"SKILL.md missing frontmatter: {path}")

    end = raw.find("---", 3)
    if end == -1:
        raise ValueError(f"SKILL.md missing closing frontmatter delimiter: {path}")

    frontmatter_text = raw[3:end].strip()
    body = raw[end + 3 :].strip()

    # Parse YAML with lenient fallback for unquoted colons
    try:
        fm = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        # Retry with values wrapped in quotes (common cross-client issue)
        try:
            fixed = _fix_unquoted_colons(frontmatter_text)
            fm = yaml.safe_load(fixed)
        except yaml.YAMLError as e:
            raise ValueError(f"Unparseable SKILL.md frontmatter: {path}: {e}")

    if not isinstance(fm, dict):
        raise ValueError(f"SKILL.md frontmatter is not a mapping: {path}")

    # Description is required (per spec: essential for disclosure)
    description = fm.get("description", "")
    if not description or not str(description).strip():
        raise ValueError(f"SKILL.md missing required 'description' field: {path}")
    description = str(description).strip()

    # Name: use frontmatter value or fall back to parent directory name
    name = fm.get("name", "")
    dir_name = path.parent.name
    if not name:
        name = dir_name

    # Lenient validation: warn but don't fail on name issues
    warnings = []
    if name != dir_name:
        warnings.append(f"Skill name '{name}' does not match directory '{dir_name}'")
    if len(name) > 64:
        warnings.append(f"Skill name '{name}' exceeds 64 characters")
    if not _NAME_PATTERN.match(name):
        warnings.append(
            f"Skill name '{name}' does not match spec pattern (lowercase, hyphens only)"
        )

    # Parse allowed-tools (space-delimited string -> list)
    allowed_tools_raw = fm.get("allowed-tools", "")
    allowed_tools = allowed_tools_raw.split() if isinstance(allowed_tools_raw, str) else []

    required_secrets = scan_secret_refs(path.parent)

    metadata = SkillMetadata(
        name=name,
        description=description,
        path=path,
        base_dir=path.parent,
        license=fm.get("license"),
        compatibility=fm.get("compatibility"),
        metadata=fm.get("metadata", {}),
        allowed_tools=allowed_tools,
        required_secrets=required_secrets,
    )

    return metadata, body, warnings


def load_skill_content(metadata: SkillMetadata) -> SkillContent:
    """Load full skill content (Tier 2) from a previously parsed metadata entry."""
    raw = metadata.path.read_text(encoding="utf-8")
    end = raw.find("---", 3)
    body = raw[end + 3 :].strip() if end != -1 else raw

    resources = _enumerate_resources(metadata.base_dir)

    return SkillContent(metadata=metadata, body=body, resources=resources)


def scan_secret_refs(base_dir: Path) -> List[str]:
    """Scan a skill directory for ${{ secrets.X }} references.

    Scans SKILL.md plus all files under scripts/, references/, and assets/.
    Returns a deduplicated, sorted list of secret names (uppercased).
    """
    found: set[str] = set()

    def _scan_file(path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in _SECRETS_REF_PATTERN.finditer(text):
                found.add(match.group(1).upper())
        except OSError:
            pass

    skill_md = base_dir / "SKILL.md"
    if skill_md.is_file():
        _scan_file(skill_md)

    for subdir in ("scripts", "references", "assets"):
        d = base_dir / subdir
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    _scan_file(f)

    return sorted(found)


def _enumerate_resources(base_dir: Path) -> List[str]:
    """List files in scripts/, references/, assets/ directories."""
    resources = []
    for subdir in ("scripts", "references", "assets"):
        d = base_dir / subdir
        if d.is_dir():
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    resources.append(str(f.relative_to(base_dir)))
    return resources


def _fix_unquoted_colons(text: str) -> str:
    """Attempt to fix YAML with unquoted colons in values."""
    lines = []
    for line in text.split("\n"):
        if ":" in line and not line.strip().startswith("#"):
            key_end = line.index(":")
            rest = line[key_end + 1 :]
            # If the value part contains another colon, wrap in quotes
            if ":" in rest and not rest.strip().startswith('"'):
                value = rest.strip()
                indent = line[: key_end + 1]
                lines.append(f'{indent} "{value}"')
                continue
        lines.append(line)
    return "\n".join(lines)
