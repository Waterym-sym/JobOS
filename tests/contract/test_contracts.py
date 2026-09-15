import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
WS_DIR = ROOT / "contracts" / "ws"


def collect_constants(value: Any) -> set[Any]:
    if isinstance(value, dict):
        result = {value["const"]} if "const" in value else set()
        for child in value.values():
            result.update(collect_constants(child))
        return result
    if isinstance(value, list):
        result: set[Any] = set()
        for child in value:
            result.update(collect_constants(child))
        return result
    return set()


def test_frozen_ws_contracts_are_valid_json_schema() -> None:
    for schema_path in WS_DIR.glob("*.schema.json"):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["x-status"] == "v1"


def test_rest_contract_is_frozen_and_loopback_only() -> None:
    openapi = (ROOT / "contracts" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    assert "version: 1.0.0" in openapi
    assert "x-status: v1" in openapi
    assert "http://127.0.0.1:8000/api/v1" in openapi


def test_capture_rest_contract_is_versioned_and_never_exposes_pairing_token() -> None:
    contract = yaml.safe_load(
        (ROOT / "contracts" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    paths = contract["paths"]
    assert {
        "/extension/status",
        "/captures",
        "/captures/{id}",
        "/captures/{id}/abort",
        "/raw-jobs",
    } <= set(paths)
    assert not any("pairing-token" in path for path in paths)
    assert contract["security"] == [{"pairingToken": []}]


def test_alembic_is_the_only_executable_migration_entry() -> None:
    assert not list((ROOT / "migrations").glob("*.sql"))
    assert not (ROOT / "services" / "api" / "app" / "migrate.py").exists()
    assert (ROOT / "alembic.ini").is_file()
    revisions = list((ROOT / "migrations" / "versions").glob("*.py"))
    assert len(revisions) == 1
    run_source = (ROOT / "services" / "api" / "run.py").read_text(encoding="utf-8")
    assert "run_migrations" not in run_source


def test_command_contract_has_no_forbidden_command_constants() -> None:
    commands = json.loads((WS_DIR / "commands.schema.json").read_text(encoding="utf-8"))
    command_constants = collect_constants(commands)
    forbidden = {
        "send_message",
        "deliver",
        "auto_apply",
        "auto_greet",
        "auto_upload",
    }
    assert command_constants.isdisjoint(forbidden)


def test_p0_golden_messages_validate() -> None:
    dataset = json.loads(
        (ROOT / "tests" / "fixtures" / "golden" / "ws-contract-v0.json").read_text(encoding="utf-8")
    )
    for case in dataset["cases"]:
        schema = json.loads((WS_DIR / case["schema"]).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        assert list(validator.iter_errors(case["payload"])) == []


def test_filter_boundary_fixture_matches_draft_schema() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "filters" / "filter-set.schema.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "rules" / "filter-boundary-v0.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(fixture["filter_set"])
