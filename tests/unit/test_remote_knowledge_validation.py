"""Unit tests for remote knowledge source config validation (fail-fast)."""

import pytest

from muxi.runtime.formation.config.validation import FormationValidator


@pytest.fixture
def validator():
    return FormationValidator()


def validate_sources(validator, sources):
    validator._validate_agent_knowledge_config({"enabled": True, "sources": sources})
    return validator.result


def remote(url, **fields):
    return {"url": url, "description": "remote source", **fields}


class TestLocalSourcesUnchanged:
    def test_local_path_source_still_valid(self, validator):
        result = validate_sources(validator, [{"path": "knowledge/faq/", "description": "faq"}])
        assert result.is_valid

    def test_local_source_missing_path_still_fails(self, validator):
        result = validate_sources(validator, [{"description": "faq"}])
        assert not result.is_valid
        assert any("'path' or 'url'" in e for e in result.errors)

    def test_path_and_url_together_rejected(self, validator):
        result = validate_sources(
            validator,
            [{"path": "knowledge/", "url": "https://x.com/d.md", "description": "d"}],
        )
        assert not result.is_valid
        assert any("not both" in e for e in result.errors)


class TestUrlSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "https://wiki.company.com/export/docs.md",
            "http://internal.corp/files/notes.txt",
            "s3://acme-bucket/policies/*",
            "rsync://docs-server/knowledge/",
            "rsync+ssh://docs@server.com/knowledge/",
            "file:///mounted/path/",
        ],
    )
    def test_supported_schemes_accepted(self, validator, url):
        result = validate_sources(validator, [remote(url)])
        assert result.is_valid, result.errors

    @pytest.mark.parametrize(
        "url", ["gs://bucket/x", "az://container/x", "ftp://h/x", "sftp://u@h/x"]
    )
    def test_planned_schemes_rejected_as_not_yet_supported(self, validator, url):
        result = validate_sources(validator, [remote(url)])
        assert not result.is_valid
        assert any("not yet supported" in e for e in result.errors)

    def test_unknown_scheme_rejected(self, validator):
        result = validate_sources(validator, [remote("gopher://host/x")])
        assert not result.is_valid
        assert any("unsupported URL scheme" in e for e in result.errors)

    def test_empty_url_rejected(self, validator):
        result = validate_sources(validator, [remote("  ")])
        assert not result.is_valid

    def test_http_glob_rejected(self, validator):
        result = validate_sources(validator, [remote("https://host/docs/*.md")])
        assert not result.is_valid
        assert any("glob" in e for e in result.errors)

    def test_s3_without_bucket_rejected(self, validator):
        result = validate_sources(validator, [remote("s3:///prefix/*")])
        assert not result.is_valid
        assert any("bucket" in e for e in result.errors)

    def test_file_requires_absolute_local_path(self, validator):
        result = validate_sources(validator, [remote("file://host/share")])
        assert not result.is_valid
        result2 = validate_sources(FormationValidator(), [remote("file:relative")])
        assert not result2.is_valid

    def test_description_required_for_remote_sources(self, validator):
        result = validate_sources(validator, [{"url": "https://h/x.md"}])
        assert not result.is_valid
        assert any("description" in e for e in result.errors)


class TestSourceIds:
    def test_duplicate_ids_rejected(self, validator):
        result = validate_sources(
            validator,
            [
                remote("https://h/a.md", id="docs"),
                remote("https://h/b.md", id="docs"),
            ],
        )
        assert not result.is_valid
        assert any("duplicate" in e for e in result.errors)

    def test_empty_id_rejected(self, validator):
        result = validate_sources(validator, [remote("https://h/a.md", id="  ")])
        assert not result.is_valid


class TestAuthBlocks:
    def test_http_basic_auth_valid(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "https://h/a.md",
                    auth={"type": "basic", "username": "u", "password": "p"},
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_http_basic_auth_missing_password(self, validator):
        result = validate_sources(
            validator, [remote("https://h/a.md", auth={"type": "basic", "username": "u"})]
        )
        assert not result.is_valid
        assert any("password" in e for e in result.errors)

    def test_bearer_requires_token(self, validator):
        result = validate_sources(validator, [remote("https://h/a.md", auth={"type": "bearer"})])
        assert not result.is_valid

    def test_s3_aws_auth_valid(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "s3://bucket/docs/*",
                    auth={
                        "type": "aws",
                        "access_key": "${{ secrets.AWS_ACCESS_KEY }}",
                        "secret_key": "${{ secrets.AWS_SECRET_KEY }}",
                        "region": "us-east-1",
                    },
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_s3_aws_auth_missing_secret_key(self, validator):
        result = validate_sources(
            validator, [remote("s3://bucket/x", auth={"type": "aws", "access_key": "k"})]
        )
        assert not result.is_valid
        assert any("secret_key" in e for e in result.errors)

    def test_auth_type_scheme_mismatch(self, validator):
        result = validate_sources(
            validator,
            [remote("s3://bucket/x", auth={"type": "basic", "username": "u", "password": "p"})],
        )
        assert not result.is_valid
        assert any("not valid for" in e for e in result.errors)

    def test_ssh_key_auth_for_rsync_ssh(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "rsync+ssh://user@host/path/",
                    auth={"type": "ssh_key", "key": "${{ secrets.RSYNC_SSH_KEY }}"},
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_auth_without_type_rejected(self, validator):
        result = validate_sources(validator, [remote("https://h/a.md", auth={"token": "x"})])
        assert not result.is_valid
        assert any("'type'" in e for e in result.errors)


class TestOptions:
    def test_headers_valid_for_http(self, validator):
        result = validate_sources(
            validator,
            [remote("https://h/a.md", headers={"Authorization": "Bearer ${{ secrets.T }}"})],
        )
        assert result.is_valid, result.errors

    def test_headers_rejected_for_s3(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", headers={"X-Custom": "v"})])
        assert not result.is_valid

    def test_headers_must_be_string_map(self, validator):
        result = validate_sources(validator, [remote("https://h/a.md", headers={"K": 5})])
        assert not result.is_valid

    def test_include_exclude_patterns(self, validator):
        result = validate_sources(
            validator,
            [remote("s3://bucket/docs/*", include=["*.md"], exclude=["drafts/*"])],
        )
        assert result.is_valid, result.errors

    def test_invalid_include_rejected(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", include="*.md")])
        assert not result.is_valid

    @pytest.mark.parametrize("key", ["max_files", "max_file_size", "max_total_size", "timeout"])
    def test_limits_must_be_positive_integers(self, validator, key):
        result = validate_sources(validator, [remote("s3://bucket/x", **{key: 0})])
        assert not result.is_valid
        result2 = validate_sources(FormationValidator(), [remote("s3://bucket/x", **{key: "10"})])
        assert not result2.is_valid

    def test_extract_rejected_in_phase_1(self, validator):
        result = validate_sources(validator, [remote("https://h/a.zip", extract=True)])
        assert not result.is_valid
        assert any("extraction" in e for e in result.errors)

    def test_schedule_cron_and_aliases_accepted(self, validator):
        result = validate_sources(
            validator,
            [
                remote("s3://bucket/a/*", schedule="*/15 * * * *"),
                remote("s3://bucket/b/*", schedule="@daily"),
                remote("s3://bucket/c/*", schedule="@startup"),
            ],
        )
        assert result.is_valid, result.errors

    def test_invalid_schedule_rejected(self, validator):
        result = validate_sources(
            validator, [remote("s3://bucket/x", schedule="whenever I feel like it")]
        )
        assert not result.is_valid
        assert any("schedule" in e for e in result.errors)


class TestFormationLevelKnowledge:
    def test_formation_knowledge_accepts_remote_sources(self, tmp_path, validator):
        validator._validate_knowledge_config({"sources": [remote("https://h/a.md")]}, tmp_path)
        assert validator.result.is_valid, validator.result.errors

    def test_formation_knowledge_rejects_bad_scheme(self, tmp_path, validator):
        validator._validate_knowledge_config({"sources": [remote("gopher://h/a.md")]}, tmp_path)
        assert not validator.result.is_valid
