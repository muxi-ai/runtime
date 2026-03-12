"""Tests for Formation._run_init_hook() and Formation._check_missing_path_args()."""

import pytest

from muxi.runtime.formation.formation import Formation


class TestCheckMissingPathArgs:
    """Tests for the static _check_missing_path_args helper."""

    def test_no_args(self):
        assert Formation._check_missing_path_args({"id": "test"}) == []

    def test_empty_args(self):
        assert Formation._check_missing_path_args({"args": []}) == []

    def test_non_path_args(self):
        config = {"args": ["-y", "@modelcontextprotocol/server-filesystem", "some-flag"]}
        assert Formation._check_missing_path_args(config) == []

    def test_existing_path(self):
        config = {"args": ["-y", "/tmp"]}
        assert Formation._check_missing_path_args(config) == []

    def test_missing_absolute_path(self):
        config = {"args": ["-y", "/tmp/nonexistent_test_dir_xyz_12345"]}
        result = Formation._check_missing_path_args(config)
        assert result == ["/tmp/nonexistent_test_dir_xyz_12345"]

    def test_missing_relative_path(self):
        config = {"args": ["./nonexistent_dir_xyz_12345"]}
        result = Formation._check_missing_path_args(config)
        assert result == ["./nonexistent_dir_xyz_12345"]

    def test_multiple_missing(self):
        config = {"args": ["/tmp/missing_a_xyz", "/tmp", "/tmp/missing_b_xyz"]}
        result = Formation._check_missing_path_args(config)
        assert len(result) == 2
        assert "/tmp/missing_a_xyz" in result
        assert "/tmp/missing_b_xyz" in result

    def test_non_string_args_ignored(self):
        config = {"args": [123, True, None, "/tmp"]}
        assert Formation._check_missing_path_args(config) == []

    def test_missing_dotdot_path(self):
        config = {"args": ["../nonexistent_dir_xyz_12345"]}
        result = Formation._check_missing_path_args(config)
        assert result == ["../nonexistent_dir_xyz_12345"]

    def test_missing_tilde_path(self):
        config = {"args": ["~/nonexistent_dir_xyz_12345"]}
        result = Formation._check_missing_path_args(config)
        assert result == ["~/nonexistent_dir_xyz_12345"]

    def test_existing_home_dir(self):
        config = {"args": ["~"]}
        assert Formation._check_missing_path_args(config) == []


class TestRunInitHook:
    """Tests for _run_init_hook."""

    @pytest.fixture
    def formation(self, tmp_path):
        """Create a minimal Formation instance for testing."""
        config_file = tmp_path / "formation.yaml"
        config_file.write_text("schema: '1.0.0'\nid: test\n")

        f = Formation.__new__(Formation)
        f.config = {}
        f._formation_path = str(config_file)
        return f

    @pytest.mark.asyncio
    async def test_no_config(self, formation):
        formation.config = None
        await formation._run_init_hook()

    @pytest.mark.asyncio
    async def test_no_init_key(self, formation):
        formation.config = {"id": "test"}
        await formation._run_init_hook()

    @pytest.mark.asyncio
    async def test_successful_command(self, formation, tmp_path):
        target = tmp_path / "workspace"
        formation.config = {"init": f"mkdir -p {target}"}
        await formation._run_init_hook()
        assert target.is_dir()

    @pytest.mark.asyncio
    async def test_multiline_command(self, formation, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        formation.config = {"init": f"mkdir -p {dir1}\nmkdir -p {dir2}"}
        await formation._run_init_hook()
        assert dir1.is_dir()
        assert dir2.is_dir()

    @pytest.mark.asyncio
    async def test_failed_command_raises(self, formation):
        formation.config = {"init": "exit 1"}
        with pytest.raises(Exception, match="Init hook failed"):
            await formation._run_init_hook()

    @pytest.mark.asyncio
    async def test_invalid_type_raises(self, formation):
        formation.config = {"init": ["mkdir", "-p", "/tmp/x"]}
        with pytest.raises(Exception, match="must be a string"):
            await formation._run_init_hook()

    @pytest.mark.asyncio
    async def test_cwd_is_formation_directory(self, formation, tmp_path):
        marker = tmp_path / "marker.txt"
        formation.config = {"init": f"pwd > {marker}"}
        await formation._run_init_hook()
        cwd_output = marker.read_text().strip()
        assert cwd_output == str(tmp_path)

    @pytest.mark.asyncio
    async def test_stderr_included_in_error(self, formation):
        formation.config = {"init": "echo 'bad thing happened' >&2; exit 1"}
        with pytest.raises(Exception, match="bad thing happened"):
            await formation._run_init_hook()
