"""Unit tests for the adapter's pure logic (no formation boot).

The formation-backed paths (start/ingest/search against real memory)
are exercised by the harness self-run; these tests pin the mapping,
truncation, and run-dir rendering logic that the self-run depends on.
"""

from pathlib import Path

import pytest
import yaml

from bench.memory.adapter import (
    DEFAULT_FORMATION_YAML,
    MuxiMemoryAdapter,
    RetrievedItem,
)
from bench.memory.datasets import Session, Turn


def _adapter(mode="working", **kwargs):
    return MuxiMemoryAdapter(mode=mode, **kwargs)


class TestConstruction:
    def test_rejects_unknown_mode(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            MuxiMemoryAdapter(mode="kg-routing")

    def test_default_formation_yaml_exists(self):
        assert DEFAULT_FORMATION_YAML.exists()


class TestResultMapping:
    def test_working_results_mapped(self):
        raw = [
            {
                "text": "user: hello",
                "score": 0.9,
                "metadata": {
                    "bench_turn_id": "s1:0",
                    "bench_session_id": "s1",
                },
            },
            # Item without bench ids (e.g. other namespace) is skipped.
            {"text": "noise", "score": 0.8, "metadata": {}},
        ]
        items = MuxiMemoryAdapter._items_from_working(raw)
        assert len(items) == 1
        assert items[0].turn_id == "s1:0"
        assert items[0].session_id == "s1"
        assert items[0].source == "working"

    def test_persistent_results_mapped(self):
        raw = [
            {
                "text": "assistant: hi",
                "score": 0.7,
                "metadata": {"bench_turn_id": "s2:1", "bench_session_id": "s2"},
            }
        ]
        items = MuxiMemoryAdapter._items_from_persistent(raw)
        assert items[0].source == "persistent"
        assert items[0].score == 0.7

    def test_ranked_session_ids_dedupe_by_best_turn(self):
        items = [
            RetrievedItem("s1:0", "s1", "a", 0.9, "working"),
            RetrievedItem("s2:0", "s2", "b", 0.8, "working"),
            RetrievedItem("s1:1", "s1", "c", 0.7, "working"),
        ]
        assert MuxiMemoryAdapter.ranked_session_ids(items) == ["s1", "s2"]
        assert MuxiMemoryAdapter.ranked_turn_ids(items) == ["s1:0", "s2:0", "s1:1"]


class TestTurnRendering:
    def test_date_and_role_prefix(self):
        adapter = _adapter()
        session = Session(
            session_id="s1",
            turns=(),
            date="2023/04/02 (Sun) 09:12",
        )
        turn = Turn(turn_id="s1:0", role="user", content="hello world")
        text = adapter._render_turn_text(session, turn)
        assert text == "[2023/04/02 (Sun) 09:12] user: hello world"
        assert adapter.truncated_turns == 0

    def test_no_date(self):
        adapter = _adapter()
        session = Session(session_id="s1", turns=())
        turn = Turn(turn_id="s1:0", role="Nadia", content="hi")
        assert adapter._render_turn_text(session, turn) == "Nadia: hi"

    def test_truncation_counted(self):
        adapter = _adapter(max_embed_chars=20)
        session = Session(session_id="s1", turns=())
        turn = Turn(turn_id="s1:0", role="user", content="x" * 100)
        text = adapter._render_turn_text(session, turn)
        assert len(text) == 20
        assert adapter.truncated_turns == 1


class TestRunDirRendering:
    def test_renders_run_local_sqlite_path(self, tmp_path):
        adapter = _adapter(run_dir=tmp_path / "run", secrets_dir=tmp_path / "nosecrets")
        rendered = adapter._prepare_run_dir()
        assert rendered == tmp_path / "run" / "formation.yaml"
        config = yaml.safe_load(rendered.read_text())
        connection = config["memory"]["persistent"]["connection_string"]
        assert connection == str(tmp_path / "run" / "membench.db")
        # Template fields survive the rewrite.
        assert config["id"] == "membench"
        assert config["llm"]["models"][1]["embedding"].startswith("local/")

    def test_secrets_symlinked_when_present(self, tmp_path):
        secrets_dir = tmp_path / "assets"
        secrets_dir.mkdir()
        (secrets_dir / ".key").write_text("key")
        (secrets_dir / "secrets.enc").write_text("enc")
        adapter = _adapter(run_dir=tmp_path / "run", secrets_dir=secrets_dir)
        adapter._prepare_run_dir()
        assert (tmp_path / "run" / ".key").exists()
        assert (tmp_path / "run" / "secrets.enc").exists()

    def test_missing_secrets_tolerated(self, tmp_path):
        adapter = _adapter(run_dir=tmp_path / "run", secrets_dir=tmp_path / "missing")
        adapter._prepare_run_dir()
        assert not (tmp_path / "run" / ".key").exists()

    def test_idempotent(self, tmp_path):
        secrets_dir = tmp_path / "assets"
        secrets_dir.mkdir()
        (secrets_dir / ".key").write_text("key")
        (secrets_dir / "secrets.enc").write_text("enc")
        adapter = _adapter(run_dir=tmp_path / "run", secrets_dir=secrets_dir)
        adapter._prepare_run_dir()
        adapter._prepare_run_dir()  # second call must not raise on symlinks


class TestFormationTemplate:
    def test_template_is_cheap_model_configuration(self):
        config = yaml.safe_load(Path(DEFAULT_FORMATION_YAML).read_text())
        models = {k: v for entry in config["llm"]["models"] for k, v in entry.items()}
        assert models["text"] == "openai/gpt-4o-mini"
        assert models["embedding"] == "local/nomic-ai/nomic-embed-text-v1.5"
        assert config["memory"]["persistent"]["provider"] == "sqlite"
        assert config["memory"]["buffer"]["vector_search"] is True
        # Buffer must hold the largest LongMemEval-S haystack (~2.5k turns).
        buffer = config["memory"]["buffer"]
        assert buffer["size"] * buffer["multiplier"] >= 2500


class TestStopAndRunDirCleanup:
    async def test_stop_on_never_started_adapter(self):
        adapter = _adapter()
        await adapter.stop()  # must not raise
        assert adapter.formation is None

    async def test_stop_is_idempotent(self, tmp_path):
        adapter = _adapter(secrets_dir=tmp_path / "nosecrets")
        adapter._prepare_run_dir()
        await adapter.stop()
        await adapter.stop()  # second call is a no-op, must not raise

    async def test_temp_run_dir_removed_on_stop(self, tmp_path):
        adapter = _adapter(secrets_dir=tmp_path / "nosecrets")
        adapter._prepare_run_dir()  # run_dir=None -> adapter-created temp dir
        run_dir = adapter.run_dir
        assert run_dir.exists()
        await adapter.stop()
        assert not run_dir.exists()

    async def test_keep_run_dir_flag_preserves_temp_dir(self, tmp_path):
        adapter = _adapter(secrets_dir=tmp_path / "nosecrets", keep_run_dir=True)
        adapter._prepare_run_dir()
        run_dir = adapter.run_dir
        await adapter.stop()
        assert run_dir.exists()
        # Manual cleanup since the adapter intentionally kept it.
        import shutil

        shutil.rmtree(run_dir, ignore_errors=True)

    async def test_keep_run_dir_env_var_preserves_temp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUXI_BENCH_KEEP_RUN_DIR", "1")
        adapter = _adapter(secrets_dir=tmp_path / "nosecrets")
        adapter._prepare_run_dir()
        run_dir = adapter.run_dir
        await adapter.stop()
        assert run_dir.exists()
        import shutil

        shutil.rmtree(run_dir, ignore_errors=True)

    async def test_keep_run_dir_env_var_false_values_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUXI_BENCH_KEEP_RUN_DIR", "0")
        adapter = _adapter(secrets_dir=tmp_path / "nosecrets")
        adapter._prepare_run_dir()
        run_dir = adapter.run_dir
        await adapter.stop()
        assert not run_dir.exists()

    async def test_user_supplied_run_dir_never_removed(self, tmp_path):
        run_dir = tmp_path / "my-run"
        adapter = _adapter(run_dir=run_dir, secrets_dir=tmp_path / "nosecrets")
        adapter._prepare_run_dir()
        await adapter.stop()
        assert run_dir.exists()

    async def test_corrupt_yaml_failure_cleans_temp_dir(self, tmp_path):
        # Unparseable YAML fails during run-dir rendering, before the
        # Formation exists; stop() must still remove the temp dir.
        import yaml as yaml_module

        bad_yaml = tmp_path / "broken.yaml"
        bad_yaml.write_text("agents: [unbalanced")
        adapter = _adapter(formation_yaml=bad_yaml, secrets_dir=tmp_path / "nosecrets")
        with pytest.raises(yaml_module.YAMLError):
            await adapter.start()
        run_dir = adapter.run_dir
        assert run_dir is not None and run_dir.exists()
        await adapter.stop()
        assert not run_dir.exists()

    @pytest.mark.timeout(120)
    async def test_formation_load_failure_reaches_stop_and_cleans_temp_dir(self, tmp_path):
        # Valid YAML but an invalid formation: Formation.load() raises
        # after the Formation object exists (the partially-started
        # case); stop() must tear it down and remove the temp dir.
        from muxi.runtime.datatypes.exceptions import ConfigurationValidationError

        bad_yaml = tmp_path / "invalid.yaml"
        bad_yaml.write_text('schema: "1.0.0"\nid: "broken"\nagents: []\n')  # no llm/description
        adapter = _adapter(formation_yaml=bad_yaml, secrets_dir=tmp_path / "nosecrets")
        with pytest.raises(ConfigurationValidationError):
            await adapter.start()
        run_dir = adapter.run_dir
        assert run_dir is not None and run_dir.exists()
        assert adapter.formation is not None  # partially started
        await adapter.stop()
        assert not run_dir.exists()
        assert adapter.formation is None
