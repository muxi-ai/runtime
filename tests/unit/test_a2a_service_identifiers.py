from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.services.a2a.identifiers import get_service_identifier


def _validate(services):
    validator = FormationValidator()
    validator._validate_a2a_config({"outbound": {"services": services}})
    return validator.result


def test_service_identifier_falls_back_when_canonical_id_is_blank():
    assert (
        get_service_identifier({"id": "  ", "service_id": " legacy-service "}) == "legacy-service"
    )


def test_outbound_service_accepts_canonical_id():
    result = _validate(
        [
            {
                "id": "analytics",
                "url": "https://analytics.example.com",
                "auth": {"type": "bearer", "token": "token"},
            }
        ]
    )

    assert not result.errors
    assert not result.warnings


def test_outbound_service_accepts_legacy_service_id_with_warning():
    result = _validate(
        [
            {
                "service_id": "analytics.example.com",
                "auth": {"type": "bearer", "token": "token"},
            }
        ]
    )

    assert not result.errors
    assert any("deprecated service_id" in warning for warning in result.warnings)


def test_outbound_service_requires_an_identifier():
    result = _validate([{"auth": {"type": "bearer", "token": "token"}}])

    assert any("missing required field: id" in error for error in result.errors)


def test_outbound_service_rejects_duplicate_legacy_identifiers():
    result = _validate(
        [
            {"service_id": "analytics.example.com"},
            {"service_id": "analytics.example.com"},
        ]
    )

    assert any("Duplicate A2A service id" in error for error in result.errors)


def test_service_file_accepts_legacy_service_id_with_warning():
    validator = FormationValidator()
    validator._validate_a2a_service_config(
        {
            "schema": "1.0.0",
            "service_id": "analytics.example.com",
            "name": "Analytics",
            "description": "Analytics service",
            "url": "https://analytics.example.com",
            "auth": {"type": "bearer", "token": "token"},
        },
        "analytics.afs",
    )

    assert not validator.result.errors
    assert any("deprecated service_id" in warning for warning in validator.result.warnings)
