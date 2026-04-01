"""Unit tests for skill secret scanning, interpolation, and env injection."""
import re
import pytest

from muxi.runtime.formation.skills.parser import scan_secret_refs, parse_skill_md
from muxi.runtime.formation.skills.skill_manager import SkillManager


# ---------------------------------------------------------------------------
# Minimal async secrets manager stub (no real encryption needed for unit tests)
# ---------------------------------------------------------------------------


class FakeSecretsManager:
    """Minimal stub that resolves secrets from an in-memory dict."""

    _PATTERN = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", re.IGNORECASE)

    def __init__(self, secrets: dict):
        self._secrets = {k.upper(): v for k, v in secrets.items()}

    async def get_secret(self, name: str):
        return self._secrets.get(name.upper())

    async def interpolate_secrets(self, value):
        if isinstance(value, str):
            def _replace(m):
                key = m.group(1).upper()
                val = self._secrets.get(key)
                if val is None:
                    raise ValueError(f"Secret '{key}' not found")
                return val

            return self._PATTERN.sub(_replace, value)
        return value


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def skill_with_secrets(tmp_path):
    """Skill that references secrets in SKILL.md and a bundled script."""
    skill_dir = tmp_path / "notion-sync"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: notion-sync\n"
        'description: "Sync data with Notion"\n'
        "---\n\n"
        "# Notion Sync\n\n"
        "Use the Notion API key: ${{ secrets.NOTION_KEY }} to authenticate.\n"
        "Also needs ${{ secrets.SLACK_TOKEN }} for notifications.\n"
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "sync.py").write_text(
        "import os\n"
        "notion_key = os.environ['NOTION_KEY']\n"
        "slack_token = os.environ['SLACK_TOKEN']\n"
        "# also ${{ secrets.NOTION_KEY }} in a comment\n"
    )
    return skill_dir


@pytest.fixture
def skill_no_secrets(tmp_path):
    """Skill with no secret references."""
    skill_dir = tmp_path / "simple-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: simple-skill\n"
        "description: A skill with no secrets\n"
        "---\n\n"
        "# Simple\n\nDo stuff.\n"
    )
    return skill_dir


@pytest.fixture
def skill_with_assets_secrets(tmp_path):
    """Skill that references secrets in an assets/ file."""
    skill_dir = tmp_path / "asset-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: asset-skill\ndescription: Asset skill\n---\n\nBody.\n"
    )
    assets_dir = skill_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "config.json").write_text(
        '{"api_key": "${{ secrets.ASSET_API_KEY }}"}\n'
    )
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "notes.md").write_text(
        "Remember to set ${{ secrets.REF_TOKEN }} before running.\n"
    )
    return skill_dir


# ---------------------------------------------------------------------------
# scan_secret_refs tests
# ---------------------------------------------------------------------------


class TestScanSecretRefs:
    def test_scans_skill_md(self, skill_with_secrets):
        refs = scan_secret_refs(skill_with_secrets)
        assert "NOTION_KEY" in refs
        assert "SLACK_TOKEN" in refs

    def test_scans_scripts_dir(self, skill_with_secrets):
        # The script has ${{ secrets.NOTION_KEY }} in a comment too
        refs = scan_secret_refs(skill_with_secrets)
        assert "NOTION_KEY" in refs

    def test_deduplicates(self, skill_with_secrets):
        # NOTION_KEY appears in both SKILL.md and scripts/sync.py
        refs = scan_secret_refs(skill_with_secrets)
        assert refs.count("NOTION_KEY") == 1

    def test_sorted_output(self, skill_with_secrets):
        refs = scan_secret_refs(skill_with_secrets)
        assert refs == sorted(refs)

    def test_no_refs(self, skill_no_secrets):
        refs = scan_secret_refs(skill_no_secrets)
        assert refs == []

    def test_scans_assets_dir(self, skill_with_assets_secrets):
        refs = scan_secret_refs(skill_with_assets_secrets)
        assert "ASSET_API_KEY" in refs

    def test_scans_references_dir(self, skill_with_assets_secrets):
        refs = scan_secret_refs(skill_with_assets_secrets)
        assert "REF_TOKEN" in refs

    def test_uppercase_normalization(self, tmp_path):
        skill_dir = tmp_path / "case-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: case-skill\ndescription: Case test\n---\n\n"
            "Use ${{ secrets.my_lower_key }} and ${{ secrets.MY_UPPER_KEY }}.\n"
        )
        refs = scan_secret_refs(skill_dir)
        assert "MY_LOWER_KEY" in refs
        assert "MY_UPPER_KEY" in refs

    def test_whitespace_tolerant_pattern(self, tmp_path):
        skill_dir = tmp_path / "ws-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ws-skill\ndescription: Whitespace test\n---\n\n"
            "Key: ${{secrets.NO_SPACE}} and ${{ secrets.WITH_SPACE }}.\n"
        )
        refs = scan_secret_refs(skill_dir)
        assert "NO_SPACE" in refs
        assert "WITH_SPACE" in refs

    def test_missing_subdirs_ignored(self, skill_no_secrets):
        # Skill with no scripts/references/assets dirs should not error
        refs = scan_secret_refs(skill_no_secrets)
        assert refs == []

    def test_nested_scripts(self, tmp_path):
        skill_dir = tmp_path / "nested-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: nested-skill\ndescription: Nested\n---\n\nBody.\n"
        )
        scripts_dir = skill_dir / "scripts"
        sub_dir = scripts_dir / "sub"
        sub_dir.mkdir(parents=True)
        (sub_dir / "helper.py").write_text(
            "token = os.environ['${{ secrets.NESTED_TOKEN }}']\n"
        )
        refs = scan_secret_refs(skill_dir)
        assert "NESTED_TOKEN" in refs


# ---------------------------------------------------------------------------
# SkillMetadata.required_secrets populated by parse_skill_md
# ---------------------------------------------------------------------------


class TestRequiredSecretsOnMetadata:
    def test_required_secrets_populated(self, skill_with_secrets):
        metadata, _, _ = parse_skill_md(skill_with_secrets / "SKILL.md")
        assert "NOTION_KEY" in metadata.required_secrets
        assert "SLACK_TOKEN" in metadata.required_secrets

    def test_required_secrets_empty_when_none(self, skill_no_secrets):
        metadata, _, _ = parse_skill_md(skill_no_secrets / "SKILL.md")
        assert metadata.required_secrets == []


# ---------------------------------------------------------------------------
# SkillManager.activate_async
# ---------------------------------------------------------------------------


class TestActivateAsync:
    @pytest.mark.asyncio
    async def test_interpolates_secrets_in_body(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Copy skill into skills dir
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "secret-abc", "SLACK_TOKEN": "xoxb-123"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        content = await manager.activate_async("notion-sync", "session-1")
        assert "secret-abc" in content
        assert "xoxb-123" in content
        assert "${{ secrets.NOTION_KEY }}" not in content

    @pytest.mark.asyncio
    async def test_no_secrets_manager_leaves_placeholders(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        manager = SkillManager(skills_dir)  # no secrets manager
        manager.load_public_skills(["notion-sync"])

        content = await manager.activate_async("notion-sync", "session-1")
        # Placeholders should remain
        assert "${{ secrets.NOTION_KEY }}" in content

    @pytest.mark.asyncio
    async def test_deduplication_still_works(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "k", "SLACK_TOKEN": "s"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        await manager.activate_async("notion-sync", "session-1")
        result = await manager.activate_async("notion-sync", "session-1")
        assert "already active" in result

    @pytest.mark.asyncio
    async def test_nonexistent_skill(self, tmp_path):
        manager = SkillManager(tmp_path)
        result = await manager.activate_async("no-such-skill", "session-1")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_no_secrets_needed(self, skill_no_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_no_secrets, skills_dir / "simple-skill")

        secrets = FakeSecretsManager({})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["simple-skill"])

        content = await manager.activate_async("simple-skill", "s1")
        assert "simple-skill" in content
        assert "Do stuff" in content


# ---------------------------------------------------------------------------
# SkillManager.validate_secrets
# ---------------------------------------------------------------------------


class TestValidateSecrets:
    @pytest.mark.asyncio
    async def test_all_present(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "k", "SLACK_TOKEN": "s"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        missing = await manager.validate_secrets("notion-sync")
        assert missing == []

    @pytest.mark.asyncio
    async def test_some_missing(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "k"})  # SLACK_TOKEN missing
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        missing = await manager.validate_secrets("notion-sync")
        assert "SLACK_TOKEN" in missing
        assert "NOTION_KEY" not in missing

    @pytest.mark.asyncio
    async def test_no_secrets_manager_returns_empty(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        manager = SkillManager(skills_dir)
        manager.load_public_skills(["notion-sync"])

        missing = await manager.validate_secrets("notion-sync")
        assert missing == []

    @pytest.mark.asyncio
    async def test_no_secrets_needed(self, skill_no_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_no_secrets, skills_dir / "simple-skill")

        secrets = FakeSecretsManager({})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["simple-skill"])

        missing = await manager.validate_secrets("simple-skill")
        assert missing == []

    @pytest.mark.asyncio
    async def test_unknown_skill(self, tmp_path):
        manager = SkillManager(tmp_path)
        missing = await manager.validate_secrets("no-such-skill")
        assert missing == []


# ---------------------------------------------------------------------------
# SkillManager.resolve_skill_env
# ---------------------------------------------------------------------------


class TestResolveSkillEnv:
    @pytest.mark.asyncio
    async def test_all_resolved(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "abc", "SLACK_TOKEN": "xyz"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        env = await manager.resolve_skill_env("notion-sync")
        assert env == {"NOTION_KEY": "abc", "SLACK_TOKEN": "xyz"}

    @pytest.mark.asyncio
    async def test_missing_secret_omitted(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        secrets = FakeSecretsManager({"NOTION_KEY": "abc"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["notion-sync"])

        env = await manager.resolve_skill_env("notion-sync")
        assert "NOTION_KEY" in env
        assert "SLACK_TOKEN" not in env

    @pytest.mark.asyncio
    async def test_no_secrets_manager_returns_empty(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        manager = SkillManager(skills_dir)
        manager.load_public_skills(["notion-sync"])

        env = await manager.resolve_skill_env("notion-sync")
        assert env == {}

    @pytest.mark.asyncio
    async def test_no_secrets_needed_returns_empty(self, skill_no_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_no_secrets, skills_dir / "simple-skill")

        secrets = FakeSecretsManager({"UNRELATED": "val"})
        manager = SkillManager(skills_dir, secrets_manager=secrets)
        manager.load_public_skills(["simple-skill"])

        env = await manager.resolve_skill_env("simple-skill")
        assert env == {}

    @pytest.mark.asyncio
    async def test_unknown_skill_returns_empty(self, tmp_path):
        manager = SkillManager(tmp_path)
        env = await manager.resolve_skill_env("no-such-skill")
        assert env == {}


# ---------------------------------------------------------------------------
# set_secrets_manager
# ---------------------------------------------------------------------------


class TestSetSecretsManager:
    @pytest.mark.asyncio
    async def test_set_after_init(self, skill_with_secrets, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        import shutil
        shutil.copytree(skill_with_secrets, skills_dir / "notion-sync")

        manager = SkillManager(skills_dir)  # no secrets initially
        manager.load_public_skills(["notion-sync"])

        # Secrets not available yet
        env = await manager.resolve_skill_env("notion-sync")
        assert env == {}

        # Attach secrets manager later
        secrets = FakeSecretsManager({"NOTION_KEY": "late-key", "SLACK_TOKEN": "late-tok"})
        manager.set_secrets_manager(secrets)

        env = await manager.resolve_skill_env("notion-sync")
        assert env["NOTION_KEY"] == "late-key"
