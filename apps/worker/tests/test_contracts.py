"""contracts/ is the source of truth: every example must validate, every invalid example must fail,
and the Pydantic mirrors must agree with the JSON Schemas."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from inland_worker.contracts.models import AnalysisJobMessage, Evidence, JobEvent

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLES = CONTRACTS / "examples"
SCHEMAS = {
    "evidence": "evidence.schema.json",
    "analysis-job": "analysis-job.schema.json",
    "job-event": "job-event.schema.json",
}
MODELS = {"evidence": Evidence, "analysis-job": AnalysisJobMessage, "job-event": JobEvent}


def _registry() -> Registry:
    resources = []
    for name in SCHEMAS.values():
        contents = json.loads((CONTRACTS / name).read_text())
        res = Resource.from_contents(contents, default_specification=DRAFT202012)
        resources += [((CONTRACTS / name).as_uri(), res), (contents["$id"], res)]
    openapi = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text())
    resources.append(((CONTRACTS / "openapi.yaml").as_uri(), DRAFT202012.create_resource(openapi)))
    return Registry().with_resources(resources)


REGISTRY = _registry()


def validator_for(ref: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": ref}, registry=REGISTRY, format_checker=Draft202012Validator.FORMAT_CHECKER
    )


def _examples(kind: str, invalid: bool = False) -> list[Path]:
    base = EXAMPLES / "invalid" / kind if invalid else EXAMPLES / kind
    return sorted(base.glob("*.json"))


def test_openapi_document_is_valid():
    spec = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text())
    validate_openapi(spec, base_uri=(CONTRACTS / "openapi.yaml").as_uri())


@pytest.mark.parametrize("name", SCHEMAS.values())
def test_schemas_are_valid_json_schema(name):
    Draft202012Validator.check_schema(json.loads((CONTRACTS / name).read_text()))


@pytest.mark.parametrize("kind", SCHEMAS)
def test_each_schema_has_examples(kind):
    assert _examples(kind), f"add at least one example under contracts/examples/{kind}/"


@pytest.mark.parametrize(
    "path", [p for k in SCHEMAS for p in _examples(k)], ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_example_valid_in_schema_and_pydantic(path):
    kind = path.parent.name
    data = json.loads(path.read_text())
    errors = list(validator_for((CONTRACTS / SCHEMAS[kind]).as_uri()).iter_errors(data))
    assert not errors, errors[0].message
    MODELS[kind].model_validate(data)


@pytest.mark.parametrize(
    "path",
    [p for k in SCHEMAS for p in _examples(k, invalid=True)],
    ids=lambda p: f"invalid/{p.parent.name}/{p.name}",
)
def test_invalid_example_rejected_by_schema_and_pydantic(path):
    kind = path.parent.name
    data = json.loads(path.read_text())
    assert list(validator_for((CONTRACTS / SCHEMAS[kind]).as_uri()).iter_errors(data)), "schema accepted it"
    if kind != "evidence" or "bad-flag" not in path.name:  # flag format is a schema-only rule
        with pytest.raises(ValueError):
            MODELS[kind].model_validate(data)


@pytest.mark.parametrize("path", sorted((EXAMPLES / "openapi").glob("*.json")), ids=lambda p: p.name)
def test_openapi_component_examples(path):
    component = path.name.split(".")[0]
    ref = f"{(CONTRACTS / 'openapi.yaml').as_uri()}#/components/schemas/{component}"
    errors = list(validator_for(ref).iter_errors(json.loads(path.read_text())))
    assert not errors, errors[0].message


def test_pydantic_evidence_types_match_schema():
    schema = json.loads((CONTRACTS / "evidence.schema.json").read_text())
    from inland_worker.contracts.models import EvidenceType

    assert set(schema["$defs"]["EvidenceType"]["enum"]) == {e.value for e in EvidenceType}
