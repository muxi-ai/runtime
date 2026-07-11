"""
Unit tests for the mcp.watch configuration surface (remote async tools).

Covers the parse matrix (default ON with declared servers, the
``watch: false`` escape hatch, closed key set, value validation, the
dead-config guard), the group-file ``mcp: {watch: {max_concurrent}}``
override (closed key sets, inheritance keeps the highest value), and the
resolver's highest-across-groups quota property.
"""

import pytest

from muxi.runtime.services.gbac.loader import GroupPermissionError, load_groups
from muxi.runtime.services.gbac.resolver import PermissionResolver
from muxi.runtime.services.watch import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    DEFAULT_TIMEOUT_SECONDS,
    WatchConfigError,
    parse_watch_config,
)

# ===================================================================
# parse_watch_config
# ===================================================================


class TestParseWatchConfig:
    def test_no_mcp_block_is_inert(self):
        assert parse_watch_config(None) is None

    def test_no_declared_servers_is_inert(self):
        assert parse_watch_config({}) is None
        assert parse_watch_config({"servers": []}) is None

    def test_default_on_with_servers(self):
        config = parse_watch_config({"servers": ["some-mcp"]})
        assert config is not None
        assert config.interval_seconds == DEFAULT_INTERVAL_SECONDS
        assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
        assert config.max_concurrent == DEFAULT_MAX_CONCURRENT
        assert config.max_consecutive_failures == DEFAULT_MAX_CONSECUTIVE_FAILURES

    def test_watch_false_escape_hatch(self):
        assert parse_watch_config({"servers": ["some-mcp"], "watch": False}) is None

    def test_watch_true_means_default_on(self):
        assert parse_watch_config({"servers": ["some-mcp"], "watch": True}) is not None

    def test_explicit_values(self):
        config = parse_watch_config(
            {
                "servers": ["some-mcp"],
                "watch": {
                    "interval": 10,
                    "timeout": 600,
                    "max_concurrent": 4,
                    "max_consecutive_failures": 5,
                },
            }
        )
        assert config.interval_seconds == 10.0
        assert config.timeout_seconds == 600.0
        assert config.max_concurrent == 4
        assert config.max_consecutive_failures == 5

    def test_unknown_key_fails_fast(self):
        with pytest.raises(WatchConfigError, match="unknown key"):
            parse_watch_config({"servers": ["s"], "watch": {"enabled": True}})

    def test_non_mapping_watch_fails_fast(self):
        with pytest.raises(WatchConfigError, match="mapping or false"):
            parse_watch_config({"servers": ["s"], "watch": "yes"})

    @pytest.mark.parametrize("key", ["interval", "timeout"])
    @pytest.mark.parametrize("value", [0, -1, "30s", True, None])
    def test_invalid_durations_fail_fast(self, key, value):
        with pytest.raises(WatchConfigError, match=f"mcp.watch.{key}"):
            parse_watch_config({"servers": ["s"], "watch": {key: value}})

    @pytest.mark.parametrize("key", ["max_concurrent", "max_consecutive_failures"])
    @pytest.mark.parametrize("value", [0, -2, 1.5, True, "3"])
    def test_invalid_counts_fail_fast(self, key, value):
        with pytest.raises(WatchConfigError, match=f"mcp.watch.{key}"):
            parse_watch_config({"servers": ["s"], "watch": {key: value}})

    def test_watch_without_servers_is_dead_config(self):
        with pytest.raises(WatchConfigError, match="no servers"):
            parse_watch_config({"servers": [], "watch": {"interval": 5}})


# ===================================================================
# Group-file override: mcp: {watch: {max_concurrent: N}}
# ===================================================================


def _write_group(tmp_path, name: str, content: str) -> None:
    (tmp_path / f"{name}.yaml").write_text(content)


class TestGroupWatchOverride:
    def test_group_override_parses(self, tmp_path):
        _write_group(
            tmp_path,
            "power-users",
            "agents: '*'\nmcp:\n  watch:\n    max_concurrent: 25\n",
        )
        groups = load_groups(str(tmp_path))
        assert groups["power-users"].watch_max_concurrent == 25

    def test_no_override_is_none(self, tmp_path):
        _write_group(tmp_path, "basic", "agents: '*'\n")
        groups = load_groups(str(tmp_path))
        assert groups["basic"].watch_max_concurrent is None

    def test_unknown_mcp_key_rejected(self, tmp_path):
        _write_group(tmp_path, "bad", "mcp:\n  servers: {}\n")
        with pytest.raises(GroupPermissionError, match="only 'watch'"):
            load_groups(str(tmp_path))

    def test_unknown_watch_key_rejected(self, tmp_path):
        _write_group(tmp_path, "bad", "mcp:\n  watch:\n    interval: 5\n")
        with pytest.raises(GroupPermissionError, match="only 'max_concurrent'"):
            load_groups(str(tmp_path))

    @pytest.mark.parametrize("value", ["0", "-1", "true", "'5'"])
    def test_invalid_quota_rejected(self, tmp_path, value):
        _write_group(tmp_path, "bad", f"mcp:\n  watch:\n    max_concurrent: {value}\n")
        with pytest.raises(GroupPermissionError, match="max_concurrent"):
            load_groups(str(tmp_path))

    def test_inheritance_keeps_highest(self, tmp_path):
        _write_group(tmp_path, "parent", "agents: '*'\nmcp:\n  watch:\n    max_concurrent: 25\n")
        _write_group(
            tmp_path,
            "child",
            "inherits: parent\nmcp:\n  watch:\n    max_concurrent: 10\n",
        )
        groups = load_groups(str(tmp_path))
        # Grants are additive: the inherited higher quota persists.
        assert groups["child"].watch_max_concurrent == 25

    def test_inheritance_child_raises(self, tmp_path):
        _write_group(tmp_path, "parent", "mcp:\n  watch:\n    max_concurrent: 5\n")
        _write_group(
            tmp_path,
            "child",
            "inherits: parent\nmcp:\n  watch:\n    max_concurrent: 30\n",
        )
        groups = load_groups(str(tmp_path))
        assert groups["child"].watch_max_concurrent == 30

    def test_resolver_highest_across_groups(self, tmp_path):
        _write_group(tmp_path, "a", "mcp:\n  watch:\n    max_concurrent: 5\n")
        _write_group(tmp_path, "b", "mcp:\n  watch:\n    max_concurrent: 15\n")
        _write_group(tmp_path, "c", "agents: '*'\n")
        resolver = PermissionResolver(load_groups(str(tmp_path)), formation_id="f")
        assert resolver.resolve_groups(["a", "b", "c"]).watch_max_concurrent == 15
        assert resolver.resolve_groups(["c"]).watch_max_concurrent is None
        assert resolver.resolve_groups([]).watch_max_concurrent is None
