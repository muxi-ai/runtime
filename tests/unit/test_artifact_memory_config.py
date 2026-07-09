"""Unit tests for the Artifact Memory configuration surface (Phase 1).

Covers the ``artifacts`` formation block parser (defaults, custom values,
relative path resolution, every rejection path), the FormationValidator
integration, and the no-config posture: capture defaults ON for
formations with persistent memory (PRD "Formation Schema") and is
disabled by ``enabled: false`` or by the absence of persistent storage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.initialization import _initialize_artifact_memory
from muxi.runtime.services.memory.artifacts import parse_artifacts_config


class TestParseDefaults:
    """No artifacts block gets the PRD defaults."""

    def test_defaults(self):
        settings = parse_artifacts_config(None)
        assert settings.enabled is True
        assert settings.storage_type == "local"
        assert settings.storage_path == Path("./artifacts")
        assert settings.encryption_enabled is True
        assert settings.retention_policy == "last_accessed"
        assert settings.retention_days == 0  # forever
        assert settings.max_size_bytes == 50 * 1024 * 1024  # PRD default: 50MB

    def test_empty_block_matches_defaults(self):
        assert parse_artifacts_config({}) == parse_artifacts_config(None)

    def test_relative_path_resolves_against_formation_dir(self):
        settings = parse_artifacts_config({}, formation_dir="/formations/demo")
        assert settings.storage_path == Path("/formations/demo/artifacts")

    def test_absolute_path_is_kept(self):
        settings = parse_artifacts_config(
            {"storage": {"path": "/var/muxi/artifacts"}}, formation_dir="/formations/demo"
        )
        assert settings.storage_path == Path("/var/muxi/artifacts")


class TestParseCustomValues:
    """Explicit values are honored."""

    def test_full_block(self):
        settings = parse_artifacts_config(
            {
                "enabled": True,
                "storage": {"type": "local", "path": "./my-artifacts"},
                "encryption": {"enabled": False},
                "retention": {"policy": "last_updated", "duration": 90},
                "max_size_mb": 10,
            }
        )
        assert settings.storage_path == Path("./my-artifacts")
        assert settings.encryption_enabled is False
        assert settings.retention_policy == "last_updated"
        assert settings.retention_days == 90
        assert settings.max_size_bytes == 10 * 1024 * 1024

    def test_disabled(self):
        assert parse_artifacts_config({"enabled": False}).enabled is False


class TestParseRejections:
    """Every invalid field fails loudly at config time."""

    def test_non_dict_block(self):
        with pytest.raises(ValueError, match="must be a dictionary"):
            parse_artifacts_config(["not", "a", "dict"])

    def test_non_bool_enabled(self):
        with pytest.raises(ValueError, match="artifacts.enabled"):
            parse_artifacts_config({"enabled": "yes"})

    def test_s3_not_supported_yet(self):
        with pytest.raises(ValueError, match="not supported yet"):
            parse_artifacts_config({"storage": {"type": "s3", "bucket": "b"}})

    def test_unknown_storage_type(self):
        with pytest.raises(ValueError, match="artifacts.storage.type"):
            parse_artifacts_config({"storage": {"type": "ftp"}})

    def test_empty_storage_path(self):
        with pytest.raises(ValueError, match="artifacts.storage.path"):
            parse_artifacts_config({"storage": {"path": "  "}})

    def test_non_bool_encryption(self):
        with pytest.raises(ValueError, match="artifacts.encryption.enabled"):
            parse_artifacts_config({"encryption": {"enabled": "on"}})

    def test_unknown_retention_policy(self):
        with pytest.raises(ValueError, match="artifacts.retention.policy"):
            parse_artifacts_config({"retention": {"policy": "created_at"}})

    def test_negative_duration(self):
        with pytest.raises(ValueError, match="artifacts.retention.duration"):
            parse_artifacts_config({"retention": {"duration": -1}})

    def test_non_integer_duration(self):
        with pytest.raises(ValueError, match="artifacts.retention.duration"):
            parse_artifacts_config({"retention": {"duration": "30"}})

    def test_boolean_duration_rejected(self):
        with pytest.raises(ValueError, match="artifacts.retention.duration"):
            parse_artifacts_config({"retention": {"duration": True}})

    def test_zero_max_size_rejected(self):
        with pytest.raises(ValueError, match="artifacts.max_size_mb"):
            parse_artifacts_config({"max_size_mb": 0})

    def test_non_integer_max_size_rejected(self):
        with pytest.raises(ValueError, match="artifacts.max_size_mb"):
            parse_artifacts_config({"max_size_mb": "50"})

    def test_boolean_max_size_rejected(self):
        with pytest.raises(ValueError, match="artifacts.max_size_mb"):
            parse_artifacts_config({"max_size_mb": True})


class TestFormationValidatorIntegration:
    """The formation validator reuses the same parser."""

    def test_valid_block_passes(self):
        validator = FormationValidator()
        validator._validate_artifacts_config(
            {"retention": {"policy": "last_updated", "duration": 30}}
        )
        assert validator.result.errors == []

    def test_invalid_block_is_flagged(self):
        validator = FormationValidator()
        validator._validate_artifacts_config({"retention": {"policy": "sometimes"}})
        assert any("artifacts.retention.policy" in error for error in validator.result.errors)

    def test_s3_block_is_flagged(self):
        validator = FormationValidator()
        validator._validate_artifacts_config({"storage": {"type": "s3"}})
        assert any("not supported yet" in error for error in validator.result.errors)


class _FormationStub:
    """Minimal formation shape for the initialization wiring tests."""

    def __init__(self, config=None, db_manager=None, formation_path=None):
        self.config = config or {}
        self.formation_id = "stub-formation"
        self._db_manager = db_manager
        self._formation_path = formation_path

    def get_formation_path(self):
        return self._formation_path


class TestInitializationWiring:
    """_initialize_artifact_memory honors the enable/disable posture."""

    def test_enabled_false_yields_no_service(self):
        formation = _FormationStub(config={"artifacts": {"enabled": False}})
        _initialize_artifact_memory(formation)
        assert formation._artifact_memory is None

    def test_default_on_with_persistent_memory(self, tmp_path):
        from muxi.runtime.services.db import Base, DatabaseManager
        from muxi.runtime.services.memory.artifacts.models import Artifact, SystemConfig

        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/memory.db")
        db_manager.create_tables(Base.metadata, tables=[Artifact.__table__, SystemConfig.__table__])
        formation = _FormationStub(config={}, db_manager=db_manager, formation_path=str(tmp_path))
        _initialize_artifact_memory(formation)
        service = formation._artifact_memory
        assert service is not None
        assert service.enabled is True
        # Default local storage resolves next to the formation.
        assert service.settings.storage_path == tmp_path / "artifacts"
        db_manager.engine.dispose()

    def test_invalid_config_disables_capture_without_raising(self):
        formation = _FormationStub(config={"artifacts": {"storage": {"type": "s3"}}})
        _initialize_artifact_memory(formation)
        assert formation._artifact_memory is None
