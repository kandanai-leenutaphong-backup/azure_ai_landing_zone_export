"""Offline constitution shape/path check; no grant or campaign execution."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import yaml
from jsonschema import Draft202012Validator, FormatChecker


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ValueError("YAML aliases are not supported")
        return super().compose_node(parent, index)


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("Non-string or duplicate field")
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
SCHEMA = json.loads(Path(__file__).with_name("constitution.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate(path: Path) -> list[str]:
    raw = path.read_bytes()
    if len(raw) > 65536:
        return ["document: exceeds 64 KiB"]
    document = yaml.load(raw, Loader=StrictLoader)
    json.dumps(document, allow_nan=False)
    errors = ["/" + "/".join(map(str, error.absolute_path)) + ": invalid " + str(error.validator)
              for error in VALIDATOR.iter_errors(document)]
    if errors:
        return sorted(errors)
    expected = ("agentcraft_projects", document["project_id"], "constitution", "constitution.yaml")
    if path.absolute().parts[-4:] != expected:
        errors.append("path: expected agentcraft_projects/<project-id>/constitution/constitution.yaml")
    identifiers = [metric["id"] for metric in document["metrics"]]
    if len(set(identifiers)) != len(identifiers):
        errors.append("/metrics: duplicate id")
    if document["primary_metric"] not in identifiers:
        errors.append("/primary_metric: undefined metric")
    if document["authority"]["expires_at"] is not None:
        expires = datetime.fromisoformat(document["authority"]["expires_at"].replace("Z", "+00:00"))
        if expires <= datetime.now(timezone.utc):
            errors.append("/authority/expires_at: expired")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("constitution", type=Path)
    args = parser.parse_args(argv)
    try:
        errors = validate(args.constitution)
    except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
        errors = ["document: unreadable or invalid YAML/JSON values"]
    result = {"status": "refused" if errors else "valid", "errors": errors,
              "scope": "structure only; semantic review and effective authorization still required"}
    if not errors:
        result["sha256"] = hashlib.sha256(args.constitution.read_bytes()).hexdigest()
    print(json.dumps(result))
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())