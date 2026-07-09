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
            "gs://acme-bucket/policies/*",
            "rsync://docs-server/knowledge/",
            "rsync+ssh://docs@server.com/knowledge/",
            "ftp://files.corp/docs/*.pdf",
            "sftp://user@host/docs/",
            "file:///mounted/path/",
        ],
    )
    def test_supported_schemes_accepted(self, validator, url):
        result = validate_sources(validator, [remote(url)])
        assert result.is_valid, result.errors

    def test_az_scheme_accepted_with_auth(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "az://container/docs/*",
                    auth={"type": "azure", "connection_string": "${{ secrets.AZ_CONN }}"},
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_az_requires_auth_block(self, validator):
        result = validate_sources(validator, [remote("az://container/docs/*")])
        assert not result.is_valid
        assert any("'auth'" in e for e in result.errors)

    @pytest.mark.parametrize("url", ["gs:///prefix/*", "ftp:///x", "sftp:///x"])
    def test_new_schemes_require_host_or_bucket(self, validator, url):
        result = validate_sources(validator, [remote(url)])
        assert not result.is_valid

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

    def test_s3_aws_auth_secret_key_without_access_key(self, validator):
        result = validate_sources(
            validator, [remote("s3://bucket/x", auth={"type": "aws", "secret_key": "s"})]
        )
        assert not result.is_valid
        assert any("access_key" in e for e in result.errors)

    def test_s3_aws_auth_default_credential_chain(self, validator):
        """No explicit keys: boto3's default credential chain applies."""
        result = validate_sources(
            validator,
            [remote("s3://bucket/docs/*", auth={"type": "aws", "region": "us-east-1"})],
        )
        assert result.is_valid, result.errors

    def test_s3_aws_auth_type_only(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", auth={"type": "aws"})])
        assert result.is_valid, result.errors

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

    def test_accept_new_host_keys_valid_for_rsync_ssh(self, validator):
        result = validate_sources(
            validator,
            [remote("rsync+ssh://user@host/path/", accept_new_host_keys=True)],
        )
        assert result.is_valid, result.errors

    def test_accept_new_host_keys_rejected_for_other_schemes(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", accept_new_host_keys=True)])
        assert not result.is_valid
        assert any("accept_new_host_keys" in e for e in result.errors)

    def test_accept_new_host_keys_must_be_boolean(self, validator):
        result = validate_sources(
            validator,
            [remote("rsync+ssh://user@host/path/", accept_new_host_keys="yes")],
        )
        assert not result.is_valid
        assert any("boolean" in e for e in result.errors)

    def test_accept_new_host_keys_valid_for_sftp(self, validator):
        result = validate_sources(
            validator,
            [remote("sftp://user@host/docs/", accept_new_host_keys=True)],
        )
        assert result.is_valid, result.errors

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


class TestArchiveExtractionOptions:
    def test_extract_zip_source_valid(self, validator):
        result = validate_sources(
            validator,
            [remote("https://h/export.zip", extract=True, extract_pattern="**/*.md")],
        )
        assert result.is_valid, result.errors

    def test_extract_must_be_boolean(self, validator):
        result = validate_sources(validator, [remote("https://h/a.zip", extract="yes")])
        assert not result.is_valid
        assert any("boolean" in e for e in result.errors)

    def test_extract_pattern_requires_extract(self, validator):
        result = validate_sources(validator, [remote("https://h/a.zip", extract_pattern="**/*.md")])
        assert not result.is_valid
        assert any("requires 'extract: true'" in e for e in result.errors)

    def test_extract_rejected_for_rsync(self, validator):
        result = validate_sources(validator, [remote("rsync://server/docs/", extract=True)])
        assert not result.is_valid
        assert any("not valid for rsync" in e for e in result.errors)

    def test_extract_rejected_with_glob_url(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/*.zip", extract=True)])
        assert not result.is_valid
        assert any("single archive" in e for e in result.errors)

    @pytest.mark.parametrize("key", ["max_extracted_files", "max_extracted_size"])
    def test_extraction_bounds_positive_integers(self, validator, key):
        result = validate_sources(validator, [remote("https://h/a.zip", extract=True, **{key: 0})])
        assert not result.is_valid
        result2 = validate_sources(
            FormationValidator(), [remote("https://h/a.zip", extract=True, **{key: 500})]
        )
        assert result2.is_valid, result2.errors

    def test_extraction_bounds_require_extract(self, validator):
        result = validate_sources(validator, [remote("https://h/a.zip", max_extracted_files=10)])
        assert not result.is_valid
        assert any("requires 'extract: true'" in e for e in result.errors)

    def test_empty_extract_pattern_rejected(self, validator):
        result = validate_sources(
            validator, [remote("https://h/a.zip", extract=True, extract_pattern="  ")]
        )
        assert not result.is_valid


class TestRetryBlock:
    def test_full_retry_block_valid(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "s3://bucket/docs/*",
                    retry={
                        "max_attempts": 5,
                        "initial_delay": 2,
                        "max_delay": 120.5,
                        "exponential_base": 2,
                    },
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_retry_must_be_mapping(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", retry=3)])
        assert not result.is_valid
        assert any("mapping" in e for e in result.errors)

    def test_unknown_retry_key_rejected(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", retry={"delay": 5})])
        assert not result.is_valid
        assert any("not recognized" in e for e in result.errors)

    def test_max_attempts_positive_integer(self, validator):
        result = validate_sources(validator, [remote("s3://bucket/x", retry={"max_attempts": 0})])
        assert not result.is_valid

    @pytest.mark.parametrize("key", ["initial_delay", "max_delay"])
    def test_delays_positive_numbers(self, validator, key):
        result = validate_sources(validator, [remote("s3://bucket/x", retry={key: -1})])
        assert not result.is_valid

    def test_exponential_base_at_least_one(self, validator):
        result = validate_sources(
            validator, [remote("s3://bucket/x", retry={"exponential_base": 0.5})]
        )
        assert not result.is_valid


class TestPhase4AuthBlocks:
    def test_gcp_auth_with_credentials_json(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "gs://bucket/docs/*",
                    auth={"type": "gcp", "credentials_json": "${{ secrets.GCP_SA_JSON }}"},
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_gcp_auth_default_credential_chain(self, validator):
        result = validate_sources(validator, [remote("gs://bucket/x", auth={"type": "gcp"})])
        assert result.is_valid, result.errors

    def test_gcp_auth_empty_credentials_json_rejected(self, validator):
        result = validate_sources(
            validator, [remote("gs://bucket/x", auth={"type": "gcp", "credentials_json": " "})]
        )
        assert not result.is_valid

    def test_azure_auth_account_pair_valid(self, validator):
        result = validate_sources(
            validator,
            [
                remote(
                    "az://container/x",
                    auth={
                        "type": "azure",
                        "account_name": "acme",
                        "account_key": "${{ secrets.AZ_KEY }}",
                    },
                )
            ],
        )
        assert result.is_valid, result.errors

    def test_azure_auth_account_name_without_key_rejected(self, validator):
        result = validate_sources(
            validator,
            [remote("az://container/x", auth={"type": "azure", "account_name": "acme"})],
        )
        assert not result.is_valid
        assert any("account_key" in e for e in result.errors)

    def test_azure_auth_type_alone_rejected(self, validator):
        result = validate_sources(validator, [remote("az://container/x", auth={"type": "azure"})])
        assert not result.is_valid
        assert any("connection_string" in e for e in result.errors)

    def test_ftp_basic_auth_valid(self, validator):
        result = validate_sources(
            validator,
            [remote("ftp://h/docs/", auth={"type": "basic", "username": "u", "password": "p"})],
        )
        assert result.is_valid, result.errors

    def test_sftp_ssh_key_auth_valid(self, validator):
        result = validate_sources(
            validator,
            [remote("sftp://u@h/docs/", auth={"type": "ssh_key", "key": "${{ secrets.K }}"})],
        )
        assert result.is_valid, result.errors

    def test_sftp_password_auth_valid(self, validator):
        result = validate_sources(
            validator,
            [remote("sftp://h/docs/", auth={"type": "basic", "username": "u", "password": "p"})],
        )
        assert result.is_valid, result.errors

    def test_ftp_ssh_key_auth_rejected(self, validator):
        result = validate_sources(
            validator, [remote("ftp://h/docs/", auth={"type": "ssh_key", "key": "k"})]
        )
        assert not result.is_valid
        assert any("not valid for" in e for e in result.errors)


class TestFormationLevelKnowledge:
    def test_formation_knowledge_accepts_remote_sources(self, tmp_path, validator):
        validator._validate_knowledge_config({"sources": [remote("https://h/a.md")]}, tmp_path)
        assert validator.result.is_valid, validator.result.errors

    def test_formation_knowledge_rejects_bad_scheme(self, tmp_path, validator):
        validator._validate_knowledge_config({"sources": [remote("gopher://h/a.md")]}, tmp_path)
        assert not validator.result.is_valid
