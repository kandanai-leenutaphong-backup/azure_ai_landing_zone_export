import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

import hosted_agent
from verify_hosted_logs import inspect_events, workflow_complete, CORRELATION, FIELDS


def test_native_source_archive_contains_only_declared_members_and_is_reproducible(tmp_path):
    app = tmp_path / "app"
    (app / "hosted").mkdir(parents=True)
    for path in ("hosted/main.py", "hosted/runtime.py", "hosted/validation.py",
                 "hosted/requirements.txt", "scenarios.py", "telemetry.py"):
        (app / path).write_text("# owned source\n")
    (app / ".env").write_text("DO_NOT_EXPORT=private\n")
    (app / "hosted/test_runtime.py").write_text("# excluded\n")
    destination = tmp_path / "code.zip"
    digest = hosted_agent.package_code(app, destination)
    assert hosted_agent.package_code(app, destination) == digest
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            "main.py", "runtime.py", "validation.py", "requirements.txt", "scenarios.py", "telemetry.py",
        }
    (app / "hosted/runtime.py").unlink()
    (app / "hosted/runtime.py").symlink_to(app / "scenarios.py")
    with pytest.raises(ValueError, match="symlinks"):
        hosted_agent.package_code(app, destination)


def test_hosted_readback_requires_exact_code_configuration_and_download_digest():
    definition = hosted_agent.definition("gpt-4.1-mini")
    source = b"exact native code archive"
    digest = hashlib.sha256(source).hexdigest()
    actual = SimpleNamespace(
        definition=definition, status="active",
        metadata={"owner": hosted_agent.OWNER, "source_sha256": digest},
    )
    project = SimpleNamespace(agents=Mock())
    project.agents.get_version.return_value = actual
    project.agents.download_code.return_value = [source]
    assert hosted_agent.verify_version(project, "1", definition, digest)["downloaded_source_matches"]
    project.agents.download_code.return_value = [b"different bytes"]
    with pytest.raises(RuntimeError, match="Downloaded deployed source"):
        hosted_agent.verify_version(project, "1", definition, digest)
    actual.definition = hosted_agent.definition("different-model")
    with pytest.raises(RuntimeError, match="environment_variables"):
        hosted_agent.verify_version(project, "1", definition, digest)


def test_native_log_readback_retains_only_structured_allowlist():
    event = {name: None for name in FIELDS}
    event.update(agent_id="policy", trace_id="a" * 32, status="ok",
                 raw_prompt="must not be retained", private_diagnostic="must not be retained")
    lines = [
        "event: log", "data: not-json", "data: []",
        "data: " + json.dumps({"message": "ordinary startup log"}),
        "data: " + json.dumps({"message": json.dumps(event)}),
    ]
    rows = inspect_events(lines)
    assert len(rows) == 1
    assert set(rows[0]) == set(FIELDS + CORRELATION)
    assert "must not be retained" not in json.dumps(rows)


def test_log_readback_waits_for_workflow_row_after_agent_steps():
    steps = [{"operation_type": "chat.agent", "agent_id": role} for role in ("triage", "policy", "resolution")]
    assert not workflow_complete(steps)
    assert workflow_complete(steps + [{"operation_type": "chat.workflow", "agent_id": "cs-customer-service-chat"}])
    assert not workflow_complete(steps[:2] + [{"operation_type": "chat.workflow", "agent_id": "x"}])
