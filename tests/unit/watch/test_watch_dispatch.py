"""
Unit tests for the watch_job dispatch surface + SOP fragment resolution.

Pins the inert-when-unconfigured contract (no MCP servers = no tool, no
fragment -- byte-identical behavior) and the fragment's shadowing rule
(formation-local sops/watch_job.md wins; empty file removes it).
"""

from types import SimpleNamespace

import pytest

from muxi.runtime.formation.agents.watch_dispatch import (
    _reset_default_sop_cache,
    build_watch_tools,
    handle_watch_job,
    load_default_watch_sop,
    watch_sop_fragment,
    watch_tools_available,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _reset_default_sop_cache()
    yield
    _reset_default_sop_cache()


class TestAvailability:
    def test_no_service_means_no_tool(self):
        overlord = SimpleNamespace(watch_service=None)
        assert watch_tools_available(overlord) is False

    def test_service_means_tool(self):
        overlord = SimpleNamespace(watch_service=object())
        assert watch_tools_available(overlord) is True

    async def test_handle_without_service_is_friendly(self):
        overlord = SimpleNamespace(watch_service=None)
        result = await handle_watch_job("agent", {}, overlord, user_id="u1")
        assert result["success"] is False
        assert "not available" in result["error"]

    def test_tool_definition_shape(self):
        tools = build_watch_tools()
        assert len(tools) == 1
        function = tools[0]["function"]
        assert function["name"] == "watch_job"
        assert set(function["parameters"]["required"]) == {"tool", "done_when"}


class TestSopFragment:
    def test_bundled_fragment_ships(self):
        content = load_default_watch_sop()
        assert "watch_job" in content
        assert "done_when" in content

    def test_no_watch_config_means_no_fragment(self):
        overlord = SimpleNamespace(_configured_services={"watch_config": None})
        assert watch_sop_fragment(overlord) is None
        assert watch_sop_fragment(SimpleNamespace()) is None

    def test_fragment_present_when_configured(self, tmp_path):
        overlord = SimpleNamespace(
            _configured_services={
                "watch_config": object(),
                "formation_path": str(tmp_path),
            }
        )
        assert watch_sop_fragment(overlord) == load_default_watch_sop()

    def test_formation_local_file_shadows(self, tmp_path):
        sops = tmp_path / "sops"
        sops.mkdir()
        (sops / "watch_job.md").write_text("Custom watch guidance.")
        overlord = SimpleNamespace(
            _configured_services={
                "watch_config": object(),
                "formation_path": str(tmp_path),
            }
        )
        assert watch_sop_fragment(overlord) == "Custom watch guidance."

    def test_empty_local_file_removes_fragment(self, tmp_path):
        sops = tmp_path / "sops"
        sops.mkdir()
        (sops / "watch_job.md").write_text("   \n")
        overlord = SimpleNamespace(
            _configured_services={
                "watch_config": object(),
                "formation_path": str(tmp_path),
            }
        )
        assert watch_sop_fragment(overlord) is None
